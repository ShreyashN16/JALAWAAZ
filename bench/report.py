"""Turn bench/results/rows_*.jsonl into bench/results/latest.json (rendered on /metrics) and latest.md.
Every table carries n. Real and synthetic sources are always reported separately.

  python -m bench.report
"""
from __future__ import annotations

import glob
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
FIELDS = ["source_type", "fault", "duration_days", "households_affected", "drinking_source"]


def pct(x):
    return None if x is None else f"{100 * x:.1f}%"


def acc(rows, pred, gold):
    pairs = [(r[pred], r[gold]) for r in rows if r.get(gold) is not None]
    return (sum(p == g for p, g in pairs) / len(pairs), len(pairs)) if pairs else (None, 0)


def field_acc(rows, field, suffix="_pred"):
    pairs = [(r[field + suffix], r["gold"][field]) for r in rows if r["gold"].get(field) is not None]
    return (sum(p == g for p, g in pairs) / len(pairs), len(pairs)) if pairs else (None, 0)


def main():
    files = sorted(glob.glob(os.path.join(RES, "rows_*.jsonl")))
    if not files:
        print("No rows yet. Run python -m bench.run_bench first."); return
    tables, summary = [], []
    for path in files:
        tag = os.path.basename(path)[5:-6]
        rows = [json.loads(l) for l in open(path, encoding="utf-8")]
        audio = tag != "text"
        summary.append(f"{tag}: {len(rows)} rows")
        if audio:
            g = defaultdict(list)
            for r in rows:
                g[(r["source"], r["lang"], r["condition"])].append(r)
            out = []
            for (src, lang, cond), rs in sorted(g.items()):
                ok = [r for r in rs if r["wer"] is not None]
                from bench.wer import corpus_wer
                cw = corpus_wer([(r["ref"], r["hyp"]) for r in ok]) if ok else None
                ms = [r["stt_ms"] for r in ok if r.get("stt_ms")]
                out.append([src, lang, cond, len(rs), len(rs) - len(ok), pct(cw), round(statistics.median(ms)) if ms else None])
            tables.append({"title": f"Prisma word error rate ({tag})",
                           "columns": ["Source", "Language", "Condition", "n", "API failures", "WER (corpus)", "Median STT ms"],
                           "rows": out, "note": "WER normalisation: see bench/wer.py. Conditions: clean, <noise><snr>db, _tel = 8 kHz mu-law line."})
        for src in sorted({r["source"] for r in rows}):
            rs = [r for r in rows if r["source"] == src]
            body = []
            a, n = acc([dict(r, _vp=r["village_pred"], _vg=r["gold_village"]) for r in rs], "_vp", "_vg")
            body.append(["village (gazetteer, accept only)", pct(a), n, "", ""])
            for f in FIELDS:
                a1, n1 = field_acc(rs, f, "_pred")
                a2, _ = field_acc(rs, f, "_rules")
                body.append([f, pct(a1), n1, pct(a2), ""])
            srcs = defaultdict(int)
            for r in rs:
                srcs[r["extraction_source"]] += 1
            pr = [r for r in rs if r.get("priority_gold") is not None]
            if pr:
                a3 = sum(r["priority_pred"] == r["priority_gold"] for r in pr) / len(pr)
                body.append(["priority (rules on extracted fields)", pct(a3), len(pr), "", ""])
            tables.append({"title": f"Field accuracy, {src} data ({tag})",
                           "columns": ["Field", "Accuracy (pipeline)", "n", "Rule-only baseline"],
                           "rows": [b[:4] for b in body],
                           "note": "Pipeline = Evon when served, else rules. Extraction sources: " +
                                   ", ".join(f"{k} {v}" for k, v in srcs.items())})
            bad = [r for r in rs if r["village_pred"] != r["gold_village"] or
                   any(r[f + "_pred"] != r["gold"][f] for f in FIELDS if r["gold"][f] is not None)]
            if bad:
                tables.append({"title": f"Failure rows, {src} data ({tag}), first 10",
                               "columns": ["File", "Condition", "Heard", "Wrong fields"],
                               "rows": [[r["file"], r["condition"], r["hyp"][:80],
                                         ", ".join([f for f in FIELDS if r["gold"][f] is not None and r[f + "_pred"] != r["gold"][f]] +
                                                   (["village"] if r["village_pred"] != r["gold_village"] else []))]
                                        for r in bad[:10]]})
    out = {"run_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "summary": "; ".join(summary), "tables": tables}
    json.dump(out, open(os.path.join(RES, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(RES, "latest.md"), "w", encoding="utf-8") as f:
        f.write(f"# Jal Awaaz benchmark\n\nRun {out['run_at']}. {out['summary']}\n")
        for t in tables:
            f.write(f"\n## {t['title']}\n\n| " + " | ".join(t["columns"]) + " |\n|" + "---|" * len(t["columns"]) + "\n")
            for r in t["rows"]:
                f.write("| " + " | ".join("" if v is None else str(v) for v in r) + " |\n")
            if t.get("note"):
                f.write(f"\n{t['note']}\n")
    print("Wrote bench/results/latest.json and latest.md")


if __name__ == "__main__":
    main()
