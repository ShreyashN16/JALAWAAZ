"""SQLite schema and helpers. Parameterised queries only.

Ticket state transitions are enforced twice: in Python (core/tickets.py) and by a
database trigger, so even a buggy caller cannot write an illegal transition.
"""
from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, settings

STATES = ("NEW", "ACKED", "FIX_CLAIMED", "VERIFIED", "REOPENED", "UNVERIFIED")
ALLOWED = {
    ("NEW", "ACKED"),
    ("ACKED", "FIX_CLAIMED"),
    ("FIX_CLAIMED", "VERIFIED"),
    ("FIX_CLAIMED", "REOPENED"),
    ("FIX_CLAIMED", "UNVERIFIED"),
    ("REOPENED", "ACKED"),
}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS villages(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, variants TEXT DEFAULT '',
  taluka TEXT, district TEXT, lat REAL, lon REAL, coord_source TEXT, coord_quality TEXT);

CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, village_id INTEGER REFERENCES villages(id),
  type TEXT, lat REAL, lon REAL);

CREATE TABLE IF NOT EXISTS reports(
  id INTEGER PRIMARY KEY,
  caller_hash TEXT NOT NULL, lang TEXT, village_id INTEGER REFERENCES villages(id),
  village_text TEXT, village_score REAL, source_id INTEGER REFERENCES sources(id),
  source_type TEXT, fault TEXT, duration_days INTEGER, households INTEGER,
  drinking_source INTEGER, symptoms TEXT, smell_colour_taste TEXT,
  transcript TEXT, evidence_quote TEXT,
  extraction_source TEXT, needs_review INTEGER DEFAULT 0,
  is_synthetic INTEGER DEFAULT 0, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS tickets(
  id INTEGER PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
  report_id INTEGER NOT NULL REFERENCES reports(id),
  caller_hash TEXT NOT NULL, lang TEXT,
  state TEXT NOT NULL DEFAULT 'NEW'
     CHECK (state IN ('NEW','ACKED','FIX_CLAIMED','VERIFIED','REOPENED','UNVERIFIED')),
  priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 3),
  previous_priority INTEGER, priority_reason TEXT NOT NULL,
  created_at TEXT NOT NULL, ack_at TEXT, fix_claimed_at TEXT, verified_at TEXT,
  reopened_at TEXT, unverified_at TEXT, last_escalated_at TEXT,
  reopened_count INTEGER NOT NULL DEFAULT 0, verify_attempts INTEGER NOT NULL DEFAULT 0,
  next_verify_at TEXT, escalated_count INTEGER NOT NULL DEFAULT 0,
  notes TEXT DEFAULT '', is_synthetic INTEGER DEFAULT 0);

CREATE TRIGGER IF NOT EXISTS ticket_state_guard
BEFORE UPDATE OF state ON tickets
WHEN NEW.state <> OLD.state AND (OLD.state || '>' || NEW.state) NOT IN (
  'NEW>ACKED','ACKED>FIX_CLAIMED','FIX_CLAIMED>VERIFIED','FIX_CLAIMED>REOPENED',
  'FIX_CLAIMED>UNVERIFIED','REOPENED>ACKED')
BEGIN
  SELECT RAISE(ABORT, 'illegal ticket state transition');
END;

CREATE TABLE IF NOT EXISTS ticket_events(           -- audit trail and escalation history
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
  at TEXT NOT NULL, actor TEXT NOT NULL, event TEXT NOT NULL,
  from_state TEXT, to_state TEXT, from_priority INTEGER, to_priority INTEGER, detail TEXT);

CREATE TABLE IF NOT EXISTS verifications(
  id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
  attempt INTEGER, result TEXT CHECK (result IN ('yes','no','none')), at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS calls(
  id INTEGER PRIMARY KEY, session_id TEXT, direction TEXT, kind TEXT, caller_hash TEXT, lang TEXT,
  turns INTEGER DEFAULT 0, duration_s REAL, outcome TEXT, ticket_id INTEGER,
  stt_ms REAL DEFAULT 0, llm_ms REAL DEFAULT 0, tts_ms REAL DEFAULT 0, total_ms REAL DEFAULT 0,
  providers TEXT, created_at TEXT NOT NULL, ended_at TEXT, telephone INTEGER DEFAULT 0, tts_ttfb_ms REAL);

CREATE TABLE IF NOT EXISTS api_calls(              -- evidence of real Gnani use; never audio or transcripts
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, service TEXT, model TEXT, status INTEGER,
  ok INTEGER, ms REAL, attempt INTEGER, error_kind TEXT, request_id TEXT, cached INTEGER DEFAULT 0,
  ttfb_ms REAL);

CREATE TABLE IF NOT EXISTS outbox(                  -- simulated callbacks and verification calls
  id INTEGER PRIMARY KEY, device_hash TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('callback','verification')),
  ticket_id INTEGER, ready_at TEXT NOT NULL, delivered INTEGER DEFAULT 0, delivered_at TEXT);

