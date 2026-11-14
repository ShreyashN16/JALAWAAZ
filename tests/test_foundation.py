import io
import math
import struct
import wave

import pytest

from app import audio, db, security


def make_wav(seconds=1.0, rate=16000, amp=0.3):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * 440 * i / rate)))
                               for i in range(n)))
    return buf.getvalue()


def test_villages_seeded(con):
    vs = db.villages(con)
    names = {v["name"] for v in vs}
    assert "Khed Shivapur" in names
    shiv = next(v for v in vs if v["name"] == "Khed Shivapur")
    assert "शिवापूर" in shiv["variants"] and shiv["lat"] is not None
    # villages without a verified source have no coordinates (never invented)
    assert next(v for v in vs if v["name"] == "Sangrun")["lat"] is None


def test_state_trigger_blocks_illegal_transition(con):
    con.execute("INSERT INTO reports(caller_hash, created_at) VALUES ('h', ?)", (db.ts(),))
    con.execute("INSERT INTO tickets(ref, report_id, caller_hash, priority, priority_reason, created_at)"
                " VALUES ('10001', 1, 'h', 3, 'default', ?)", (db.ts(),))
    with pytest.raises(Exception, match="illegal"):
        con.execute("UPDATE tickets SET state='VERIFIED' WHERE id=1")
    con.execute("UPDATE tickets SET state='ACKED' WHERE id=1")
    assert con.execute("SELECT state FROM tickets").fetchone()[0] == "ACKED"


def test_priority_check_constraint(con):
    con.execute("INSERT INTO reports(caller_hash, created_at) VALUES ('h', ?)", (db.ts(),))
    with pytest.raises(Exception):
        con.execute("INSERT INTO tickets(ref, report_id, caller_hash, priority, priority_reason, created_at)"
                    " VALUES ('1', 1, 'h', 0, 'x', ?)", (db.ts(),))


def test_hash_is_salted_and_stable():
    a, b = security.hash_id("device-1"), security.hash_id("device-1")
    assert a == b and "device-1" not in a and len(a) == 32
    assert security.hash_id("device-2") != a


def test_pins_and_rate_limit():
    assert security.role_for_pin("2468") == "engineer"
    assert security.role_for_pin("1357") == "officer"
    assert security.role_for_pin("0000") is None and security.role_for_pin("") is None
    rl = security.RateLimiter(3)
    assert [rl.allow("ip") for _ in range(4)] == [True, True, True, False]


@pytest.mark.skipif(not audio.ffmpeg_available(), reason="ffmpeg missing")
def test_audio_conversion_and_telephone_mode():
    src = make_wav(1.0, rate=44100)
    out = audio.to_wav16k(src)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
    assert abs(audio.wav_duration(out) - 1.0) < 0.05
    tel = audio.to_wav16k(src, telephone=True)
    assert abs(audio.wav_duration(tel) - 1.0) < 0.05
    assert audio.wav_rms(out) > 0.05


def test_audio_rejects_garbage():
    with pytest.raises(audio.AudioError):
        audio.to_wav16k(b"")
    if audio.ffmpeg_available():
        with pytest.raises(audio.AudioError):
            audio.to_wav16k(b"not audio at all")
