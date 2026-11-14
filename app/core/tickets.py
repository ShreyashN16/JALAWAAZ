"""Ticket lifecycle and metrics. All transitions are transactional and audited.

NEW -> ACKED -> FIX_CLAIMED -> VERIFIED | REOPENED (-> ACKED, priority up) | UNVERIFIED
An engineer's "fix claimed" never closes a ticket: only the original caller's "yes" does.
"""
from __future__ import annotations

import json
import secrets
import statistics
from datetime import timedelta

from .. import db
from ..config import settings
from .priority import compute_priority
from .sms import send_sms


class TransitionError(Exception):
    pass


def _event(con, tid, actor, event, from_state=None, to_state=None, from_p=None, to_p=None, detail=None):
    con.execute("INSERT INTO ticket_events(ticket_id, at, actor, event, from_state, to_state, from_priority,"
                " to_priority, detail) VALUES (?,?,?,?,?,?,?,?,?)",
                (tid, db.ts(), actor, event, from_state, to_state, from_p, to_p, detail))


def _new_ref(con) -> str:
    while True:
        ref = str(secrets.randbelow(90000) + 10000)            # 5 digits, spoken one by one
        if not con.execute("SELECT 1 FROM tickets WHERE ref=?", (ref,)).fetchone():
            return ref


def is_repeat(con, village_id, village_text, source_type, window_days, exclude_report_id=None) -> bool:
    """Another report on the same village and source type within the window?"""
    since = db.ts(db.now() - timedelta(days=window_days))
    ex = exclude_report_id or -1
    if village_id:
        q = "SELECT COUNT(*) FROM reports WHERE village_id=? AND source_type IS ? AND created_at>=? AND id<>?"
        return con.execute(q, (village_id, source_type, since, ex)).fetchone()[0] > 0
    if village_text:
        q = ("SELECT COUNT(*) FROM reports WHERE lower(village_text)=lower(?) AND source_type IS ?"
             " AND created_at>=? AND id<>?")
        return con.execute(q, (village_text, source_type, since, ex)).fetchone()[0] > 0
    return False


def create_ticket(con, report: dict, caller_hash: str, lang: str, transcript: str, village_row: dict | None,
                  extraction_source: str = "rules", needs_review: bool = False, is_synthetic: bool = False,
                  created_at: str | None = None) -> tuple[int, str]:
    cfg = settings.cfg
    vid = village_row["id"] if village_row else None
    with db.tx(con):
        repeat = is_repeat(con, vid, report.get("village"), report.get("source_type"), cfg["priority"]["repeat_window_days"])
        p, reason = compute_priority(report, repeat, 0, cfg)
        at = created_at or db.ts()
        cur = con.execute(
            "INSERT INTO reports(caller_hash, lang, village_id, village_text, village_score, source_type, fault,"
            " duration_days, households, drinking_source, symptoms, smell_colour_taste, transcript, evidence_quote,"
            " extraction_source, needs_review, is_synthetic, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (caller_hash, lang, vid, report.get("village"), report.get("_village_score"), report.get("source_type"),
             report.get("fault"), report.get("duration_days"), report.get("households_affected"),
             None if report.get("drinking_source") is None else int(report["drinking_source"]),
             json.dumps(report.get("health_symptoms") or [], ensure_ascii=False), report.get("smell_colour_taste"),
             transcript, report.get("evidence_quote"), extraction_source, int(needs_review), int(is_synthetic), at))
        ref = _new_ref(con)
        cur = con.execute(
            "INSERT INTO tickets(ref, report_id, caller_hash, lang, priority, priority_reason, created_at, is_synthetic)"
            " VALUES (?,?,?,?,?,?,?,?)", (ref, cur.lastrowid, caller_hash, lang, p, reason, at, int(is_synthetic)))
        tid = cur.lastrowid
        _event(con, tid, "system", "created", None, "NEW", None, p, reason)
    vname = village_row["name"] if village_row else (report.get("village") or "unknown village")
    send_sms("reporter", tid, f"Jal Awaaz ticket {ref} received. We will call to check after the fix.")
    send_sms("engineer", tid, f"P{p} {vname} {report.get('source_type') or ''} {report.get('fault') or ''}, "
                              f"{report.get('households_affected') or '?'} households, {report.get('duration_days') or '?'} days. "
                              f"Reason: {reason}. /engineer#t{tid}")
    return tid, ref


def get(con, tid: int) -> dict:
    r = con.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
    if not r:
        raise TransitionError(f"ticket {tid} not found")
    return dict(r)


