"""Pre-record every fixed prompt (greeting, questions, closing lines) in all three languages.

  python -m scripts.warm_tts          # lists what would be synthesised and asks before spending credits
  python -m scripts.warm_tts --yes    # no prompt

Each fixed sentence is synthesised once and kept in tts_cache/, so during a demo those replies play
immediately and cost nothing. Sentences that contain caller details (read-backs, ticket numbers) are
never cached. Re-run after changing GNANI_TTS_MODEL, the voices, TTS_FORMAT or tts.speed.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.core import templates as tpl  # noqa: E402
from app.gnani.client import GnaniError  # noqa: E402
from app.gnani.timbre import Timbre, check_voice_config  # noqa: E402


async def main(yes: bool) -> int:
    db.init_db()
    if not settings.GNANI_API_KEY:
        print("GNANI_API_KEY is empty in .env."); return 1
    if (msg := check_voice_config()):
        print(msg); return 1
    t = Timbre()
    todo = []
    for key in tpl.STATIC_KEYS:
        for lang in ("mr", "hi", "hinglish"):
            text = tpl.t(key, lang)
            if t.cached(text.speech, lang) is None:
                todo.append((key, lang, text))
    todo = list({(k, l): (k, l, x) for k, l, x in todo}.values())
    if not todo:
        print("Every fixed prompt is already cached for this model, voice and format."); return 0
    print(f"{len(todo)} prompts to synthesise with {settings.GNANI_TTS_MODEL} ({settings.TTS_VOICE_MR}/{settings.TTS_VOICE_HI}, {settings.TTS_FORMAT}).")
    if not yes and input("Spend credits on these now? [y/N] ").strip().lower() != "y":
        return 0
    done = 0
    for key, lang, text in todo:
        try:
            await t.speak(text.speech, lang, cache=True)
            done += 1
            print(f"  ok   {key:<16} {lang}")
        except GnaniError as e:
            print(f"  fail {key:<16} {lang}: {e}")
            if e.status in (401, 402, 403):
                break
    print(f"Cached {done} of {len(todo)} prompts in {settings.TTS_CACHE_DIR}.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().yes)))
