"""Check that this machine can run Jal Awaaz, and say how to fix anything that is missing.

  python -m scripts.doctor            # offline checks only (no credits)
  python -m scripts.doctor --online   # also validate the Gnani key with a metadata request

Exit code 0 when everything needed for the demo is in place.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import shutil
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, WARN, FAIL = "\033[32mOK  \033[0m", "\033[33mWARN\033[0m", "\033[31mFAIL\033[0m"
problems = 0


def line(status, what, how=""):
    global problems
    if status == FAIL:
        problems += 1
    print(f"  {status} {what}" + (f"\n         -> {how}" if how else ""))


def main(online: bool) -> int:
    print("\nPython and packages")
    v = sys.version_info
    line(PASS if v >= (3, 10) else FAIL, f"Python {v.major}.{v.minor}.{v.micro}", "" if v >= (3, 10) else "Install Python 3.10 or newer")
    for mod, pip, needed in (("starlette", "starlette", True), ("uvicorn", "uvicorn[standard]", True), ("pydantic", "pydantic", True),
                             ("multipart", "python-multipart", True), ("itsdangerous", "itsdangerous", True),
                             ("httpx", "httpx", True), ("rapidfuzz", "rapidfuzz", False), ("numpy", "numpy", False),
                             ("pytest", "pytest", False)):
        try:
            importlib.import_module(mod)
            try:
                from importlib.metadata import version
                ver = version(pip.split("[")[0])
            except Exception:
                ver = ""
            line(PASS, f"{pip} {ver}".strip())
        except ImportError:
            if mod == "httpx":
                try:
                    importlib.import_module("httpx2"); line(WARN, "httpx missing; httpx2 fallback in use", "pip install httpx"); continue
                except ImportError:
                    pass
            line(FAIL if needed else WARN, f"{pip} not installed", f"pip install {pip}" + ("" if needed else "  (optional)"))

    from app.audio import get_ffmpeg_binary
    from app.config import ROOT, settings
    print("\nAudio")
    ff = get_ffmpeg_binary()
    line(PASS if ff else FAIL, f"ffmpeg: {ff or 'not found'}", "" if ff else "pip install imageio-ffmpeg  (or install ffmpeg and add it to PATH)")

    print("\nConfiguration (.env)")
    env = ROOT / ".env"
    line(PASS if env.exists() else WARN, ".env present" if env.exists() else ".env missing",
         "" if env.exists() else "Copy .env.example to .env and fill it in")
    line(PASS if settings.GNANI_API_KEY else WARN, "GNANI_API_KEY " + ("set (not shown)" if settings.GNANI_API_KEY else "empty"),
         "" if settings.GNANI_API_KEY else "Without it the phone uses typed answers and the browser voice")
    for name in settings.defaults_in_use:
        line(WARN, f"{name} is still the example value", "Set your own value in .env before showing anyone")
    from app.gnani.timbre import check_voice_config
    vc = check_voice_config()
    line(FAIL if vc else PASS, vc or f"Timbre {settings.GNANI_TTS_MODEL}, voices {settings.TTS_VOICE_MR}/{settings.TTS_VOICE_HI} match the model",
         "Pick voices from docs/GNANI_INTEGRATION.md for this model" if vc else "")
    line(PASS, f"Mode: {'demo (time compressed)' if settings.DEMO_MODE else 'real timings'}; voice format {settings.TTS_FORMAT}"
               f"{', streamed' if settings.TTS_STREAMING else ''}")

    print("\nData")
    from app import db
    try:
        db.init_db()
        con = db.connect()
        n = con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        vs = con.execute("SELECT COUNT(*), SUM(lat IS NOT NULL) FROM villages").fetchone()
        con.close()
        line(PASS, f"Database {settings.DB_PATH}: {n} tickets, {vs[0]} villages ({vs[1]} on the map)")
    except Exception as e:
        line(FAIL, f"Database: {e}", "Check DB_PATH in .env and that the folder is writable")
    cache = settings.TTS_CACHE_DIR
    line(PASS if os.path.isdir(cache) or not os.path.exists(cache) else WARN, f"TTS cache folder {cache}")

    print("\nServices")
    if settings.EVON_ENABLED:
        from app.gnani.evon import Evon
        up = asyncio.run(Evon().ping())
        line(PASS if up else WARN, f"Evon at {settings.EVON_BASE_URL} " + ("answers" if up else "not reachable"),
             "" if up else "Start your vLLM/SGLang server, or set EVON_ENABLED=0 to use the rule-based extractor (labelled in the UI)")
    else:
        line(PASS, "Evon disabled: rule-based extraction (labelled in the UI)")
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", 8000)); line(PASS, "Port 8000 is free")
    except OSError:
        line(WARN, "Port 8000 is in use", "Is Jal Awaaz already running? Or start it with --port 8001")
    finally:
        s.close()
    if online:
        from app.gnani import providers
        r = asyncio.run(providers.check_gnani())
        line(PASS if r["ok"] else FAIL, f"Gnani key check: {r['message']}", r.get("hint", "") if not r["ok"] else "")

    print("\n" + ("Ready. Start with:  uvicorn app.main:app --host 0.0.0.0 --port 8000" if not problems
                  else f"{problems} problem(s) to fix first."))
    return 0 if not problems else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", action="store_true", help="validate the Gnani key (one metadata request)")
    sys.exit(main(ap.parse_args().online))
