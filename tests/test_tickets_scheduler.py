from datetime import timedelta

import pytest

from app import db
from app.config import settings
from app.core import scheduler, tickets
from app.core.validators import clean


def village(con, name="Khed Shivapur"):
    return next(v for v in db.villages(con) if v["name"] == name)


def make(con, caller="h1", **kw):
    r = clean({"village": "शिवापूर", "source_type": "handpump", "fault": "no_water", "duration_days": 3,
               "households_affected": 40, **kw})
    return tickets.create_ticket(con, r, caller, "mr", "test transcript", village(con))


def test_create_and_priority_reason(con):
    tid, ref = make(con)
    t = tickets.get(con, tid)
    assert t["state"] == "NEW" and t["priority"] == 2 and "outage 3 days" in t["priority_reason"]
    assert len(ref) == 5 and ref.isdigit()
    assert con.execute("SELECT COUNT(*) FROM sms_log").fetchone()[0] == 2


def test_repeat_report_raises_priority(con):
    make(con, duration_days=1, households_affected=5)
    tid, _ = make(con, caller="h2", duration_days=1, households_affected=5)
    assert tickets.get(con, tid)["priority"] == 2
    assert "repeat" in tickets.get(con, tid)["priority_reason"]


def test_fix_claimed_never_closes(con):
    tid, _ = make(con)
    tickets.ack(con, tid)
    tickets.fix_claimed(con, tid, note="replaced washer")
    t = tickets.get(con, tid)
    assert t["state"] == "FIX_CLAIMED" and t["verified_at"] is None and "washer" in t["notes"]


def test_illegal_transitions_rejected(con):
    tid, _ = make(con)
    with pytest.raises(tickets.TransitionError):
        tickets.record_verification(con, tid, "yes")          # cannot verify a NEW ticket
    tickets.ack(con, tid)
    with pytest.raises(tickets.TransitionError):
        tickets.ack(con, tid)


def test_verify_yes(con):
    tid, _ = make(con)
    tickets.fix_claimed(con, tid)                              # auto-acks NEW
    tickets.record_verification(con, tid, "yes")
    t = tickets.get(con, tid)
    assert t["state"] == "VERIFIED" and t["verified_at"]
    m = tickets.metrics(con)
    assert m["false_closure"] == {"reopened": 0, "answered": 1, "rate": 0.0}


def test_verify_no_reopens_and_raises_priority(con):
    tid, _ = make(con)
    tickets.fix_claimed(con, tid)
    tickets.record_verification(con, tid, "no")
    t = tickets.get(con, tid)
    assert t["state"] == "ACKED" and t["reopened_count"] == 1
    assert t["priority"] == 1 and t["previous_priority"] == 2 and "reopened 1x" in t["priority_reason"]
    events = [e["to_state"] for e in tickets.detail(con, tid)["events"] if e["event"] == "state"]
    assert events[-2:] == ["REOPENED", "ACKED"]
    m = tickets.metrics(con)
    assert m["false_closure"] == {"reopened": 1, "answered": 1, "rate": 1.0}
    tickets.fix_claimed(con, tid)
    tickets.record_verification(con, tid, "yes")
    assert tickets.get(con, tid)["state"] == "VERIFIED"
    assert tickets.metrics(con)["false_closure"]["rate"] == 1.0   # reopened at least once still counts


def test_scheduler_queues_verification_then_unverified(con):
    settings.DEMO_VERIFY_RETRY_SEC = 0
    tid, _ = make(con, caller="dev-hash")
    tickets.fix_claimed(con, tid)
    now = db.now() + timedelta(seconds=1)
    for attempt in range(1, 4):
        s = scheduler.tick(con, now)
        assert s["queued"] == 1
        assert tickets.get(con, tid)["verify_attempts"] == attempt
        row = con.execute("SELECT * FROM outbox WHERE ticket_id=? AND delivered=0", (tid,)).fetchone()
        assert row["device_hash"] == "dev-hash" and row["kind"] == "verification"
        tickets.record_verification(con, tid, "none")          # no answer
        now += timedelta(seconds=1)
    s = scheduler.tick(con, now)
    assert s["unverified"] == 1 and tickets.get(con, tid)["state"] == "UNVERIFIED"


def test_quiet_hours_defer_when_not_demo(con):
    settings.DEMO_IGNORE_QUIET_HOURS = False
    tid, _ = make(con)
    tickets.fix_claimed(con, tid)
    from datetime import datetime, timezone
    late = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)   # 22:30 IST
    con.execute("UPDATE tickets SET next_verify_at=? WHERE id=?", (db.ts(late - timedelta(minutes=1)), tid))
    assert scheduler.in_quiet_hours(late)
    s = scheduler.tick(con, late)
    assert s["deferred"] == 1 and s["queued"] == 0
    nv = db.parse_ts(tickets.get(con, tid)["next_verify_at"])
    assert scheduler._local(nv).strftime("%H:%M") == "07:00"
    assert not scheduler.in_quiet_hours(datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc))   # 11:30 IST


def test_sla_escalation(con):
    tid, _ = make(con, duration_days=1, households_affected=5)   # P3, SLA 72 h
    t0 = db.parse_ts(tickets.get(con, tid)["created_at"])
    assert scheduler.tick(con, t0 + timedelta(hours=71))["escalated"] == 0
    assert scheduler.tick(con, t0 + timedelta(hours=73))["escalated"] == 1
    t = tickets.get(con, tid)
    assert t["priority"] == 2 and t["escalated_count"] == 1 and "SLA missed" in t["priority_reason"]
    assert scheduler.tick(con, t0 + timedelta(hours=74))["escalated"] == 0    # next window starts now


def test_retention_purges_old_transcripts(con):
    tid, _ = make(con)
    con.execute("UPDATE reports SET created_at=?", (db.ts(db.now() - timedelta(days=200)),))
    assert scheduler.tick(con)["purged"] == 1
    assert con.execute("SELECT transcript FROM reports").fetchone()[0] is None


def test_list_tickets_hides_caller_hash(con):
    make(con)
    assert all("caller_hash" not in t for t in tickets.list_tickets(con))
