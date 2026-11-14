"""The five-act demo over HTTP: missed call -> callback -> report -> engineer -> verification."""
import io
import math
import struct
import wave

import pytest
from starlette.testclient import TestClient

from app import db
from app.audio import ffmpeg_available
from app.config import settings
from app.core import scheduler
from app.gnani import providers
from app.gnani.base import STT, STTResult


@pytest.fixture
def client():
    providers.set_providers(stt=None, tts=None, llm=None)
    from app.main import app, limiter
    limiter.hits.clear()                     # each test starts with a fresh rate-limit window
    with TestClient(app) as c:
        yield c
    providers.set_providers()


DEV = "device-abcdef-123"


def login(c, pin):
    r = c.post("/api/login", json={"pin": pin})
    assert r.status_code == 200
    return r.json()["csrf"]


def say(c, sid, text):
    r = c.post("/api/turn", data={"session_id": sid, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def report_ticket(c, device=DEV):
    assert c.post("/api/missed-call", json={"device": device}).json()["simulated"] is True
    p = c.get("/api/poll", params={"device": device}).json()
    assert p["incoming"] == "callback"
    s = c.post("/api/session", json={"device": device, "mode": "report", "lang": "mr"}).json()
    assert "एआय सहायक" in s["reply_text"]
    say(c, s["session_id"], "Shivapur madhe handpump 3 divas band aahe, 40 ghar")
    say(c, s["session_id"], "nahi")
    last = say(c, s["session_id"], "ho")
    assert last["done"] and last["outcome"] == "ticket"
    return last["ticket_id"], last["ticket_ref"]


def test_pages_and_health(client):
    assert client.get("/phone").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert client.get("/login").status_code == 200
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    h = client.get("/health").json()
    assert h["ok"] and h["providers"]["llm"]["provider"] == "rules"
    assert "X-Request-ID" in client.get("/health").headers


def test_five_act_demo_yes_then_no(client):
    tid, ref = report_ticket(client)
    # staff APIs need a login
    assert client.get("/api/tickets").status_code == 401
    csrf = login(client, settings.ENGINEER_PIN)
    t = client.get("/api/tickets").json()
    assert t[0]["ref"] == ref and t[0]["state"] == "NEW" and "caller_hash" not in t[0]
    # CSRF required for state changes
    assert client.post(f"/api/tickets/{tid}/ack").status_code == 403
    H = {"X-CSRF-Token": csrf}
    assert client.post(f"/api/tickets/{tid}/ack", headers=H).json()["state"] == "ACKED"
    d = client.post(f"/api/tickets/{tid}/fix-claimed", headers=H, json={"note": "new washer"}).json()
    assert d["state"] == "FIX_CLAIMED"                       # never closed by the engineer
    con = db.connect()
    scheduler.tick(con)
    con.close()
    p = client.get("/api/poll", params={"device": DEV}).json()
    assert p["incoming"] == "verification" and p["ticket_id"] == tid
    s = client.post("/api/session", json={"device": DEV, "mode": "verify", "lang": "mr", "ticket_id": tid}).json()
    assert ref[0] in s["reply_text"]
    v = say(client, s["session_id"], "ho, chalu jhala")
    assert v["outcome"] == "verified"
    m = client.get("/api/metrics").json()
    assert m["by_state"]["VERIFIED"] == 1 and m["false_closure"]["answered"] == 1

    # second run: the caller says no
    tid2, _ = report_ticket(client, device=DEV + "x")
    client.post(f"/api/tickets/{tid2}/fix-claimed", headers=H)
    con = db.connect()
    scheduler.tick(con)
    con.close()
    client.get("/api/poll", params={"device": DEV + "x"})
    s = client.post("/api/session", json={"device": DEV + "x", "mode": "verify", "lang": "mr", "ticket_id": tid2}).json()
    assert say(client, s["session_id"], "nahi, ajun band aahe")["outcome"] == "reopened"
    t2 = client.get(f"/api/tickets/{tid2}").json()
    assert t2["state"] == "ACKED" and t2["reopened_count"] == 1 and t2["priority"] == 1
    m = client.get("/api/metrics").json()
    assert m["false_closure"] == {"reopened": 1, "answered": 2, "rate": 0.5}


def test_officer_cannot_act_and_bad_pin(client):
    assert client.post("/api/login", json={"pin": "9999"}).status_code == 401
    tid, _ = report_ticket(client)
    csrf = login(client, settings.OFFICER_PIN)
    assert client.get("/api/tickets").status_code == 200
    assert client.post(f"/api/tickets/{tid}/ack", headers={"X-CSRF-Token": csrf}).status_code == 403


def test_verify_requires_original_device(client):
    tid, _ = report_ticket(client)
    csrf = login(client, settings.ENGINEER_PIN)
    client.post(f"/api/tickets/{tid}/fix-claimed", headers={"X-CSRF-Token": csrf})
    r = client.post("/api/session", json={"device": "intruder-device-999", "mode": "verify", "ticket_id": tid})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_caller"


def test_validation_and_public_summary(client):
    assert client.post("/api/session", json={"device": "short", "mode": "report"}).status_code == 422
    assert client.post("/api/turn", data={"session_id": "nope", "text": "x"}).status_code == 404
    report_ticket(client)
    s = client.get("/api/public/summary").json()
    assert s["total"] == 1 and "repeat_sources" in s
    assert "transcript" not in str(s)


def tone_wav(seconds=1.0):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 300 * i / 16000))) for i in range(int(16000 * seconds))))
    return buf.getvalue()


