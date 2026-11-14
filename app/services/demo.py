"""Clearly labelled SYNTHETIC demo tickets, so the dashboard is not empty on first open.

Every row is flagged is_synthetic=1, carries a "synthetic" badge in every view, is excluded from the
public view when the toggle is off, and is removed by clear(). Real tickets are never touched.
The lifecycles cover every path: new, acknowledged, fix claimed, verified, reopened after a false
closure, reopened then verified, no answer (unverified), and a repeat report on the same source.
"""
from __future__ import annotations

from datetime import timedelta

from .. import db
from ..core import tickets
from ..core.validators import clean
from ..security import hash_id

# (village, report fields, days ago, lifecycle, language)
CASES = [
    ("Donje", dict(source_type="tap", fault="contamination", drinking_source=True, health_symptoms=["diarrhoea"],
                   households_affected=60, duration_days=2), 12.5, "verified", "mr"),
    ("Khed Shivapur", dict(source_type="borewell", fault="power", duration_days=4, households_affected=120), 11.0, "reopened", "mr"),
    ("Kudje", dict(source_type="handpump", fault="broken_part", duration_days=1, households_affected=15), 10.2, "verified", "hi"),
    ("Khadakwasla", dict(source_type="tap", fault="low_pressure", duration_days=5, households_affected=80), 9.0, "reopened_verified", "mr"),
    ("Kondhanpur", dict(source_type="tank", fault="leakage", duration_days=6, households_affected=30), 8.1, "unverified", "mr"),
    ("Gorhe Budruk", dict(source_type="well", fault="no_water", duration_days=3, households_affected=45), 7.0, "verified", "hinglish"),
    ("Donje", dict(source_type="tap", fault="no_water", duration_days=1, households_affected=40), 5.5, "claimed", "mr"),
    ("Sangrun", dict(source_type="well", fault="low_pressure", duration_days=2, households_affected=25), 4.2, "acked", "hi"),
    ("Kudje", dict(source_type="borewell", fault="no_water", duration_days=2, households_affected=110), 3.0, "verified", "mr"),
    ("Khed Shivapur", dict(source_type="handpump", fault="no_water", duration_days=2, households_affected=35), 2.1, "acked", "mr"),
    ("Malkhed", dict(source_type="tanker", fault="no_water", duration_days=3, households_affected=50), 1.4, "new", "hi"),
    ("Khadakwasla", dict(source_type="tap", fault="contamination", drinking_source=True, households_affected=20), 0.9, "claimed", "mr"),
    ("Kondhanpur", dict(source_type="handpump", fault="broken_part", duration_days=1, households_affected=12), 0.35, "new", "hinglish"),
    ("Gorhe Budruk", dict(source_type="tank", fault="power", duration_days=1, households_affected=70), 0.12, "new", "mr"),
]


def _at(days_ago: float, plus_hours: float = 0) -> str:
    return db.ts(db.now() - timedelta(days=days_ago) + timedelta(hours=plus_hours))


def seed(con) -> int:
    vs = {v["name"]: v for v in db.villages(con)}
    n = 0
    for i, (vname, fields, days, life, lang) in enumerate(CASES):
        r = clean({"village": vname, **fields})
        tid, _ = tickets.create_ticket(con, r, hash_id(f"synthetic-{i}"), lang, "[synthetic demo report]", vs.get(vname),
                                       extraction_source="synthetic", is_synthetic=True, created_at=_at(days))
        con.execute("UPDATE reports SET is_synthetic=1 WHERE id=(SELECT report_id FROM tickets WHERE id=?)", (tid,))
        con.execute("UPDATE ticket_events SET at=? WHERE ticket_id=? AND event='created'", (_at(days), tid))
        n += 1
        if life == "new":
            continue
        tickets.ack(con, tid, actor="synthetic")
        con.execute("UPDATE tickets SET ack_at=? WHERE id=?", (_at(days, 1.5), tid))
        if life == "acked":
            continue
        tickets.fix_claimed(con, tid, actor="synthetic", note="synthetic demo fix")
        con.execute("UPDATE tickets SET fix_claimed_at=?, next_verify_at=NULL WHERE id=?", (_at(days, 20), tid))
        if life == "claimed":
            continue
        if life == "unverified":
            with db.tx(con):
                t = tickets.get(con, tid)
                for k in range(3):
                    con.execute("INSERT INTO verifications(ticket_id, attempt, result, at) VALUES (?,?,?,?)",
                                (tid, k + 1, "none", _at(days, 26 + 3 * k)))
                tickets._set_state(con, t, "UNVERIFIED", "synthetic", "no answer after 3 verification attempts",
                                   unverified_at=_at(days, 34), verify_attempts=3)
            continue
        first = "no" if life in ("reopened", "reopened_verified") else "yes"
        tickets.record_verification(con, tid, first, actor="synthetic")
        if first == "yes":
            con.execute("UPDATE tickets SET verified_at=? WHERE id=?", (_at(days, 27), tid))
            continue
        con.execute("UPDATE tickets SET reopened_at=? WHERE id=?", (_at(days, 27), tid))
        if life == "reopened_verified":
            tickets.fix_claimed(con, tid, actor="synthetic", note="synthetic second fix")
            con.execute("UPDATE tickets SET fix_claimed_at=?, next_verify_at=NULL WHERE id=?", (_at(days, 40), tid))
            tickets.record_verification(con, tid, "yes", actor="synthetic")
            con.execute("UPDATE tickets SET verified_at=? WHERE id=?", (_at(days, 46), tid))
    return n


def clear(con) -> int:
    ids = [r[0] for r in con.execute("SELECT id FROM tickets WHERE is_synthetic=1")]
    with db.tx(con):
        for tid in ids:
            for tbl in ("ticket_events", "verifications", "outbox", "sms_log"):
                con.execute(f"DELETE FROM {tbl} WHERE ticket_id=?", (tid,))
            con.execute("UPDATE calls SET ticket_id=NULL WHERE ticket_id=?", (tid,))
        con.execute("DELETE FROM tickets WHERE is_synthetic=1")
        con.execute("DELETE FROM reports WHERE is_synthetic=1")
    return len(ids)


def count(con) -> int:
    return con.execute("SELECT COUNT(*) FROM tickets WHERE is_synthetic=1").fetchone()[0]
