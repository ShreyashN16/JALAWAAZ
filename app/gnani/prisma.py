"""Prisma speech-to-text (REST). POST https://api.vachana.ai/stt/v3, multipart form.

Fields we send (docs.gnani.ai, re-checked 2026-11-13):
  audio_file, model=prisma-v3.0, language_code (one code, up to four comma-separated, or indic-auto),
  format (always explicit: `transcribe` writes numbers as digits),
  v3.0 context hints: keyterms (JSON array, max 200), topic (max 1,600 chars),
  previous_text (only the last 600 chars are used), and optional substitution rules
  (enable_substitution + substitution_map, max 10 rules).
Prisma v2.5 (omit `model`): one language, bias_list of single letter-only words (max 100) with a
positive bias_score; v3.0-only fields are not sent.
Response: success, request_id, transcript, model, detected_language_code, truncated,
processing_time, end_to_end_latency.
"""
from __future__ import annotations

import json
import unicodedata

from ..config import settings
from . import catalog
from .base import STT, STTContext, STTResult
from .client import call, explain

FORBIDDEN = ("<|", "|>")          # Prisma rejects context values containing these


def _clean_terms(terms: list[str] | None, limit: int) -> list[str]:
    out = []
    for t in dict.fromkeys(t.strip() for t in (terms or []) if t and t.strip()):
        if any(f in t for f in FORBIDDEN):
            continue
        out.append(t[:60])
        if len(out) >= limit:
            break
    return out


def _letters_only(word: str) -> bool:
    return bool(word) and all(unicodedata.category(c)[0] in "LM" for c in word)


def build_form(language_code: str, fmt: str, model: str, keyterms: list[str] | None,
               context: STTContext | None, substitutions: list[dict] | None) -> tuple[dict, list[str]]:
    """The multipart fields for one request, plus the names of the context hints used."""
    used: list[str] = []
    ctx = context or STTContext()
    terms = keyterms if keyterms is not None else ctx.keyterms
    data: dict = {}
    if model and model != "prisma-v2.5":
        data["model"] = model
        data["language_code"] = language_code
        data["format"] = fmt if fmt in catalog.STT_FORMATS_V3 else "transcribe"
        kt = _clean_terms(terms, catalog.KEYTERMS_MAX)
        if kt:
            data["keyterms"] = json.dumps(kt, ensure_ascii=False)
            used.append("keyterms")
        if ctx.topic and not any(f in ctx.topic for f in FORBIDDEN):
            data["topic"] = ctx.topic.strip()[: catalog.TOPIC_MAX_CHARS]
            used.append("topic")
        prev = (ctx.previous_text or "").strip()
        if len(prev) >= 4 and not any(f in prev for f in FORBIDDEN):
            data["previous_text"] = prev[-catalog.PREVIOUS_TEXT_KEEP:]
            used.append("previous_text")
    else:                                             # Prisma v2.5: omit `model`
        data["language_code"] = language_code.split(",")[0].strip()
        data["format"] = fmt if fmt in catalog.STT_FORMATS_V25 else "transcribe"
        words = [w for w in _clean_terms(terms, 1000) if _letters_only(w)][: catalog.BIAS_LIST_MAX]
        if words:
            data["bias_list"] = json.dumps(words, ensure_ascii=False)
            data["bias_score"] = "1.0"
            used.append("bias_list")
    rules = [r for r in (substitutions or []) if isinstance(r, dict) and r.get("patterns") and r.get("replacement")]
    if rules:
        data["enable_substitution"] = "true"
        data["substitution_map"] = json.dumps(rules[: catalog.SUBSTITUTION_MAX_RULES], ensure_ascii=False)
        used.append("substitution_map")
    return data, used


class Prisma(STT):
    name = "prisma"

    def __init__(self, fmt: str | None = None):
        self.fmt = fmt or settings.cfg.get("stt", {}).get("format", "transcribe")

    async def transcribe(self, wav: bytes, language_code: str, keyterms: list[str] | None = None,
                         context: STTContext | None = None) -> STTResult:
        model = settings.GNANI_STT_MODEL
        stt_cfg = settings.cfg.get("stt", {})
        data, used = build_form(language_code, self.fmt, model, keyterms, context, stt_cfg.get("substitutions"))
        r, ms = await call("POST", settings.GNANI_STT_URL, service="stt", model=model or "prisma-v2.5",
                           files={"audio_file": ("turn.wav", wav, "audio/wav")}, data=data)
        if r.status_code != 200:
            raise explain(r)
        b = r.json()
        if not b.get("success", True) or "transcript" not in b:
            raise explain(r)
        return STTResult(text=(b.get("transcript") or "").strip(), lang=b.get("detected_language_code"),
                         ms=ms, request_id=b.get("request_id"), model=b.get("model") or model,
                         truncated=bool(b.get("truncated")), context_used=used)