class FakePrisma(STT):
    def __init__(self):
        self.calls = []

    async def transcribe(self, wav, language_code, keyterms=None, context=None):
        self.calls.append((len(wav), language_code, context.keyterms if context else keyterms, context))
        return STTResult("शिवापूर मध्ये हातपंप तीन दिवस बंद आहे, चाळीस घरे", "mr-IN", 5.0, "r1", "prisma-v3.0")


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg missing")
def test_audio_turn_uses_stt_with_keyterms_and_telephone_mode(client):
    fake = FakePrisma()
    providers.set_providers(stt=fake, tts=None, llm=None)
    s = client.post("/api/session", json={"device": DEV, "mode": "report", "lang": "mr", "telephone": True}).json()
    r = client.post("/api/turn", data={"session_id": s["session_id"]}, files={"audio": ("turn", tone_wav(), "audio/webm")})
    j = r.json()
    assert r.status_code == 200 and j["providers"]["stt"] == "prisma" and "शिवापूर" in j["transcript"]
    n, code, kt, ctx = fake.calls[0]
    assert code == "mr-IN,hi-IN,en-IN" and "शिवापूर" in kt and len(kt) <= 200
    assert "Haveli" in ctx.topic and "एआय सहायक" in ctx.previous_text      # Prisma context hints
    assert j["report"]["village_matched"] == "Khed Shivapur" and j["report"]["households_affected"] == 40
    # language is now known, so the next turn sends only mr-IN
    client.post("/api/turn", data={"session_id": s["session_id"]}, files={"audio": ("turn", tone_wav(), "audio/mp4")})
    assert fake.calls[1][1] == "mr-IN"


def test_no_stt_key_offers_typing(client):
    s = client.post("/api/session", json={"device": DEV, "mode": "report"}).json()
    if not ffmpeg_available():
        pytest.skip("ffmpeg missing")
    j = client.post("/api/turn", data={"session_id": s["session_id"]}, files={"audio": ("t", tone_wav(), "audio/webm")}).json()
    assert j["offer_text"] and j["providers"]["stt"] == "none" and "type" in j["notices"][0].lower()


def test_bench_endpoint(client):
    j = client.get("/api/bench").json()
    assert "live_api_calls" in j and "benchmark" in j
