"""The 2026-11 Gnani API features, against a mocked HTTP layer (never the real API)."""
import asyncio
import base64
import json
import struct

import pytest

from app.audio import mulaw_to_wav
from app.config import settings
from app.core import templates as tpl
from app.gnani import catalog, client
from app.gnani.base import STTContext
from app.gnani.client import GnaniError, explain, httpx, parse_sse
from app.gnani.evon import Evon
from app.gnani.prisma import Prisma, build_form
from app.gnani.timbre import Timbre, check_voice_config, prepare_text
from app.nlp.spoken import digit_words, number_words

WAV = b"RIFF" + b"\x00" * 200
OK_STT = {"success": True, "request_id": "r1", "transcript": "हो", "model": "prisma-v3.0", "detected_language_code": "mr-IN"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    settings.GNANI_API_KEY = "test-key"
    client.STATE.update(credits_exhausted=False)
    client._sems.clear()

    async def no_sleep(_):
        return None
    monkeypatch.setattr(client.asyncio, "sleep", no_sleep)
    yield
    client.TRANSPORT = None
    client.STATE.update(credits_exhausted=False)


def install(handler):
    seen = []

    def h(req):
        seen.append(req)
        return handler(req, len(seen))
    client.TRANSPORT = httpx.MockTransport(h)
    return seen


def run(c):
    return asyncio.run(c)


def form_fields(req) -> str:
    return req.content.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------- Prisma
def test_prisma_sends_context_hints_and_request_id():
    seen = install(lambda r, i: httpx.Response(200, json=OK_STT))
    ctx = STTContext(keyterms=["शिवापूर", "हातपंप"], topic="Rural water complaint call", previous_text="किती घरांना फटका बसला आहे?")
    r = run(Prisma().transcribe(WAV, "mr-IN", None, ctx))
    body = form_fields(seen[0])
    for f in ('name="topic"', "Rural water complaint call", 'name="previous_text"', "किती घरांना",
              'name="keyterms"', 'name="enable_substitution"', 'name="substitution_map"', "handpump"):
        assert f in body
    assert seen[0].headers["X-API-Request-ID"].startswith("ja-")
    assert set(r.context_used) >= {"keyterms", "topic", "previous_text", "substitution_map"}


def test_context_limits_and_forbidden_tokens():
    data, used = build_form("mr-IN", "transcribe", "prisma-v3.0", [f"t{i}" for i in range(300)] + ["bad<|x"],
                            STTContext(topic="x" * 5000, previous_text="y" * 900), None)
    assert len(json.loads(data["keyterms"])) == catalog.KEYTERMS_MAX
    assert len(data["topic"]) == catalog.TOPIC_MAX_CHARS and len(data["previous_text"]) == catalog.PREVIOUS_TEXT_KEEP
    data, _ = build_form("mr-IN", "transcribe", "prisma-v3.0", ["ok"], STTContext(topic="no <|tags|>"), None)
    assert "topic" not in data


def test_prisma_v25_uses_single_language_and_letter_only_bias_list():
    data, used = build_form("mr-IN,hi-IN", "codemix", "prisma-v2.5", ["शिवापूर", "खेड शिवापूर", "hand-pump", "Donje"],
                            STTContext(topic="ignored on v2.5"), None)
    assert "model" not in data and data["language_code"] == "mr-IN" and data["format"] == "transcribe"
    assert json.loads(data["bias_list"]) == ["शिवापूर", "Donje"] and data["bias_score"] == "1.0"
    assert "topic" not in data and "keyterms" not in data


def test_explain_handles_422_list_and_504_shape():
    e = explain(httpx.Response(422, json={"detail": [{"loc": ["body", "language_code"], "msg": "Field required"}]}))
    assert e.status == 422 and e.kind == "VALIDATION" and "Field required" in e.message
    e = explain(httpx.Response(504, json={"error": "Gateway Timeout", "code": "UPSTREAM_TIMEOUT", "message": "slow"}))
    assert e.kind == "UPSTREAM_TIMEOUT" and e.user_hint.startswith("Gnani timed out")


def test_504_is_retried_then_succeeds():
    seen = install(lambda r, i: httpx.Response(504, json={"error": "Gateway Timeout", "code": "UPSTREAM_TIMEOUT"})
                   if i == 1 else httpx.Response(200, json=OK_STT))
    assert run(Prisma().transcribe(WAV, "mr-IN")).text == "हो" and len(seen) == 2


def test_truncated_flag_is_reported():
    install(lambda r, i: httpx.Response(200, json={**OK_STT, "truncated": True}))
    assert run(Prisma().transcribe(WAV, "mr-IN")).truncated is True


# ---------------------------------------------------------------- Timbre
def sse(*events):
    out = ""
    for name, payload in events:
        out += f"event: {name}\ndata: {json.dumps(payload)}\n\n"
    return out.encode()


def test_timbre_sse_stream_yields_chunks_in_order():
    a, b = b"ID3" + b"\x01" * 300, b"\xff\xfb" + b"\x02" * 300
    seen = install(lambda r, i: httpx.Response(200, content=sse(
        ("start", {"status": "streaming_started"}),
        ("chunk", {"chunk_index": 0, "audio": base64.b64encode(a).decode(), "is_final": False}),
        ("chunk", {"chunk_index": 1, "audio": base64.b64encode(b).decode(), "is_final": False}),
        ("complete", {"chunk_index": 2, "audio": "", "is_final": True})), headers={"content-type": "text/event-stream"}))
    stats = {}

    async def collect():
        return [c async for c in Timbre().stream("नमस्कार", "mr", stats=stats)]
    chunks = run(collect())
    assert chunks == [a, b] and stats["mode"] == "stream" and stats["bytes"] == len(a) + len(b)
    assert str(seen[0].url).endswith("/api/v1/tts/sse")
    assert json.loads(seen[0].content)["audio_config"]["container"] == "mp3"


def test_timbre_stream_falls_back_to_rest_when_sse_fails():
    mp3 = b"ID3" + b"\x05" * 500

    def h(req, i):
        if req.url.path.endswith("/sse"):
            return httpx.Response(500, content=b"boom")
        return httpx.Response(200, content=mp3, headers={"content-type": "audio/mpeg"})
    seen = install(h)
    stats = {}

    async def collect():
        return [c async for c in Timbre().stream("नमस्कार", "mr", stats=stats)]
    assert run(collect()) == [mp3] and stats["mode"] == "rest" and "stream_fallback" in stats
    assert any(r.url.path.endswith("/inference") for r in seen)


def test_timbre_stream_error_event_before_audio_falls_back():
    mp3 = b"ID3" + b"\x07" * 500

    def h(req, i):
        if req.url.path.endswith("/sse"):
            return httpx.Response(200, content=sse(("error", {"type": "error", "message": "model busy"})))
        return httpx.Response(200, content=mp3, headers={"content-type": "audio/mpeg"})
    install(h)

    async def collect():
        return [c async for c in Timbre().stream("x", "hi")]
    assert run(collect()) == [mp3]


def test_telephone_mode_requests_mulaw_and_returns_playable_wav():
    mulaw = bytes(range(256)) * 4
    seen = install(lambda r, i: httpx.Response(200, content=mulaw, headers={"content-type": "audio/basic"}))
    r = run(Timbre().speak("नमस्कार", "mr", telephone=True))
    body = json.loads(seen[0].content)
    assert body["audio_config"] == {"container": "mulaw"}
    assert r.audio[:4] == b"RIFF" and r.mime == "audio/wav"
    assert struct.unpack("<I", r.audio[24:28])[0] == 8000


def test_mulaw_decoder_known_values():
    wav = mulaw_to_wav(bytes([0xFF, 0x7F, 0x00, 0x80]))
    samples = struct.unpack("<4h", wav[44:52])
    assert samples[0] == 0 and samples[1] == 0 and samples[2] == -32124 and samples[3] == 32124


def test_pause_markers_become_tags_only_on_v30():
    s = f"तक्रार क्रमांक {catalog.PAUSE} चार, दोन."
    assert "<pauses>" in prepare_text(s, "timbre-v3.0")
    assert "<pauses>" not in prepare_text(s, "timbre-v2.5") and "क्रमांक, चार" in prepare_text(s, "timbre-v2.5")


def test_voice_catalogue_validation_both_directions():
    settings.GNANI_TTS_MODEL, settings.TTS_VOICE_MR, settings.TTS_VOICE_HI = "timbre-v3.0", "Shivani", "Kalpana"
    assert check_voice_config() is None
    settings.TTS_VOICE_MR = "Zahira"
    assert "belongs to timbre-v2.5" in check_voice_config()
    settings.GNANI_TTS_MODEL, settings.TTS_VOICE_MR, settings.TTS_VOICE_HI, settings.TTS_VOICE_HIEN = "timbre-v2.5", "Zahira", "Shivani", "Poorvi"
    assert "belongs to timbre-v3.0" in check_voice_config()
    settings.TTS_VOICE_HI = "Nalini"
    assert check_voice_config() is None
    settings.GNANI_TTS_MODEL, settings.TTS_VOICE_MR, settings.TTS_VOICE_HI = "timbre-v3.0", "Shivani", "Shivani"


def test_sse_parser_variants():
    assert parse_sse(["event: chunk", 'data: {"audio": "QQ==", "is_final": false}'])[0] == "chunk"
    assert parse_sse(['data: {"audio": "", "is_final": true}'])[0] == "complete"


# ---------------------------------------------------------------- speech text
def test_numbers_are_spelled_and_ticket_digits_read_one_by_one():
    assert number_words(40, "mr") == "चाळीस" and number_words(40, "hi") == "चालीस"
    assert number_words(100, "mr") == "शंभर" and number_words(150, "mr") == "एकशे पन्नास"
    assert number_words(1250, "hi") == "एक हज़ार दो सौ पचास" and number_words(2000, "mr") == "दोन हजार"
    assert digit_words("40712", "mr") == "चार, शून्य, सात, एक, दोन"
    r = tpl.readback({"source_type": "handpump", "fault": "no_water", "duration_days": 3, "households_affected": 40},
                     "शिवापूर", "mr")
    assert "3 दिवसांपासून" in r and "तीन दिवसांपासून" in r.speech and "चाळीस घरांना" in r.speech


def test_say_survives_concatenation():
    x = tpl.t("ticket", "hi", digits=tpl.digits("12345", "hi")) + " " + tpl.t("safety_line", "hi")
    assert isinstance(x, tpl.Say) and "12345" in x and "एक, दो, तीन" in x.speech and "उबालकर" in x.speech


# ---------------------------------------------------------------- Evon
def test_evon_json_mode_dropped_when_server_rejects_it():
    seen = install(lambda r, i: httpx.Response(400, json={"error": "response_format not supported"}) if i == 1 else
                   httpx.Response(200, json={"choices": [{"message": {"content": '{"village": "Donje"}'}}]}))
    settings.EVON_BASE_URL, settings.EVON_JSON_MODE = "http://evon.test", True
    assert run(Evon().complete("s", "u")) == '{"village": "Donje"}'
    first, second = json.loads(seen[0].content), json.loads(seen[1].content)
    assert "response_format" in first and "response_format" not in second and "chat_template_kwargs" in second


def test_check_gnani_reports_bad_key():
    from app.gnani import providers
    install(lambda r, i: httpx.Response(401, json={"detail": {"error_code": "INVALID_API_KEY", "message": "bad"}}))
    out = run(providers.check_gnani())
    assert out["ok"] is False and out["status"] == 401 and "INVALID_API_KEY" in out["message"]
