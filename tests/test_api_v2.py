"""Endpoints added in v2: streamed speech, villager status, map data, dashboard insights, exports,
evaluation, system report, demo data controls and the API reference."""
import csv
import io

import pytest
from starlette.routing import Mount
from starlette.testclient import TestClient

from app import db, openapi
from app.gnani import providers
from app.gnani.base import TTS, TTSResult

DEV = "device-v2-abcdef"


class FakeTimbre(TTS):
    name = "timbre"

    def __init__(self):
        self.spoken = []

    def mime_for(self, telephone=False):
        return "audio/wav" if telephone else "audio/mpeg"

    async def speak(self, text, lang, cache=False, telephone=False):
        self.spoken.append(("speak", text, cache))
        return TTSResult(b"ID3" + text.encode()[:50] + b"\x00" * 200, self.mime_for(telephone), 12.0, cached=False)

    async def stream(self, text, lang, telephone=False, stats=None):
        self.spoken.append(("stream", text, False))
        if stats is not None:
            stats.update(mode="stream", ttfb_ms=5.0, ms=20.0)
        for part in (b"ID3", b"\xff\xfb" * 50, text.encode()[:20]):
            yield part


@pytest.fixture
def tts():
    return FakeTimbre()


@pytest.fixture
def client(tts):
    providers.set_providers(stt=None, tts=tts, llm=None)
    from app.main import app, limiter
    limiter.hits.clear()
    with TestClient(app) as c:
        yield c
    providers.set_providers()


def login(c, pin):
    return c.post("/api/login", json={"pin": pin}).json()["csrf"]