def _set_state(con, t: dict, to: str, actor: str, detail: str | None = None, **fields):
    if (t["state"], to) not in db.ALLOWED:
        raise TransitionError(f"cannot move ticket from {t['state']} to {to}")
    cols = ", ".join(["state=?"] + [f"{k}=?" for k in fields])
    con.execute(f"UPDATE tickets SET {cols} WHERE id=?", (to, *fields.values(), t["id"]))
    _event(con, t["id"], actor, "state", t["state"], to, t["priority"], fields.get("priority", t["priority"]), detail)
    t.update(state=to, **fields)


def ack(con, tid: int, actor: str = "engineer") -> dict:
    with db.tx(con):
        t = get(con, tid)
        if t["state"] == "REOPENED":
            _set_state(con, t, "ACKED", actor, "re-acknowledged after reopen", ack_at=db.ts())
        else:
            _set_state(con, t, "ACKED", actor, ack_at=db.ts())
    return t


def verify_delay() -> timedelta:
    if settings.DEMO_MODE:
        return timedelta(seconds=settings.DEMO_VERIFY_DELAY_SEC)
    return timedelta(hours=settings.cfg["calling"]["verify_delay_hours"])


def fix_claimed(con, tid: int, actor: str = "engineer", note: str = "") -> dict:
    with db.tx(con):
        t = get(con, tid)
        if t["state"] in ("NEW", "REOPENED"):
            _set_state(con, t, "ACKED", actor, "auto-acknowledged on fix claim", ack_at=t.get("ack_at") or db.ts())
        _set_state(con, t, "FIX_CLAIMED", actor, note or None, fix_claimed_at=db.ts(), verify_attempts=0,
                   next_verify_at=db.ts(db.now() + verify_delay()))
        if note:
            con.execute("UPDATE tickets SET notes = trim(coalesce(notes,'') || char(10) || ?, char(10) || ' ') WHERE id=?",
                        (f"[{db.ts()}] {note}", tid))
    return t


def add_note(con, tid: int, note: str, actor: str = "engineer") -> None:
    note = (note or "").strip()[:500]
    if not note:
        return
    with db.tx(con):
        get(con, tid)
        con.execute("UPDATE tickets SET notes = trim(coalesce(notes,'') || char(10) || ?, char(10) || ' ') WHERE id=?",
                    (f"[{db.ts()}] {note}", tid))
        _event(con, tid, actor, "note", detail=note)


def _report_for(con, t) -> dict:
    r = dict(con.execute("SELECT * FROM reports WHERE id=?", (t["report_id"],)).fetchone())
    return {"source_type": r["source_type"], "fault": r["fault"], "duration_days": r["duration_days"],
            "households_affected": r["households"], "drinking_source": None if r["drinking_source"] is None else bool(r["drinking_source"]),
            "health_symptoms": json.loads(r["symptoms"] or "[]"), "village": r["village_text"], "_village_id": r["village_id"]}


def record_verification(con, tid: int, result: str, actor: str = "caller") -> dict:
    """result: yes | no | none. Only the original caller reaches this (checked by the API)."""
    if result not in ("yes", "no", "none"):
        raise ValueError(result)
    with db.tx(con):
        t = get(con, tid)
        if t["state"] != "FIX_CLAIMED":
            raise TransitionError(f"ticket {tid} is {t['state']}, not awaiting verification")
        con.execute("INSERT INTO verifications(ticket_id, attempt, result, at) VALUES (?,?,?,?)",
                    (tid, t["verify_attempts"], result, db.ts()))
        if result == "yes":
            _set_state(con, t, "VERIFIED", actor, "caller confirmed water is flowing", verified_at=db.ts(), next_verify_at=None)
        elif result == "no":
            _set_state(con, t, "REOPENED", actor, "caller reports the fault persists", reopened_at=db.ts(),
                       reopened_count=t["reopened_count"] + 1, next_verify_at=None)
            r = _report_for(con, t)
            repeat = is_repeat(con, r["_village_id"], r["village"], r["source_type"],
                               settings.cfg["priority"]["repeat_window_days"], exclude_report_id=t["report_id"])
            p, reason = compute_priority(r, repeat, t["reopened_count"], settings.cfg)
            p = min(p, t["priority"])                       # never lower urgency on reopen
            con.execute("UPDATE tickets SET previous_priority=?, priority=?, priority_reason=? WHERE id=?",
                        (t["priority"], p, reason, tid))
            _event(con, tid, "system", "priority", from_p=t["priority"], to_p=p, detail=reason)
            t.update(previous_priority=t["priority"], priority=p, priority_reason=reason)
            _set_state(con, t, "ACKED", "system", "returned to engineer queue")
        else:
            _event(con, tid, actor, "verify_no_answer", detail=f"attempt {t['verify_attempts']}")
    if result == "no":
        send_sms("engineer", tid, f"REOPENED P{t['priority']}: caller says ticket {t['ref']} is still broken.")
    return t


