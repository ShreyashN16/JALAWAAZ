"""Village gazetteer matching (second line of defence after Prisma keyterms).

Score >= accept (88): accept.  confirm (70) <= score < accept: ask the caller to confirm.
Below confirm: ask again. Thresholds are prototype assumptions (data/config.json).
Uses rapidfuzz when installed; otherwise a pure-Python scorer with the same definitions.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

try:  # pragma: no cover - exercised on machines with rapidfuzz installed
    from rapidfuzz import fuzz as _rf

    def ratio(a: str, b: str) -> float:
        return float(_rf.ratio(a, b))

    def token_set_ratio(a: str, b: str) -> float:
        return float(_rf.token_set_ratio(a, b))
    BACKEND = "rapidfuzz"
except ImportError:
    BACKEND = "difflib"

    def ratio(a: str, b: str) -> float:
        if not a and not b:
            return 100.0
        return 100.0 * SequenceMatcher(None, a, b).ratio()

    def token_set_ratio(a: str, b: str) -> float:
        ta, tb = set(a.split()), set(b.split())
        if not ta or not tb:
            return 0.0
        inter = " ".join(sorted(ta & tb))
        da, db = " ".join(sorted(ta - tb)), " ".join(sorted(tb - ta))
        sa, sb = (inter + " " + da).strip(), (inter + " " + db).strip()
        if inter and (not da or not db):
            return 100.0
        return max(ratio(inter, sa) if inter else 0, ratio(inter, sb) if inter else 0, ratio(sa, sb))

SUFFIXES = sorted(["मध्ये", "मधे", "मधील", "मधला", "पासून", "हून", "च्या", "ला", "ात", "त", "चा", "ची", "चे",
                   "में", "का", "की", "के", "से", "madhe", "madhye", "madhla", "la", "mein", "me", "mai",
                   "ka", "ki", "ke", "cha", "chi", "che", "chya", "at", "gavat"], key=len, reverse=True)
STOP = {"गाव", "गावात", "गावामध्ये", "गाँव", "gaon", "gav", "gaav", "village", "taluka", "तालुका",
        "जिल्हा", "जिला", "district", "मध्ये", "में", "madhe", "mein", "aahe", "आहे", "hai", "है"}
TOK = re.compile(r"[A-Za-z]+|[ऀ-ॣॱ-ॿ‌‍]+")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "").lower()).replace("़", "").replace("ँ", "ं")
    return s.replace("‌", "").replace("‍", "")


def strip_suffix(tok: str) -> str:
    for suf in SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)]
    return tok


def _choices(villages: list[dict]) -> dict[str, dict]:
    out = {}
    for v in villages:
        for n in [v["name"], *v.get("variants", [])]:
            if n:
                out[norm(n)] = v
    return out


def match_village(mention: str | None, villages: list[dict], accept: float = 88, confirm: float = 70):
    """Match an extracted village mention. Returns (village | None, score, mode accept|confirm|ask)."""
    if not mention or not villages:
        return None, 0.0, "ask"
    toks = [t for t in TOK.findall(norm(mention)) if t not in STOP]
    m = " ".join(strip_suffix(t) for t in toks)
    raw = " ".join(toks)                      # names that end like a suffix (खडकवासला ends in -ला)
    if not m:
        return None, 0.0, "ask"
    best_v, best = None, 0.0
    for name, v in _choices(villages).items():
        s = max(token_set_ratio(m, name), ratio(m, name), ratio(raw, name))
        if s > best:
            best_v, best = v, s
    if best >= accept:
        return best_v, round(best, 1), "accept"
    if best >= confirm:
        return best_v, round(best, 1), "confirm"
    return None, round(best, 1), "ask"


def find_in_text(text: str, villages: list[dict], accept: float = 88, confirm: float = 70):
    """Scan a whole transcript (1-3 word windows) for the best village. Same return shape."""
    raw = [t for t in TOK.findall(norm(text)) if t not in STOP]
    toks = [strip_suffix(t) for t in raw]
    if not toks or not villages:
        return None, 0.0, "ask"
    choices = _choices(villages)
    best_v, best = None, 0.0
    for n in (1, 2, 3):
        for i in range(len(toks) - n + 1):
            spans = {" ".join(toks[i:i + n]), " ".join(raw[i:i + n])}   # with and without suffix stripping
            for span in spans:
                if len(span) < 4:
                    continue
                for name, v in choices.items():
                    if abs(len(name) - len(span)) > max(4, len(name) // 2):
                        continue
                    s = ratio(span, name)
                    if s > best:
                        best_v, best = v, s
    if best >= accept:
        return best_v, round(best, 1), "accept"
    if best >= confirm:
        return best_v, round(best, 1), "confirm"
    return None, round(best, 1), "ask"


def keyterms(villages: list[dict], extra: list[str] | None = None, limit: int = 200) -> list[str]:
    """Village names and variants for Prisma `keyterms` (max 200 items)."""
    terms: list[str] = []
    for v in villages:
        terms.append(v["name"])
        terms.extend(v.get("variants", []))
    terms.extend(extra or [])
    return list(dict.fromkeys(t for t in terms if t))[:limit]
