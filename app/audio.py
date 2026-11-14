"""Audio conversion. Audio lives only in memory or a temporary directory that is deleted.

Prisma REST accepts wav/mp3/ogg/flac/aac/m4a, 0.1-30 s, and resamples to 16 kHz mono itself. Phone
browsers record webm/opus (Android Chrome) or mp4 (iOS Safari), which Prisma does not accept, so
everything is converted to 16 kHz mono WAV with ffmpeg. Telephone mode simulates a G.711 mu-law
8 kHz line before converting back, so the same pipeline is tested on phone-quality audio.
"""
from __future__ import annotations

import array
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave


class AudioError(Exception):
    pass


def get_ffmpeg_binary() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for candidate in (os.path.join(sys.prefix, "Scripts", "ffmpeg.exe"), os.path.join(sys.prefix, "Scripts", "ffmpeg"),
                      os.path.join(sys.prefix, "bin", "ffmpeg"), os.path.join(sys.prefix, "bin", "ffmpeg.exe")):
        if os.path.exists(candidate):
            return candidate
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffmpeg_available() -> bool:
    return get_ffmpeg_binary() is not None


def _ff(*args: str) -> None:
    exe = get_ffmpeg_binary() or "ffmpeg"
    try:
        r = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, timeout=30)
    except FileNotFoundError:
        raise AudioError("ffmpeg is not installed or not on PATH")
    except subprocess.TimeoutExpired:
        raise AudioError("ffmpeg took too long")
    if r.returncode != 0:
        raise AudioError("ffmpeg failed: " + r.stderr.decode(errors="ignore")[-300:])


def to_wav16k(raw: bytes, telephone: bool = False) -> bytes:
    if not raw:
        raise AudioError("empty audio")
    if not ffmpeg_available():
        raise AudioError("ffmpeg is not installed or not on PATH")
    with tempfile.TemporaryDirectory(prefix="ja_") as d:      # deleted on exit: no audio persists
        src, dst = os.path.join(d, "in"), os.path.join(d, "out.wav")
        with open(src, "wb") as f:
            f.write(raw)
        if telephone:
            mid = os.path.join(d, "mid.wav")
            _ff("-i", src, "-ac", "1", "-ar", "8000", "-c:a", "pcm_mulaw", mid)
            _ff("-i", mid, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst)
        else:
            _ff("-i", src, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst)
        with open(dst, "rb") as f:
            return f.read()


def wav_duration(wav: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav)) as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, ZeroDivisionError) as e:
        raise AudioError(f"not a WAV file: {e}")


def wav_rms(wav: bytes) -> float:
    """Rough loudness (0..1) to catch silent clips before spending a Prisma credit."""
    with wave.open(io.BytesIO(wav)) as w:
        frames = w.readframes(w.getnframes())
    a = array.array("h")
    a.frombytes(frames[: len(frames) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    if not a:
        return 0.0
    step = max(1, len(a) // 16000)
    s = a[::step]
    return (sum(x * x for x in s) / len(s)) ** 0.5 / 32768


# ---------------------------------------------------------------- G.711 mu-law (telephone mode)
def _mulaw_table() -> list[int]:
    out = []
    for b in range(256):
        u = ~b & 0xFF
        sign, exponent, mantissa = u & 0x80, (u >> 4) & 0x07, u & 0x0F
        sample = ((mantissa << 3) + 0x84) << exponent
        sample -= 0x84
        out.append(-sample if sign else sample)
    return out


_MULAW = _mulaw_table()


def pcm16_wav(samples: array.array, rate: int) -> bytes:
    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    data = samples.tobytes()
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data))
    return header + data


def mulaw_to_wav(raw: bytes, rate: int = 8000) -> bytes:
    """Decode headerless G.711 mu-law bytes to a 16-bit PCM WAV the browser can play."""
    if raw[:4] == b"RIFF":                    # already a WAV container
        return raw
    return pcm16_wav(array.array("h", (_MULAW[b] for b in raw)), rate)