CREATE TABLE IF NOT EXISTS sms_log(
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, to_role TEXT, ticket_id INTEGER, body TEXT);

CREATE INDEX IF NOT EXISTS ix_tickets_state ON tickets(state);
CREATE INDEX IF NOT EXISTS ix_outbox_dev ON outbox(device_hash, delivered);
CREATE INDEX IF NOT EXISTS ix_reports_village ON reports(village_id, source_type, created_at);
CREATE INDEX IF NOT EXISTS ix_events_ticket ON ticket_events(ticket_id, id);
CREATE INDEX IF NOT EXISTS ix_api_calls_service ON api_calls(service, ok);
CREATE INDEX IF NOT EXISTS ix_tickets_caller ON tickets(caller_hash);
"""

# Columns added after v1. init_db() adds any that an older database is missing, so an existing
# jalawaaz.db keeps its tickets and upgrades in place (no data is dropped).
MIGRATIONS = {
    "villages": {"coord_source": "TEXT", "coord_quality": "TEXT"},
    "api_calls": {"request_id": "TEXT", "cached": "INTEGER DEFAULT 0", "ttfb_ms": "REAL"},
    "calls": {"telephone": "INTEGER DEFAULT 0", "tts_ttfb_ms": "REAL"},
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def ts(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def connect(path: str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(path or settings.DB_PATH, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextmanager
def tx(con: sqlite3.Connection):
    """Write transaction (BEGIN IMMEDIATE ... COMMIT / ROLLBACK)."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def _migrate(con: sqlite3.Connection) -> list[str]:
    added = []
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols.items():
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                added.append(f"{table}.{col}")
    return added


def init_db(path: str | None = None, seed_villages: bool = True) -> None:
    con = connect(path)
    try:
        con.executescript(SCHEMA)        # IF NOT EXISTS: never touches existing tables or rows
        _migrate(con)                    # then add columns an older database is missing
        if seed_villages:
            sync_villages(con, ROOT / "data" / "villages.csv")
    finally:
        con.close()


def sync_villages(con: sqlite3.Connection, csv_path: Path) -> int:
    """Insert new gazetteer rows and refresh coordinates/variants of existing ones (ids never change,
    so old reports keep pointing at the same village)."""
    n = 0
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["name"].strip()
            lat = float(row["lat"]) if row.get("lat") else None
            lon = float(row["lon"]) if row.get("lon") else None
            vals = (row.get("variants", ""), row.get("taluka"), row.get("district"), lat, lon,
                    row.get("coord_source") or None, row.get("coord_quality") or None)
            cur = con.execute("UPDATE villages SET variants=?, taluka=?, district=?, lat=?, lon=?, coord_source=?,"
                              " coord_quality=? WHERE name=?", (*vals, name))
            if cur.rowcount == 0:
                con.execute("INSERT INTO villages(variants, taluka, district, lat, lon, coord_source, coord_quality, name)"
                            " VALUES (?,?,?,?,?,?,?,?)", (*vals, name))
            n += 1
    return n


def load_villages(con: sqlite3.Connection, csv_path: Path) -> int:
    """Kept for older scripts: same as sync_villages."""
    return sync_villages(con, csv_path)


def villages(con: sqlite3.Connection) -> list[dict]:
    out = []
    for r in con.execute("SELECT * FROM villages ORDER BY name"):
        d = dict(r)
        d["variants"] = [v.strip() for v in (d.get("variants") or "").split("|") if v.strip()]
        out.append(d)
    return out


def log_api_call(service: str, model: str, status: int, ok: bool, ms: float, attempt: int,
                 error_kind: str | None = None, request_id: str | None = None, cached: bool = False,
                 ttfb_ms: float | None = None) -> None:
    """Evidence of genuine Gnani/Evon use: service, model, status, latency. Never audio or text."""
    con = connect()
    try:
        con.execute(
            "INSERT INTO api_calls(at, service, model, status, ok, ms, attempt, error_kind, request_id, cached, ttfb_ms)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts(), service, model, status, int(ok), round(ms, 1), attempt, error_kind, request_id, int(cached),
             None if ttfb_ms is None else round(ttfb_ms, 1)),
        )
    finally:
        con.close()
