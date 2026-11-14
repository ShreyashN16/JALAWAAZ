"""Which model is actually serving each role right now. Used for honest UI labels.

Rules (never silently substituted):
- STT: Prisma when a Gnani key is set and credits remain; otherwise None (the caller types instead).
- TTS: Timbre when a key is set; otherwise None (the page may use the browser voice, labelled).
- LLM: Evon when EVON_ENABLED and the server answers; otherwise rule-based extraction (labelled).
"""
from __future__ import annotations

import time

from ..config import settings
from . import catalog
from .base import LLM, STT, TTS
from .client import STATE, GnaniError, call, explain
from .evon import Evon
from .prisma import Prisma
from .timbre import Timbre, audio_config, check_voice_config, voice_and_lang

_override: dict = {}
_evon_ping = {"at": 0.0, "ok": False}


def set_providers(**kw) -> None:
    """Tests (and the benchmark) inject fakes: set_providers(stt=..., tts=..., llm=...)."""
    _override.clear()
    _override.update(kw)


def stt() -> STT | None:
    if "stt" in _override:
        return _override["stt"]
    return Prisma() if settings.GNANI_API_KEY and not STATE["credits_exhausted"] else None


def tts() -> TTS | None:
    if "tts" in _override:
        return _override["tts"]
    return Timbre() if settings.GNANI_API_KEY and not STATE["credits_exhausted"] else None


async def llm() -> LLM | None:
    if "llm" in _override:
        return _override["llm"]
    if not settings.EVON_ENABLED:
        return None
    if time.time() - _evon_ping["at"] > 30:
        e = Evon()
        _evon_ping.update(at=time.time(), ok=await e.ping())
    return Evon() if _evon_ping["ok"] else None


async def status() -> dict:
    l = await llm()
    s, t = stt(), tts()
    cfg_stt = settings.cfg.get("stt", {})
    _, container = audio_config(False)
    return {
        "stt": {"provider": "prisma" if s else "none", "model": settings.GNANI_STT_MODEL if s else None,
                "key_configured": settings.gnani_configured, "format": cfg_stt.get("format"),
                "context": {k: bool(v) for k, v in (cfg_stt.get("context") or {}).items()},
                "substitution_rules": len(cfg_stt.get("substitutions") or [])},
        "tts": {"provider": "timbre" if t else "browser-fallback", "model": settings.GNANI_TTS_MODEL if t else None,
                "voices": {lang: voice_and_lang(lang)[0] for lang in ("mr", "hi", "hinglish")},
                "format": container, "streaming": bool(settings.TTS_STREAMING and container == "mp3"),
                "voice_config_error": check_voice_config()},
        "llm": {"provider": "evon" if l else "rules", "enabled": settings.EVON_ENABLED,
                "base_url": settings.EVON_BASE_URL if settings.EVON_ENABLED else None},
        "credits_exhausted": STATE["credits_exhausted"],
        "last_error": STATE.get("last_error"),
        "docs_checked": catalog.DOCS_CHECKED,
    }


async def check_gnani() -> dict:
    """Validate the key with Prisma's language list (a metadata call, no audio is sent)."""
    if not settings.GNANI_API_KEY:
        return {"ok": False, "status": 401, "message": "GNANI_API_KEY is not set in .env"}
    try:
        r, ms = await call("GET", settings.GNANI_STT_LANGUAGES_URL, service="stt-meta", model="languages")
    except GnaniError as e:
        return {"ok": False, "status": e.status, "message": f"{e.kind}: {e.message}", "hint": e.user_hint}
    if r.status_code != 200:
        e = explain(r)
        return {"ok": False, "status": r.status_code, "message": f"{e.kind}: {e.message}", "hint": e.user_hint}
    try:
        body = r.json()
    except ValueError:
        body = {}
    limits = body.get("audio_constraints") if isinstance(body, dict) else None
    return {"ok": True, "status": 200, "ms": round(ms), "audio_constraints": limits,
            "message": "Key accepted by Gnani"}