# ------------------------------------------------------------------ read models
def list_tickets(con, include_synthetic: bool = True) -> list[dict]:
    q = """SELECT t.*, r.source_type, r.fault, r.duration_days, r.households, r.drinking_source, r.symptoms,
                  r.village_text, r.transcript, r.evidence_quote, r.extraction_source, r.needs_review, r.lang AS report_lang,
                  r.smell_colour_taste, v.name AS village, v.taluka, v.district, v.lat, v.lon, v.coord_source,
                  v.coord_quality
           FROM tickets t JOIN reports r ON r.id=t.report_id LEFT JOIN villages v ON v.id=r.village_id"""
    if not include_synthetic:
        q += " WHERE t.is_synthetic=0"
    q += " ORDER BY t.priority ASC, t.created_at ASC"
    out = []
    for row in con.execute(q):
        d = dict(row)
        d["symptoms"] = json.loads(d["symptoms"] or "[]")
        d["village"] = d["village"] or d["village_text"] or "unknown"
        d.pop("caller_hash", None)                         # never sent to any page
        out.append(d)
    return out


def detail(con, tid: int) -> dict:
    t = next((x for x in list_tickets(con) if x["id"] == tid), None)
    if not t:
        raise TransitionError(f"ticket {tid} not found")
    t["events"] = [dict(r) for r in con.execute("SELECT * FROM ticket_events WHERE ticket_id=? ORDER BY id", (tid,))]
    t["verifications"] = [dict(r) for r in con.execute("SELECT * FROM verifications WHERE ticket_id=? ORDER BY id", (tid,))]
    return t


def _minutes(a, b):
    da, dbb = db.parse_ts(a), db.parse_ts(b)
    return (dbb - da).total_seconds() / 60 if da and dbb else None


def metrics(con, include_synthetic: bool = True) -> dict:
    where = "" if include_synthetic else " WHERE is_synthetic=0"
    rows = [dict(r) for r in con.execute("SELECT * FROM tickets" + where)]
    by = {s: sum(1 for r in rows if r["state"] == s) for s in db.STATES}
    open_ = sum(1 for r in rows if r["state"] not in ("VERIFIED", "UNVERIFIED"))
    ack_m = [m for r in rows if (m := _minutes(r["created_at"], r["ack_at"])) is not None]
    fix_v = [m for r in rows if (m := _minutes(r["fix_claimed_at"], r["verified_at"])) is not None]
    ids = [r["id"] for r in rows]
    answered = reopened_once = 0
    if ids:
        qmarks = ",".join("?" * len(ids))
        answered = con.execute(f"SELECT COUNT(DISTINCT ticket_id) FROM verifications WHERE result IN ('yes','no')"
                               f" AND ticket_id IN ({qmarks})", ids).fetchone()[0]
        reopened_once = con.execute(f"SELECT COUNT(*) FROM tickets WHERE reopened_count>0 AND id IN ({qmarks})", ids).fetchone()[0]
    window = settings.cfg["priority"]["repeat_window_days"]
    since = db.ts(db.now() - timedelta(days=window))
    syn = "" if include_synthetic else " AND r.is_synthetic=0"
    repeats = [dict(r) for r in con.execute(
        "SELECT coalesce(v.name, r.village_text) AS village, r.source_type, COUNT(*) AS reports, v.lat, v.lon"
        " FROM reports r LEFT JOIN villages v ON v.id=r.village_id WHERE r.created_at>=? AND r.id IN (SELECT report_id FROM tickets)"
        + syn + " GROUP BY coalesce(v.name, r.village_text), r.source_type HAVING COUNT(*)>=2 ORDER BY reports DESC", (since,))]
    return {
        "total": len(rows), "open": open_, "by_state": by,
        "p1_open": sum(1 for r in rows if r["priority"] == 1 and r["state"] not in ("VERIFIED", "UNVERIFIED")),
        "median_ack_min": round(statistics.median(ack_m), 1) if ack_m else None, "n_ack": len(ack_m),
        "median_fix_to_verified_min": round(statistics.median(fix_v), 1) if fix_v else None, "n_fix_verified": len(fix_v),
        "false_closure": {"reopened": reopened_once, "answered": answered,
                          "rate": round(reopened_once / answered, 3) if answered else None},
        "repeat_sources": repeats, "synthetic_tickets": sum(1 for r in rows if r["is_synthetic"]),
    }


# ------------------------------------------------------------------ dashboard read models
def sla_due(t: dict) -> str | None:
    """When an open (NEW / ACKED) ticket escalates if nobody acts. Same rule as the scheduler."""
    if t.get("state") not in ("NEW", "ACKED"):
        return None
    base = db.parse_ts(t.get("last_escalated_at") or t.get("created_at"))
    if not base:
        return None
    return db.ts(base + timedelta(hours=float(settings.cfg["sla_hours"][str(t["priority"])])))


