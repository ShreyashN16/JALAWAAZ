"""Gnani adapters against a mocked HTTP layer. These tests never call the real API."""
import asyncio
import json

import pytest

from app import db
from app.config import settings
from app.gnani import client
from app.gnani.client import GnaniError, httpx
from app.gnani.evon import Evon, EvonError
from app.gnani.prisma import Prisma
from app.gnani.timbre import Timbre, check_voice_config

WAV = b"RIFF" + b"\x00" * 200


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    settings.GNANI_API_KEY = "test-key"
    client.STATE.update(credits_exhausted=False)
    client._sems.clear()

    async def no_sleep(_):
        return None
    monkeypatch.setattr(client.asyncio, "sleep", no_sleep)
    yield
    client.TRANSPORT = None
    client.STATE.update(credits_exhausted=False)


def install(responses):
    """responses: list of (status, body, headers) returned in order; records requests."""
    seen = []
    it = iter(responses)

    def handler(req):
        seen.append(req)
        status, body, headers = next(it)
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body, headers=headers or {})
        return httpx.Response(status, content=body, headers=headers or {})
    client.TRANSPORT = httpx.MockTransport(handler)
    return seen


OK_STT = {"success": True, "request_id": "r1", "transcript": "शिवापूर मध्ये हातपंप 3 दिवस बंद आहे",
          "model": "prisma-v3.0", "detected_language_code": "mr-IN"}


def run(c):
    return asyncio.run(c)


def api_rows():
    con = db.connect()
    try:
        return [dict(r) for r in con.execute("SELECT service, status, ok, attempt FROM api_calls ORDER BY id")]
    finally:
        con.close()


def test_prisma_success_sends_documented_fields():
    seen = install([(200, OK_STT, None)])
    r = run(Prisma().transcribe(WAV, "mr-IN,hi-IN,en-IN", keyterms=["शिवापूर", "हातपंप"]))
    assert r.text.startswith("शिवापूर") and r.lang == "mr-IN" and r.request_id == "r1"
    req = seen[0]
    assert str(req.url) == "https://api.vachana.ai/stt/v3"
    assert req.headers["X-API-Key-ID"] == "test-key"
    body = req.content.decode("utf-8", errors="ignore")
    for field in ('name="model"', "prisma-v3.0", 'name="format"', "transcribe",
                  'name="language_code"', "mr-IN,hi-IN,en-IN", 'name="keyterms"', 'name="audio_file"'):
        assert field in body
    assert api_rows() == [{"service": "stt", "status": 200, "ok": 1, "attempt": 0}]


def test_401_not_retried():
    seen = install([(401, {"detail": {"error_code": "INVALID_API_KEY", "message": "bad", "status_code": 401}}, None)])
    with pytest.raises(GnaniError) as e:
        run(Prisma().transcribe(WAV, "mr-IN"))
    assert e.value.status == 401 and e.value.kind == "INVALID_API_KEY" and len(seen) == 1


def test_402_marks_credits_exhausted_and_stops_calls():
    install([(402, {"detail": {"error_code": "INSUFFICIENT_CREDITS", "message": "no credit"}}, None)])
    with pytest.raises(GnaniError):
        run(Prisma().transcribe(WAV, "mr-IN"))
    assert client.STATE["credits_exhausted"] is True
    seen = install([(200, OK_STT, None)])
    with pytest.raises(GnaniError) as e:
        run(Prisma().transcribe(WAV, "mr-IN"))
    assert e.value.status == 402 and seen == []          # no further paid requests


def test_429_then_success_retries():
    seen = install([(429, {"detail": {"error_code": "RATE_LIMITED", "message": "one at a time"}}, None),
                    (200, OK_STT, None)])
    assert run(Prisma().transcribe(WAV, "mr-IN")).text
    assert len(seen) == 2 and [r["attempt"] for r in api_rows()] == [0, 1]


def test_500_then_success_retries():
    seen = install([(500, b"oops", None), (200, OK_STT, None)])
    assert run(Prisma().transcribe(WAV, "hi-IN")).lang == "mr-IN" and len(seen) == 2


def test_three_503s_give_up_with_error():
    install([(503, b"x", None)] * 3)
    with pytest.raises(GnaniError) as e:
        run(Prisma().transcribe(WAV, "hi-IN"))
    assert e.value.status == 503


def test_stt_error_envelope():
    install([(400, {"success": False, "error": {"type": "INVALID_CONTEXT", "message": "bad keyterms"}}, None)])
    with pytest.raises(GnaniError) as e:
        run(Prisma().transcribe(WAV, "mr-IN", keyterms=["x"]))
    assert e.value.kind == "INVALID_CONTEXT"


def test_timbre_success_body_and_cache(tmp_path):
    audio = b"RIFF" + b"\x01" * 500
    seen = install([(200, audio, {"content-type": "audio/wav"})])
    t = Timbre()
    r1 = run(t.speak("नमस्कार", "mr", cache=True))
    r2 = run(t.speak("नमस्कार", "mr", cache=True))      # served from cache, no second request
    assert r1.audio == audio and r2.cached and len(seen) == 1
    body = json.loads(seen[0].content)
    assert body["model"] == "timbre-v3.0" and body["voice"] == "Shivani" and body["language"] == "mr-IN"
    assert body["audio_config"]["container"] == "mp3" and body["audio_config"]["bitrate"] == "64k"
    assert 0.85 <= body["speed"] <= 1.15 and r1.mime == "audio/mpeg"


def test_timbre_dynamic_text_not_cached():
    audio = b"RIFF" + b"\x01" * 500
    seen = install([(200, audio, {"content-type": "audio/wav"})] * 2)
    run(Timbre().speak("क्रमांक 4 4 7 1", "mr"))
    run(Timbre().speak("क्रमांक 4 4 7 1", "mr"))
    assert len(seen) == 2


def test_timbre_400_voice_mismatch():
    install([(400, {"success": False, "message": "Invalid voice 'Zahira' for model timbre-v3.0. Valid: Shivani, ...",
                    "status_code": 400}, None)])
    with pytest.raises(GnaniError) as e:
        run(Timbre().speak("hello", "hi"))
    assert e.value.status == 400 and "Zahira" in e.value.message


def test_voice_config_check():
    settings.TTS_VOICE_MR = "Zahira"
    assert "timbre-v2.5" in check_voice_config()
    settings.TTS_VOICE_MR = "Shivani"
    assert check_voice_config() is None


def test_evon_strips_think_and_retries_without_template_kwargs():
    seen = install([(400, {"error": "unknown field chat_template_kwargs"}, None),
                    (200, {"choices": [{"message": {"content": "<think>hmm</think>{\"village\": \"Shivapur\"}"}}]}, None)])
    settings.EVON_BASE_URL = "http://evon.test"
    out = run(Evon().complete("Return only JSON.", "x"))
    assert out == '{"village": "Shivapur"}'
    first, second = json.loads(seen[0].content), json.loads(seen[1].content)
    assert first["temperature"] == 0 and "chat_template_kwargs" in first and "chat_template_kwargs" not in second


def test_evon_unreachable_raises():
    def boom(req):
        raise httpx.ConnectError("refused")
    client.TRANSPORT = httpx.MockTransport(boom)
    with pytest.raises(EvonError):
        run(Evon().complete("s", "u"))
