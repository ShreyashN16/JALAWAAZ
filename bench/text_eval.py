"""Text evaluation of the language layer from the command line (no Gnani credits).

  python -m bench.text_eval

Same code as the "Run now" button on /metrics (app/services/evaluation.py). Writes
bench/results/text_eval.json and prints accuracy per field with n, plus every failing case.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.services import evaluation  # noqa: E402


def main() -> None:
    db.init_db()
    r = asyncio.run(evaluation.run())
    print(f"{r['n_cases']} cases, extractor: {r['extractor']}. {r['note']}\n")
    print(f"{'field':<22}{'accuracy':>10}{'n':>6}{'rules only':>12}")
    for k, a in r["fields"].items():
        b = r["rules_baseline"][k]
        print(f"{k:<22}{(a['rate'] or 0) * 100:>9.1f}%{a['n']:>6}{(b['rate'] or 0) * 100:>11.1f}%")
    for name, st in r["sets"].items():
        a = st["required_fields_all_correct"]
        print(f"{name:<11} village + source + fault all correct: {a['correct']}/{a['n']}")
    if r["failures"]:
        print(f"\n{len(r['failures'])} failing cases:")
        for f in r["failures"]:
            print(f"  [{f['set']}] {f['id']:<10} " + "; ".join(f"{w['field']}: expected {w['expected']}, got {w['got']}" for w in f["wrong"]))
    print("\nWrote bench/results/text_eval.json")


if __name__ == "__main__":
    main()
