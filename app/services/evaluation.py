"""In-app text evaluation of the language layer (no Gnani credits are spent).

Two sets, always reported separately:
- regression: bench/text_cases.csv plus the transcripts in bench/clips/gold.csv. The rules were
  adjusted after earlier runs on this set, so it guards against regressions; it is not a fair test.
- held-out: bench/text_cases_holdout.csv, written once and never used to tune the rules.
Every case runs
through the same code a call uses: number normaliser -> extraction (Evon when served, else rules) ->
validators -> gazetteer -> priority. Reports accuracy per field and per language WITH n, the
rule-only baseline next to it, and every failing case. Results are measured, never typed in.
Audio benchmarks (Prisma WER on recorded clips) stay in bench/run_bench.py because they cost credits.
"""
from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from datetime import datetime, timezone

from .. import db
from ..config import ROOT
from ..gnani import providers
from ..nlp import extract as ex
from ..nlp.gazetteer import find_in_text, match_village

FIELDS = ["village", "source_type", "fault", "duration_days", "households_affected", "drinking_source"]
OUT = ROOT / "bench" / "results" / "text_eval.json"


def _int(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


def _bool(v):
    return {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}.get(str(v or "").strip().lower())


def load_cases() -> list[dict]:
    cases = []
    for fname, set_name in (("text_cases.csv", "regression"), ("text_cases_holdout.csv", "held-out")):
        p = ROOT / "bench" / fname
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cases.append({"id": r["id"], "lang": r["lang"], "source": r.get("source") or "synthetic", "set": set_name,
                              "text": r["transcript"], "gold": {
                                  "village": r.get("village") or None, "source_type": r.get("source_type") or None,
                                  "fault": r.get("fault") or None, "duration_days": _int(r.get("duration_days")),
                                  "households_affected": _int(r.get("households")),
                                  "drinking_source": _bool(r.get("drinking_source"))}})
    g = ROOT / "bench" / "clips" / "gold.csv"
    if g.exists():
        with open(g, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r.get("file") or r["file"].startswith("#"):
                    continue
                cases.append({"id": "gold:" + r["file"], "lang": r["lang"], "source": r.get("source") or "synthetic", "set": "regression",
                              "text": r["transcript"], "gold": {
                                  "village": r.get("village") or None, "source_type": r.get("source_type") or None,
                                  "fault": r.get("fault") or None, "duration_days": _int(r.get("duration_days")),
                                  "households_affected": _int(r.get("households")),
                                  "drinking_source": _bool(r.get("drinking_source"))}})
    return cases


def _village(text: str, mention: str | None, villages: list[dict]) -> str | None:
    v, score, mode = match_village(mention, villages) if mention else (None, 0, "ask")
    v2, s2, m2 = find_in_text(text, villages)
    if s2 > score:
        v, score, mode = v2, s2, m2
    return v["name"] if v and mode == "accept" else None


async def run() -> dict:
    con = db.connect()
    try:
        villages = db.villages(con)
    finally:
        con.close()
    llm = await providers.llm()
    cases = load_cases()
    rows = []
    t_start = time.perf_counter()
    for c in cases:
        t0 = time.perf_counter()
        pred, meta = await ex.extract(c["text"], None, llm)
        ms = (time.perf_counter() - t0) * 1000
        rules = pred if llm is None else (await ex.extract(c["text"], None, None))[0]
        p = {f: pred.get(f) for f in FIELDS}
        r = {f: rules.get(f) for f in FIELDS}
        p["village"] = _village(c["text"], pred.get("village"), villages)
        r["village"] = _village(c["text"], rules.get("village"), villages)
        rows.append({**c, "pred": p, "rules": r, "extraction_source": meta["source"], "ms": round(ms, 1)})
    total_ms = (time.perf_counter() - t_start) * 1000

    def acc(rs, key):
        out = {}
        for f in FIELDS:
            pairs = [(x[key][f], x["gold"][f]) for x in rs if x["gold"][f] is not None]
            ok = sum(1 for a, b in pairs if a == b)
            out[f] = {"correct": ok, "n": len(pairs), "rate": round(ok / len(pairs), 3) if pairs else None}
        return out

    by_lang = defaultdict(list)
    for x in rows:
        by_lang[x["lang"]].append(x)

    def all_right(rs):
        ok = [x for x in rs if all(x["pred"][f] == x["gold"][f] for f in ("village", "source_type", "fault"))]
        return {"correct": len(ok), "n": len(rs), "rate": round(len(ok) / len(rs), 3) if rs else None}
    complete = [x for x in rows if all(x["pred"][f] == x["gold"][f] for f in ("village", "source_type", "fault"))]
    sets = {}
    for name in ("held-out", "regression"):
        rs = [x for x in rows if x["set"] == name]
        if rs:
            sets[name] = {"n": len(rs), "required_fields_all_correct": all_right(rs), "fields": acc(rs, "pred"),
                          "rules_baseline": acc(rs, "rules")}
    failures = []
    for x in rows:
        wrong = [f for f in FIELDS if x["gold"][f] is not None and x["pred"][f] != x["gold"][f]]
        if wrong:
            failures.append({"id": x["id"], "lang": x["lang"], "text": x["text"], "set": x["set"],
                             "wrong": [{"field": f, "expected": x["gold"][f], "got": x["pred"][f]} for f in wrong]})
    result = {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_cases": len(rows), "sources": sorted({x["source"] for x in rows}),
        "extractor": "evon" if llm is not None else "rules",
        "extraction_sources": {k: sum(1 for x in rows if x["extraction_source"] == k) for k in {x["extraction_source"] for x in rows}},
        "required_fields_all_correct": {"correct": len(complete), "n": len(rows),
                                        "rate": round(len(complete) / len(rows), 3) if rows else None},
        "fields": acc(rows, "pred"), "rules_baseline": acc(rows, "rules"), "sets": sets,
        "by_language": {lang: {"n": len(rs), "fields": acc(rs, "pred")} for lang, rs in sorted(by_lang.items())},
        "median_ms": sorted(x["ms"] for x in rows)[len(rows) // 2] if rows else None,
        "total_ms": round(total_ms),
        "failures": failures,
        "note": "Synthetic text cases written for this prototype (not real callers). Measures the language layer "
                "only: number normaliser, extraction, validators and village matching. No speech recognition. "
                "The regression set was used while improving the rules; the held-out set never was.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def latest() -> dict | None:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None
