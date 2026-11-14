"""Background rules, all deterministic code. `tick()` is pure enough to unit-test with a fake clock.

1. Verification calls: FIX_CLAIMED tickets whose next_verify_at has passed get a `verification`
   outbox row for the ORIGINAL caller's device (attempts +1, retry later). After max attempts with no
   yes/no answer the ticket becomes UNVERIFIED. Never during quiet hours (deferred), unless the demo
   flag DEMO_IGNORE_QUIET_HOURS is on (labelled "time compressed" in the UI).
2. SLA escalation: NEW/ACKED tickets older than the SLA for their priority move up one level.
3. Retention: transcripts older than the retention window are erased.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .. import db
from ..config import settings
from .priority import escalate
from .tickets import _event

log = logging.getLogger("jalawaaz.scheduler")


def _local(now: datetime) -> datetime:
    return now.astimezone(timezone(timedelta(minutes=settings.cfg["calling"]["tz_offset_minutes"])))


def in_quiet_hours(now: datetime) -> bool:
    start, end = settings.cfg["calling"]["quiet_hours"]
    t = _local(now).strftime("%H:%M")
    return (t >= start or t < end) if start > end else (start <= t < end)


def quiet_end(now: datetime) -> datetime:
    _, end = settings.cfg["calling"]["quiet_hours"]
    loc = _local(now)
    h, m = map(int, end.split(":"))
    cand = loc.replace(hour=h, minute=m, second=0, microsecond=0)
    if cand <= loc:
        cand += timedelta(days=1)
    return cand.astimezone(timezone.utc)


def retry_delay() -> timedelta:
    if settings.DEMO_MODE:
        return timedelta(seconds=settings.DEMO_VERIFY_RETRY_SEC)
    return timedelta(hours=settings.cfg["calling"]["verify_retry_hours"])


def tick(con, now: datetime | None = None) -> dict:
    now = now or db.now()
    stamp = db.ts(now)
    stats = {"queued": 0, "unverified": 0, "deferred": 0, "escalated": 0, "purged": 0}
    calling = settings.cfg["calling"]
    respect_quiet = not (settings.DEMO_MODE and settings.DEMO_IGNORE_QUIET_HOURS)

    due = con.execute("SELECT * FROM tickets WHERE state='FIX_CLAIMED' AND next_verify_at IS NOT NULL"
                      " AND next_verify_at<=?", (stamp,)).fetchall()
    for t in due:
        t = dict(t)
        with db.tx(con):
            if t["verify_attempts"] >= calling["max_verify_attempts"]:
                con.execute("UPDATE tickets SET state='UNVERIFIED', unverified_at=?, next_verify_at=NULL WHERE id=?",
                            (stamp, t["id"]))
                con.execute("DELETE FROM outbox WHERE ticket_id=? AND delivered=0", (t["id"],))
                _event(con, t["id"], "scheduler", "state", "FIX_CLAIMED", "UNVERIFIED", t["priority"], t["priority"],
                       f"no answer after {t['verify_attempts']} verification attempts")
                stats["unverified"] += 1
                continue
            if respect_quiet and in_quiet_hours(now):
                con.execute("UPDATE tickets SET next_verify_at=? WHERE id=?", (db.ts(quiet_end(now)), t["id"]))
                stats["deferred"] += 1
                continue
            con.execute("DELETE FROM outbox WHERE ticket_id=? AND kind='verification' AND delivered=0", (t["id"],))
            con.execute("INSERT INTO outbox(device_hash, kind, ticket_id, ready_at) VALUES (?,?,?,?)",
                        (t["caller_hash"], "verification", t["id"], stamp))
            con.execute("UPDATE tickets SET verify_attempts=verify_attempts+1, next_verify_at=? WHERE id=?",
                        (db.ts(now + retry_delay()), t["id"]))
            _event(con, t["id"], "scheduler", "verify_call_queued", detail=f"attempt {t['verify_attempts'] + 1}")
            stats["queued"] += 1

    for t in con.execute("SELECT * FROM tickets WHERE state IN ('NEW','ACKED')").fetchall():
        t = dict(t)
        sla = timedelta(hours=float(settings.cfg["sla_hours"][str(t["priority"])]))
        ref = db.parse_ts(t["last_escalated_at"] or t["created_at"])
        if ref and now - ref > sla:
            newp = escalate(t["priority"])
            with db.tx(con):
                note = (f"; SLA missed ({settings.cfg['sla_hours'][str(t['priority'])]} h at P{t['priority']})"
                        if newp != t["priority"] else "")
                con.execute("UPDATE tickets SET previous_priority=?, priority=?, escalated_count=escalated_count+1,"
                            " last_escalated_at=?, priority_reason=priority_reason || ? WHERE id=?",
                            (t["priority"], newp, stamp, note, t["id"]))
                _event(con, t["id"], "scheduler", "sla_escalation" if newp != t["priority"] else "sla_breach_p1",
                       from_p=t["priority"], to_p=newp, detail=f"{t['state']} beyond {sla} SLA")
            stats["escalated"] += 1

    cutoff = db.ts(now - timedelta(days=settings.cfg["privacy"]["transcript_retention_days"]))
    cur = con.execute("UPDATE reports SET transcript=NULL WHERE transcript IS NOT NULL AND created_at<?", (cutoff,))
    stats["purged"] = cur.rowcount
    return stats


async def run_forever(interval: float = 2.0):
    while True:
        try:
            con = db.connect()
            try:
                tick(con)
            finally:
                con.close()
        except Exception:  # keep the loop alive; errors are logged, never swallowed silently
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval)
