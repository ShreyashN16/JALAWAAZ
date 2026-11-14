"""Timbre text-to-speech.

REST:      POST https://api.vachana.ai/api/v1/tts/inference  -> one audio file
Streaming: POST https://api.vachana.ai/api/v1/tts/sse        -> SSE events start / chunk / complete,
           each chunk {"chunk_index", "audio": <base64>, "is_final"} (docs.gnani.ai, 2026-11-13)

Choices (see docs/GNANI_INTEGRATION.md):
- Browser phone: MP3 (64 kbit/s, 24 kHz). About a quarter the size of 16-bit WAV, and an <audio>
  element can start playing it while the SSE stream is still arriving, which hides most of Timbre's
  synthesis time. Any streaming failure before the first byte falls back to REST.
- Telephone mode: container=mulaw (G.711, 8 kHz, exactly what a phone line carries). The browser
  cannot play raw mu-law, so it is decoded to an 8 kHz PCM WAV locally; you hear the phone-line sound.
- Numbers: the docs ask for numbers to be written as words; app/core/templates.py does that and
  writes ticket digits one by one. The neutral pause marker becomes the <pauses> audio tag on
  timbre-v3.0 (tags are v3.0-only) and a comma elsewhere.
- Only static template sentences are cached to disk; anything with caller details is never cached.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import AsyncIterator

from ..audio import mulaw_to_wav
from ..config import settings
from . import catalog
from .base import TTS, TTSResult
from .client import GnaniError, call, explain, stream_sse

LANG = {"mr": "mr-IN", "hi": "hi-IN", "hinglish": "hi-IN", "en": "en-IN"}


def voice_and_lang(lang: str) -> tuple[str, str]:
    model = settings.GNANI_TTS_MODEL
    if lang == "hinglish" and model == "timbre-v2.5":
        return settings.TTS_VOICE_HIEN, "hi-en"
    voice = settings.TTS_VOICE_MR if lang == "mr" else settings.TTS_VOICE_HI
    return voice, LANG.get(lang, "hi-IN")


def check_voice_config() -> str | None:
    """Catch a voice/model mismatch before it costs a request (Gnani answers 400)."""
    model = settings.GNANI_TTS_MODEL
    names = [settings.TTS_VOICE_MR, settings.TTS_VOICE_HI]
    if model == "timbre-v2.5":
        names.append(settings.TTS_VOICE_HIEN)
    problems = [p for v in dict.fromkeys(names) if (p := catalog.voice_problem(model, v))]
    return "; ".join(problems) or None


def prepare_text(text: str, model: str | None = None) -> str:
    """Pause markers -> <pauses> (v3.0) or commas; tidy whitespace and punctuation runs."""
    model = model or settings.GNANI_TTS_MODEL
    tags = settings.cfg.get("tts", {}).get("audio_tags", True) and model == "timbre-v3.0"
    if tags:
        return re.sub(r"\s{2,}", " ", text.replace(catalog.PAUSE, " <pauses> ")).strip()
    return catalog.pauses_as_commas(re.sub(r"<[a-z ]+>", " ", text))


def speed() -> float:
    s = float(settings.cfg.get("tts", {}).get("speed", 1.0))
    lo, hi = catalog.TTS_SPEED_RANGE
    return max(lo, min(hi, s))


def audio_config(telephone: bool = False) -> tuple[dict, str]:
    """(audio_config, container) for the request."""
    if telephone and settings.TTS_TELEPHONE_CONTAINER in ("mulaw", "alaw"):
        c = settings.TTS_TELEPHONE_CONTAINER
        return {"container": c}, c
    fmt = settings.TTS_FORMAT if settings.TTS_FORMAT in ("mp3", "wav", "ogg") else "mp3"
    rate = settings.TTS_SAMPLE_RATE if settings.TTS_SAMPLE_RATE in catalog.TTS_SAMPLE_RATES else 24000
    if fmt == "mp3":
        br = settings.TTS_BITRATE if settings.TTS_BITRATE in catalog.TTS_BITRATES else "64k"
        return {"container": "mp3", "sample_rate": rate, "num_channels": 1, "bitrate": br}, "mp3"
    if fmt == "ogg":
        return {"container": "ogg", "encoding": "oggopus", "sample_rate": rate, "num_channels": 1}, "ogg"
    return {"sample_rate": 16000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm",
            "container": "wav"}, "wav"


class Timbre(TTS):
    name = "timbre"

    def mime_for(self, telephone: bool = False) -> str:
        _, container = audio_config(telephone)
        return "audio/wav" if container in ("mulaw", "alaw", "wav") else catalog.CONTAINER_MIME[container]

    def body(self, text: str, lang: str, telephone: bool = False) -> tuple[dict, str]:
        model = settings.GNANI_TTS_MODEL
        voice, code = voice_and_lang(lang)
        cfg, container = audio_config(telephone)
        return ({"text": prepare_text(text, model), "voice": voice, "model": model, "language": code,
                 "speed": speed(), "audio_config": cfg}, container)

    def _finish(self, raw: bytes, container: str) -> bytes:
        if container == "mulaw":
            return mulaw_to_wav(raw, 8000)
        return raw

    async def speak(self, text: str, lang: str, cache: bool = False, telephone: bool = False) -> TTSResult:
        body, container = self.body(text, lang, telephone)
        model, voice = body["model"], body["voice"]
        mime = self.mime_for(telephone)
        key = hashlib.sha256(json_key(body).encode()).hexdigest()
        ext = {"audio/mpeg": "mp3", "audio/ogg": "ogg"}.get(mime, "wav")
        path = os.path.join(settings.TTS_CACHE_DIR, f"{key}.{ext}")
        if cache and os.path.exists(path):
            with open(path, "rb") as f:
                return TTSResult(f.read(), mime, 0.0, cached=True, model=model, voice=voice)
        r, ms = await call("POST", settings.GNANI_TTS_URL, service="tts", model=model, json=body)
        if r.status_code != 200:
            raise explain(r)
        if "json" in r.headers.get("content-type", ""):     # errors can arrive as JSON with a 200
            raise explain(r)
        if len(r.content) < 100:
            raise GnaniError(200, "EMPTY_AUDIO", "Timbre returned no audio")
        audio = self._finish(r.content, container)
        if cache:
            os.makedirs(settings.TTS_CACHE_DIR, exist_ok=True)
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(audio)
            os.replace(tmp, path)
        return TTSResult(audio, mime, ms, model=model, voice=voice)

    def cached(self, text: str, lang: str, telephone: bool = False) -> bytes | None:
        body, _ = self.body(text, lang, telephone)
        ext = {"audio/mpeg": "mp3", "audio/ogg": "ogg"}.get(self.mime_for(telephone), "wav")
        path = os.path.join(settings.TTS_CACHE_DIR, f"{hashlib.sha256(json_key(body).encode()).hexdigest()}.{ext}")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        return None

    def can_stream(self, telephone: bool = False) -> bool:
        _, container = audio_config(telephone)
        return settings.TTS_STREAMING and container == "mp3"

    async def stream(self, text: str, lang: str, telephone: bool = False, stats: dict | None = None) -> AsyncIterator[bytes]:
        """SSE streaming for MP3; REST for everything else or when the stream fails before audio."""
        stats = stats if stats is not None else {}
        if self.can_stream(telephone):
            body, _ = self.body(text, lang, telephone)
            got = False
            try:
                async for chunk in stream_sse(settings.GNANI_TTS_SSE_URL, service="tts-stream",
                                              model=body["model"], json_body=body, stats=stats):
                    got = True
                    yield chunk
                stats["mode"] = "stream"
                return
            except GnaniError as e:
                if got or e.status in (401, 402, 403):
                    raise
                stats["stream_fallback"] = f"{e.status} {e.kind}"
        r = await self.speak(text, lang, telephone=telephone)
        stats.update(mode="rest", ms=r.ms, ttfb_ms=r.ms)
        yield r.audio


def json_key(body: dict) -> str:
    """Stable cache key: everything that changes the audio."""
    import json
    return json.dumps(body, sort_keys=True, ensure_ascii=False)
