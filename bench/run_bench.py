"""Benchmark runner. Writes per-item rows to bench/results/rows.jsonl, then calls report.py.

Two modes:
  python -m bench.run_bench --text-only      # gold transcripts -> normaliser, gazetteer, extraction,
                                             # priority. No Gnani credits. Measures the language layer.
  python -m bench.run_bench                  # real Prisma on every derived clip (make_noisy first),
                                             # then the same pipeline. Spends credits; results cached.
Options: --format verbatim (ablation), --no-keyterms (ablation), --limit N.

gold.csv columns: file,lang,source,transcript,village,source_type,fault,duration_days,households,
drinking_source,priority   (source = real | synthetic; priority optional, hand-labelled)
STT results are cached in bench/results/stt_cache.jsonl keyed by audio hash + settings, so a re-run
never pays twice for the same request.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import glob
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.core.priority import compute_priority  # noqa: E402
from app.gnani import providers  # noqa: E402
from app.gnani.prisma import Prisma  # noqa: E402
from app.nlp import extract as ex  # noqa: E402
from app.nlp.gazetteer import find_in_text, keyterms, match_village  # noqa: E402
from bench.wer import wer  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
CODE = {"mr": "mr-IN", "hi": "hi-IN", "hinglish": "hi-IN,en-IN"}


def load_gold(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("file") and not r["file"].startswith("#")]


def _int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


def _bool(v):
    return {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}.get(str(v).strip().lower())


def _cache_get(key):
    p = os.path.join(RES, "stt_cache.jsonl")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            j = json.loads(line)
            if j["key"] == key:
                return j
    return None


def _cache_put(row):
    with open(os.path.join(RES, "stt_cache.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def evaluate(text: str, gold: dict, villages: list, llm) -> dict:
    t0 = time.perf_counter()
    r, meta = await ex.extract(text, None, llm)
    ext_ms = (time.perf_counter() - t0) * 1000
    v, score, mode = match_village(r.get("village"), villages) if r.get("village") else (None, 0, "ask")
    v2, s2, m2 = find_in_text(text, villages)
    if s2 > score:
        v, score, mode = v2, s2, m2
    rules, _ = await ex.extract(text, None, None)
    out = {"extraction_source": meta["source"], "extract_ms": round(ext_ms, 1),
           "village_pred": v["name"] if v and mode == "accept" else None, "village_mode": mode, "village_score": score}
    for f, gk in (("source_type", "source_type"), ("fault", "fault"), ("duration_days", "duration_days"),
                  ("households_affected", "households"), ("drinking_source", "drinking_source")):
        out[f + "_pred"] = r.get(f)
        out[f + "_rules"] = rules.get(f)
    out["gold_village"] = gold.get("village") or None
    out["gold"] = {"source_type": gold.get("source_type") or None, "fault": gold.get("fault") or None,
                   "duration_days": _int(gold.get("duration_days")), "households_affected": _int(gold.get("households")),
                   "drinking_source": _bool(gold.get("drinking_source"))}
    if gold.get("priority"):
        p, _ = compute_priority(r, False, 0, settings.cfg)
        out["priority_pred"], out["priority_gold"] = p, _int(gold["priority"])
    return out


async def main(a):
    db.init_db()
    os.makedirs(RES, exist_ok=True)
    gold = load_gold(a.gold)[: a.limit or None]
    con = db.connect()
    villages = db.villages(con)
    con.close()
    llm = await providers.llm()
    rows = []
    if a.text_only:
        for g in gold:
            row = {"file": g["file"], "lang": g["lang"], "source": g["source"], "condition": "gold-text",
                   "ref": g["transcript"], "hyp": g["transcript"], "wer": None}
            row.update(await evaluate(g["transcript"], g, villages, llm))
            rows.append(row)
    else:
        stt = Prisma(fmt=a.format)
        if not settings.GNANI_API_KEY:
            sys.exit("GNANI_API_KEY is empty. Use --text-only or fill .env.")
        kt = [] if a.no_keyterms else keyterms(villages)
        for g in gold:
            stem = os.path.splitext(g["file"])[0]
            files = sorted(glob.glob(os.path.join(HERE, "clips", "derived", f"{stem}__*.wav")))
            if not files:
                print(f"  no derived audio for {g['file']} (run python -m bench.make_noisy)")
            for f in files:
                cond = os.path.basename(f).split("__", 1)[1][:-4]
                audio = open(f, "rb").read()
                key = hashlib.sha256(audio).hexdigest()[:20] + f"|{CODE.get(g['lang'], 'hi-IN')}|{a.format}|{int(not a.no_keyterms)}"
                hit = _cache_get(key)
                if hit is None:
                    try:
                        r = await stt.transcribe(audio, CODE.get(g["lang"], "hi-IN"), kt)
                        hit = {"key": key, "text": r.text, "lang": r.lang, "ms": round(r.ms, 1), "ok": True}
                    except Exception as e:  # recorded as a failure row, never hidden
                        hit = {"key": key, "text": "", "lang": None, "ms": None, "ok": False, "error": str(e)[:200]}
                    _cache_put(hit)
                row = {"file": g["file"], "lang": g["lang"], "source": g["source"], "condition": cond,
                       "ref": g["transcript"], "hyp": hit["text"], "stt_ok": hit["ok"], "stt_ms": hit["ms"],
                       "detected": hit["lang"], "wer": wer(g["transcript"], hit["text"]) if hit["ok"] else None,
                       "format": a.format, "keyterms": not a.no_keyterms}
                row.update(await evaluate(hit["text"], g, villages, llm))
                rows.append(row)
                print(f"  {g['file']:<24} {cond:<16} WER {row['wer'] if row['wer'] is not None else 'ERR'}")
    tag = "text" if a.text_only else f"audio_{a.format}_{'kt' if not a.no_keyterms else 'nokt'}"
    with open(os.path.join(RES, f"rows_{tag}.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows -> bench/results/rows_{tag}.jsonl")
    from bench import report
    report.main()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=os.path.join(HERE, "clips", "gold.csv"))
    ap.add_argument("--text-only", action="store_true")
    ap.add_argument("--format", default="transcribe", choices=["transcribe", "verbatim"])
    ap.add_argument("--no-keyterms", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    asyncio.run(main(ap.parse_args()))