def say(c, sid, text):
    r = c.post("/api/turn", data={"session_id": sid, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def make_ticket(c, device=DEV):
    s = c.post("/api/session", json={"device": device, "mode": "report", "lang": "mr"}).json()
    say(c, s["session_id"], "Shivapur madhe handpump 3 divas band aahe, 40 ghar")
    say(c, s["session_id"], "nahi")
    last = say(c, s["session_id"], "ho")
    assert last["outcome"] == "ticket"
    return last


def test_greeting_returns_audio_url_and_static_prompt_is_cached(client, tts):
    s = client.post("/api/session", json={"device": DEV, "mode": "report", "lang": "mr"}).json()
    assert s["audio_url"].startswith("/api/speech/") and s["browser_voice"] is False
    r = client.get(s["audio_url"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/mpeg")
    assert tts.spoken[-1][0] == "speak" and tts.spoken[-1][2] is True        # greeting is static: disk cache path
    again = client.get(s["audio_url"])                                       # replay: memory, no new synthesis
    assert again.content == r.content and len(tts.spoken) == 1


def test_dynamic_reply_streams_and_speech_has_number_words(client, tts):
    s = client.post("/api/session", json={"device": DEV, "mode": "report", "lang": "mr"}).json()
    j = say(client, s["session_id"], "Shivapur madhe handpump 3 divas band aahe, 40 ghar")
    j = say(client, s["session_id"], "nahi")                                  # read-back follows
    assert "बरोबर" in j["reply_text"] and "चाळीस" in j["speech_text"]
    r = client.get(j["audio_url"])
    assert r.status_code == 200 and r.content.startswith(b"ID3")
    assert tts.spoken[-1][0] == "stream" and "चाळीस" in tts.spoken[-1][1]


def test_speech_failure_returns_503_json(client, tts):
    async def broken(*a, **k):
        from app.gnani.client import GnaniError
        raise GnaniError(402, "NO_CREDIT", "none")
        yield b""
    async def broken_speak(*a, **k):
        from app.gnani.client import GnaniError
        raise GnaniError(402, "NO_CREDIT", "none")
    tts.stream, tts.speak = broken, broken_speak
    s = client.post("/api/session", json={"device": DEV, "mode": "report", "lang": "hi"}).json()
    j = say(client, s["session_id"], "Donje gaon ka handpump kharab hai")
    r = client.get(j["audio_url"])
    assert r.status_code == 503 and r.json()["error"]["code"] == "tts_failed"


def test_unknown_speech_id_is_404(client):
    assert client.get("/api/speech/nope").status_code == 404


def test_browser_voice_when_no_tts():
    providers.set_providers(stt=None, tts=None, llm=None)
    from app.main import app
    with TestClient(app) as c:
        s = c.post("/api/session", json={"device": DEV, "mode": "report", "lang": "mr"}).json()
        assert s["audio_url"] is None and s["browser_voice"] is True and s["speech_text"]
    providers.set_providers()


def test_my_tickets_only_shows_this_device(client):
    last = make_ticket(client)
    make_ticket(client, device="someone-else-1234")
    mine = client.get("/api/my-tickets", params={"device": DEV}).json()
    assert [t["ref"] for t in mine] == [last["ticket_ref"]] and mine[0]["village"] == "Khed Shivapur"
    assert "caller_hash" not in mine[0]


def test_villages_have_sources_for_every_coordinate(client):
    vs = client.get("/api/villages").json()
    assert len(vs) >= 9
    for v in vs:
        if v["lat"] is not None:
            assert v["coord_source"] and v["coord_quality"] in ("cited", "approximate")


def test_metrics_include_insights_and_sla(client):
    make_ticket(client)
    login(client, "1357")
    m = client.get("/api/metrics").json()
    ins = m["insights"]
    assert len(ins["daily"]) == 14 and sum(d["reported"] for d in ins["daily"]) == 1
    assert ins["by_fault"] and ins["by_village"][0]["village"] == "Khed Shivapur"
    t = client.get("/api/tickets").json()[0]
    assert t["sla_due_at"] and t["sla_overdue"] is False
    assert m["loop"]["tickets"] == 1


def test_activity_feed_and_detail_include_sms(client):
    last = make_ticket(client)
    login(client, "1357")
    feed = client.get("/api/activity").json()
    assert feed[0]["ref"] == last["ticket_ref"] and feed[0]["event"] == "created"
    d = client.get(f"/api/tickets/{last['ticket_id']}").json()
    assert any(s["to_role"] == "engineer" for s in d["sms"])


def test_csv_export_is_officer_only_and_has_no_caller_data(client):
    make_ticket(client)
    login(client, "2468")
    assert client.get("/api/export/tickets.csv").status_code == 403
    login(client, "1357")
    r = client.get("/api/export/tickets.csv")
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert rows[0][0] == "ref" and len(rows) == 2
    assert "caller_hash" not in rows[0] and "transcript" not in rows[0]


def test_text_evaluation_runs_and_reports_n(client):
    csrf = login(client, "1357")
    assert client.post("/api/bench/run-text").status_code == 403              # CSRF required
    r = client.post("/api/bench/run-text", headers={"x-csrf-token": csrf}).json()
    assert r["n_cases"] >= 40 and r["extractor"] == "rules"
    assert r["fields"]["source_type"]["n"] == r["n_cases"]
    assert 0 <= r["fields"]["village"]["rate"] <= 1
    assert client.get("/api/bench").json()["text_eval"]["n_cases"] == r["n_cases"]


def test_system_report_warns_about_defaults(client):
    login(client, "2468")
    s = client.get("/api/system").json()
    assert s["counts"]["villages_on_map"] >= 6 and s["version"]
    assert any("GNANI_API_KEY" in w for w in s["warnings"])


def test_demo_seed_and_clear_are_officer_only_and_labelled(client):
    make_ticket(client)
    csrf = login(client, "2468")
    assert client.post("/api/demo/seed", headers={"x-csrf-token": csrf}).status_code == 403
    csrf = login(client, "1357")
    added = client.post("/api/demo/seed", headers={"x-csrf-token": csrf}).json()["added"]
    tickets_ = client.get("/api/tickets").json()
    assert added == 14 and sum(t["is_synthetic"] for t in tickets_) == 14
    states = {t["state"] for t in tickets_}
    assert {"NEW", "ACKED", "FIX_CLAIMED", "VERIFIED", "UNVERIFIED"} <= states
    assert client.get("/api/tickets", params={"synthetic": "0"}).json()[0]["is_synthetic"] == 0
    m = client.get("/api/metrics", params={"synthetic": "1"}).json()
    assert m["false_closure"]["reopened"] >= 2 and m["false_closure"]["answered"] >= 6
    assert client.post("/api/demo/clear", headers={"x-csrf-token": csrf}).json()["removed"] == 14
    assert len(client.get("/api/tickets").json()) == 1                       # the real ticket survives


def test_public_summary_has_loop_counts(client):
    make_ticket(client)
    j = client.get("/api/public/summary").json()
    assert j["loop"]["tickets"] == 1 and j["loop"]["report_calls"] == 1 and "transcript" not in str(j)


def test_me_shows_demo_pins_only_while_defaults_in_use(client):
    assert client.get("/api/me").json()["demo_pins"] == {"engineer": "2468", "officer": "1357"}
    from app.config import settings
    settings.OFFICER_PIN = "908172"
    assert "demo_pins" not in client.get("/api/me").json()


def test_every_route_is_documented_and_pages_load(client):
    from app.main import routes
    documented = {(m, p) for m, p, *_ in openapi.ENDPOINTS}
    for r in routes:
        if isinstance(r, Mount) or not (r.path.startswith("/api") or r.path == "/health"):
            continue
        for m in r.methods - {"HEAD"}:
            path = r.path.replace("{tid:int}", "{id}").replace("{sid}", "{speech_id}")
            assert (m, path) in documented, f"{m} {path} missing from app/openapi.py"
    spec = client.get("/api/openapi.json").json()
    assert spec["openapi"].startswith("3.1") and "/api/turn" in spec["paths"]
    for p in ("/", "/phone", "/metrics", "/docs", "/login"):
        assert client.get(p).status_code == 200, p
    assert client.get("/no-such-page").status_code == 404
    assert client.get("/api/nope").json()["error"]["code"] == "not_found"


def test_existing_database_is_migrated_in_place(tmp_path):
    import sqlite3
    old = tmp_path / "old.db"
    c = sqlite3.connect(old)
    c.executescript("""CREATE TABLE villages(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, variants TEXT DEFAULT '',
        taluka TEXT, district TEXT, lat REAL, lon REAL, coord_source TEXT);
        INSERT INTO villages(name) VALUES ('Donje');
        CREATE TABLE api_calls(id INTEGER PRIMARY KEY, at TEXT NOT NULL, service TEXT, model TEXT, status INTEGER,
        ok INTEGER, ms REAL, attempt INTEGER, error_kind TEXT, request_id TEXT, cached INTEGER DEFAULT 0);
        INSERT INTO api_calls(at, service) VALUES ('2026-11-10 07:55:07', 'stt');""")
    c.close()
    db.init_db(str(old))
    c = sqlite3.connect(old)
    cols = {r[1] for r in c.execute("PRAGMA table_info(api_calls)")}
    assert "ttfb_ms" in cols and c.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0] == 1
    assert c.execute("SELECT coord_quality FROM villages WHERE name='Kudje'").fetchone()[0] == "approximate"
    assert c.execute("SELECT id FROM villages WHERE name='Donje'").fetchone()[0] == 1   # ids never change
