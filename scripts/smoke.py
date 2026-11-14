"""Smoke test against the REAL Gnani APIs (and your Evon server if enabled). Spends a few credits.

  python -m scripts.smoke              # about 8 requests: key check, Timbre (file, stream, phone line),
                                       # Prisma on Timbre's own audio with and without context hints, Evon
  python -m scripts.smoke --models     # also compare timbre-v3.0 and timbre-v2.5 voices
  python -m scripts.smoke --samples    # also transcribe your recordings in samples/ (mr.*, hi.*, hinglish.*)

No recordings are needed: Timbre speaks a Marathi complaint, then Prisma transcribes that audio, so
one run checks both directions. Audio files are written to samples/ for a native speaker to review.
Every request is logged in the api_calls table (status and latency only).
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.audio import to_wav16k  # noqa: E402
from app.config import settings  # noqa: E402
from app.core import templates as tpl  # noqa: E402
from app.gnani import providers  # noqa: E402
from app.gnani.base import STTContext  # noqa: E402
from app.gnani.client import GnaniError  # noqa: E402
from app.gnani.evon import Evon, EvonError  # noqa: E402
from app.gnani.prisma import Prisma  # noqa: E402
from app.gnani.timbre import Timbre, check_voice_config  # noqa: E402
from app.nlp import extract as ex  # noqa: E402
from app.services.pipeline import CallContext, stt_context  # noqa: E402

SENTENCE = "शिवापूर मध्ये हातपंप तीन दिवसांपासून बंद आहे, चाळीस घरांना पाणी नाही."
OUT = "samples"
results: list[tuple[str, bool, str]] = []


def ok(name, msg):
    results.append((name, True, msg)); print(f"  \033[32mOK\033[0m   {name}: {msg}")


def bad(name, msg):
    results.append((name, False, msg)); print(f"  \033[31mFAIL\033[0m {name}: {msg}")


def save(name: str, data: bytes) -> str:
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with open(p, "wb") as f:
        f.write(data)
    return p


async def main(a) -> int:
    db.init_db()
    if not settings.GNANI_API_KEY:
        print("GNANI_API_KEY is empty. Put your key in .env (create it at app.gnani.ai) and run again.")
        return 1
    if (msg := check_voice_config()):
        print("Voice configuration problem:", msg); return 1

    print("\n[1] Key")
    r = await providers.check_gnani()
    (ok if r["ok"] else bad)("key check", r["message"] + (f" ({r.get('ms')} ms)" if r.get("ms") else ""))
    if not r["ok"]:
        return 1

    print(f"\n[2] Timbre {settings.GNANI_TTS_MODEL}, voice {settings.TTS_VOICE_MR}")
    t = Timbre()
    mp3 = b""
    try:
        res = await t.speak(SENTENCE, "mr")
        mp3 = res.audio
        ok("file (REST)", f"{len(res.audio)} bytes {res.mime} in {res.ms:.0f} ms -> {save('smoke_mr.' + ('mp3' if 'mpeg' in res.mime else 'wav'), res.audio)}")
    except GnaniError as e:
        bad("file (REST)", f"{e} {e.user_hint}")
    stats: dict = {}
    t0 = time.perf_counter()
    try:
        chunks = [c async for c in t.stream(SENTENCE, "mr", stats=stats)]
        total = (time.perf_counter() - t0) * 1000
        mode = stats.get("mode")
        msg = f"{len(chunks)} chunks, first audio after {stats.get('ttfb_ms', 0):.0f} ms, all audio after {total:.0f} ms (mode {mode})"
        if stats.get("stream_fallback"):
            msg += f"; stream failed ({stats['stream_fallback']}), REST was used"
        (ok if mode == "stream" else bad)("stream (SSE)", msg)
        save("smoke_mr_stream.mp3", b"".join(chunks))
    except GnaniError as e:
        bad("stream (SSE)", str(e))
    try:
        res = await t.speak(SENTENCE, "mr", telephone=True)
        ok("phone line (mu-law 8 kHz)", f"{len(res.audio)} bytes WAV -> {save('smoke_mr_8khz.wav', res.audio)}")
    except GnaniError as e:
        bad("phone line (mu-law 8 kHz)", str(e))
    ticket = tpl.t("ticket", "mr", digits=tpl.digits("40712", "mr"))
    try:
        res = await t.speak(ticket.speech, "mr")
        ok("ticket number read digit by digit", f"-> {save('smoke_ticket_mr.mp3', res.audio)} (listen: 'चार, शून्य, सात, एक, दोन')")
    except GnaniError as e:
        bad("ticket number", str(e))

    if a.models:
        for model, voice in (("timbre-v3.0", "Kalpana"), ("timbre-v2.5", "Zahira")):
            old = settings.GNANI_TTS_MODEL, settings.TTS_VOICE_MR
            settings.GNANI_TTS_MODEL, settings.TTS_VOICE_MR = model, voice
            try:
                res = await Timbre().speak(SENTENCE, "mr")
                ok(f"{model} {voice}", f"-> {save(f'smoke_mr_{model}_{voice}.mp3', res.audio)}")
            except GnaniError as e:
                bad(f"{model} {voice}", str(e))
            settings.GNANI_TTS_MODEL, settings.TTS_VOICE_MR = old

    print(f"\n[3] Prisma {settings.GNANI_STT_MODEL} on Timbre's audio")
    if mp3:
        wav = to_wav16k(mp3)
        entry = {"sess": {"last_question": tpl.t("greet", "mr")}}
        ctx = stt_context(entry, CallContext(entry))
        for label, c in (("no context", STTContext()), ("with keyterms + topic + previous_text", ctx)):
            try:
                r = await Prisma().transcribe(wav, "mr-IN", None, c)
                fields, _ = await ex.extract(r.text, None, None)
                ok(label, f"{r.text!r} | detected {r.lang} | {r.ms:.0f} ms | extracted: {fields.get('source_type')}, "
                          f"{fields.get('fault')}, {fields.get('duration_days')} days, {fields.get('households_affected')} households")
            except GnaniError as e:
                bad(label, f"{e} {e.user_hint}")
    if a.samples:
        for f in sorted(glob.glob(os.path.join(OUT, "*.*"))):
            stem = os.path.basename(f).split(".")[0]
            if stem not in ("mr", "hi", "hinglish", "auto"):
                continue
            code = {"mr": "mr-IN", "hi": "hi-IN", "hinglish": "hi-IN,en-IN", "auto": "indic-auto"}[stem]
            try:
                r = await Prisma().transcribe(to_wav16k(open(f, "rb").read()), code)
                ok(f"sample {f}", f"{r.text!r} | detected {r.lang} | {r.ms:.0f} ms")
            except GnaniError as e:
                bad(f"sample {f}", str(e))

    print("\n[4] Evon")
    if not settings.EVON_ENABLED:
        print("  skip EVON_ENABLED=0 (rule-based extraction is used)")
    else:
        try:
            t0 = time.perf_counter()
            out = await Evon().complete(ex.SYSTEM_PROMPT, "Transcript: " + SENTENCE, 300)
            obj = ex.parse_json(out)
            (ok if obj else bad)("JSON extraction", f"{(time.perf_counter() - t0) * 1000:.0f} ms -> {obj if obj else out[:200]}")
        except EvonError as e:
            bad("Evon", f"{e} (start your vLLM/SGLang server or set EVON_ENABLED=0)")

    n_ok = sum(1 for _, good, _ in results if good)
    print(f"\n{n_ok}/{len(results)} checks passed. Note your credit balance at app.gnani.ai before and after to "
          "measure credits per request (docs/costs.md).")
    return 0 if n_ok == len(results) else 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", action="store_true", help="compare timbre-v3.0 and timbre-v2.5")
    ap.add_argument("--samples", action="store_true", help="also transcribe recordings in samples/")
    sys.exit(asyncio.run(main(ap.parse_args())))
