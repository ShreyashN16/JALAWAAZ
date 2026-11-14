"""Word error rate with documented normalisation (used when jiwer is not installed; identical maths).

Normalisation before scoring (applied to reference and hypothesis alike):
  lowercase; Unicode NFC; nukta and candrabindu folded; Devanagari digits -> ASCII;
  punctuation (including । ॥ , . ? !) removed; whitespace collapsed.
WER = (substitutions + deletions + insertions) / reference words.
"""
from __future__ import annotations

import re
import unicodedata

_DEV = str.maketrans("०१२३४५६७८९", "0123456789")
_PUNCT = re.compile(r"[।॥,.;:!?\"'()\[\]{}\-–—/\\]")


def norm(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", (s or "").lower()).translate(_DEV)
    s = s.replace("़", "").replace("ँ", "ं")
    s = _PUNCT.sub(" ", s)
    return s.split()


def edits(ref: list[str], hyp: list[str]) -> int:
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def wer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    return edits(r, h) / len(r)


def corpus_wer(pairs: list[tuple[str, str]]) -> float:
    errs = sum(edits(norm(r), norm(h)) for r, h in pairs)
    words = sum(len(norm(r)) for r, _ in pairs)
    return errs / words if words else 0.0
