"""Short-lived store of replies waiting to be spoken.

A turn returns its text at once with an `audio_url`; the browser then fetches /api/speech/<id>,
which streams Timbre audio as it is synthesised. The finished audio is kept in memory for a couple
of minutes so "play again" and browser re-requests do not cost another Gnani credit. Nothing here
is written to disk (static prompts are cached by the Timbre adapter, never caller details).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from ..security import new_token

TTL_SEC = 180
MAX_ITEMS = 400


@dataclass
class SpeechItem:
    id: str
    text: str                       # what Timbre should say (Say.speech)
    lang: str
    telephone: bool = False
    static: bool = False            # a fixed template sentence: safe to cache on disk
    call_id: int | None = None
    created: float = field(default_factory=time.time)
    audio: bytes | None = None      # filled once fully synthesised
    mime: str | None = None
    lock: asyncio.Lock | None = None


STORE: dict[str, SpeechItem] = {}


def _prune() -> None:
    now = time.time()
    for k in [k for k, v in STORE.items() if now - v.created > TTL_SEC]:
        STORE.pop(k, None)
    if len(STORE) > MAX_ITEMS:
        for k in sorted(STORE, key=lambda k: STORE[k].created)[: len(STORE) - MAX_ITEMS]:
            STORE.pop(k, None)


def register(text: str, lang: str, telephone: bool = False, static: bool = False, call_id: int | None = None) -> str:
    _prune()
    sid = new_token(12)
    STORE[sid] = SpeechItem(sid, text, lang, telephone, static, call_id)
    return sid


def get(sid: str) -> SpeechItem | None:
    _prune()
    return STORE.get(sid)