def with_sla(rows: list[dict]) -> list[dict]:
    now = db.now()
    for t in rows:
        due = sla_due(t)
        t["sla_due_at"] = due
        t["sla_overdue"] = bool(due and db.parse_ts(due) < now)
    return rows


def _local_date(ts: str | None) -> str | None:
    d = db.parse_ts(ts)
    if not d:
        return None
    from datetime import timezone as _tz
    return d.astimezone(_tz(timedelta(minutes=settings.cfg["calling"]["tz_offset_minutes"]))).strftime("%Y-%m-%d")


def insights(con, include_synthetic: bool = True, days: int = 14) -> dict:
    """Trends and breakdowns, all computed from the tickets table (no estimates)."""
    rows = with_sla(list_tickets(con, include_synthetic))
    today = db.parse_ts(db.ts())
    from datetime import timezone as _tz
    local_today = today.astimezone(_tz(timedelta(minutes=settings.cfg["calling"]["tz_offset_minutes"]))).date()
    dates = [(local_today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    series = {d: {"date": d, "reported": 0, "verified": 0, "reopened": 0} for d in dates}
    ids = [r["id"] for r in rows]
    for r in rows:
        d = _local_date(r["created_at"])
        if d in series:
            series[d]["reported"] += 1
        d = _local_date(r["verified_at"])
        if d in series:
            series[d]["verified"] += 1
    if ids:
        q = ",".join("?" * len(ids))
        for e in con.execute(f"SELECT at FROM ticket_events WHERE event='state' AND to_state='REOPENED'"
                             f" AND ticket_id IN ({q})", ids):
            d = _local_date(e["at"])
            if d in series:
                series[d]["reopened"] += 1
    by_fault, by_source = {}, {}
    villages: dict[str, dict] = {}
    for r in rows:
        by_fault[r["fault"] or "unknown"] = by_fault.get(r["fault"] or "unknown", 0) + 1
        by_source[r["source_type"] or "unknown"] = by_source.get(r["source_type"] or "unknown", 0) + 1
        v = villages.setdefault(r["village"], {"village": r["village"], "total": 0, "open": 0, "reopened": 0,
                                               "verified": 0, "lat": r["lat"], "lon": r["lon"],
                                               "coord_quality": r.get("coord_quality")})
        v["total"] += 1
        v["open"] += r["state"] not in ("VERIFIED", "UNVERIFIED")
        v["verified"] += r["state"] == "VERIFIED"
        v["reopened"] += 1 if r["reopened_count"] else 0
    open_rows = [r for r in rows if r["state"] not in ("VERIFIED", "UNVERIFIED")]
    return {
        "daily": list(series.values()),
        "by_fault": dict(sorted(by_fault.items(), key=lambda kv: -kv[1])),
        "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        "by_village": sorted(villages.values(), key=lambda v: (-v["open"], -v["total"])),
        "sla": {"open_with_sla": sum(1 for r in open_rows if r["sla_due_at"]),
                "overdue": [{"id": r["id"], "ref": r["ref"], "village": r["village"], "priority": r["priority"],
                             "state": r["state"], "due": r["sla_due_at"]} for r in open_rows if r["sla_overdue"]],
                "awaiting_caller": sum(1 for r in rows if r["state"] == "FIX_CLAIMED")},
        "by_priority_open": {p: sum(1 for r in open_rows if r["priority"] == p) for p in (1, 2, 3)},
    }


def activity(con, include_synthetic: bool = True, limit: int = 40) -> list[dict]:
    """Recent audited events with ticket ref and village, newest first. No caller data."""
    q = ("SELECT e.id, e.ticket_id, e.at, e.actor, e.event, e.from_state, e.to_state, e.from_priority, e.to_priority,"
         " e.detail, t.ref, t.is_synthetic, coalesce(v.name, r.village_text) AS village"
         " FROM ticket_events e JOIN tickets t ON t.id=e.ticket_id JOIN reports r ON r.id=t.report_id"
         " LEFT JOIN villages v ON v.id=r.village_id")
    if not include_synthetic:
        q += " WHERE t.is_synthetic=0"
    q += " ORDER BY e.at DESC, e.id DESC LIMIT ?"
    return [dict(r) for r in con.execute(q, (limit,))]


EXPORT_COLUMNS = ["ref", "state", "priority", "priority_reason", "village", "taluka", "district", "source_type", "fault",
                  "duration_days", "households", "drinking_source", "created_at", "ack_at", "fix_claimed_at",
                  "verified_at", "reopened_count", "verify_attempts", "escalated_count", "extraction_source",
                  "is_synthetic"]
