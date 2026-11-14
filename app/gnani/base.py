"""Vendor-neutral interfaces. The rest of the app never depends on a Gnani detail."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class STTContext:
    """Optional Prisma v3.0 context hints. Each one can be switched off in data/config.json."""
    keyterms: list[str] = field(default_factory=list)   # village names, water words (max 200)
    topic: str | None = None                            # what the call is about (max 1,600 chars)
    previous_text: str | None = None                    # the question the caller is answering


@dataclass
class STTResult:
    text: str
    lang: str | None = None          # detected_language_code, e.g. "mr-IN"
    ms: float = 0.0
    request_id: str | None = None
    model: str = ""
    truncated: bool = False          # Prisma hit its token limit
    context_used: list[str] = field(default_factory=list)


@dataclass
class TTSResult:
    audio: bytes
    mime: str                        # "audio/mpeg", "audio/wav" ...
    ms: float = 0.0
    cached: bool = False
    model: str = ""
    voice: str = ""
    ttfb_ms: float | None = None


class STT(ABC):
    name = "stt"

    @abstractmethod
    async def transcribe(self, wav: bytes, language_code: str, keyterms: list[str] | None = None,
                         context: STTContext | None = None) -> STTResult: ...


class TTS(ABC):
    name = "tts"

    @abstractmethod
    async def speak(self, text: str, lang: str, cache: bool = False, telephone: bool = False) -> TTSResult: ...

    def mime_for(self, telephone: bool = False) -> str:
        return "audio/wav"

    async def stream(self, text: str, lang: str, telephone: bool = False, stats: dict | None = None) -> AsyncIterator[bytes]:
        """Default: no streaming, one chunk from speak()."""
        r = await self.speak(text, lang, telephone=telephone)
        if stats is not None:
            stats.update(ms=r.ms, ttfb_ms=r.ms, cached=r.cached)
        yield r.audio


class LLM(ABC):
    name = "llm"

    @abstractmethod
    async def complete(self, system: str, user: str, max_tokens: int = 400) -> str: ...
