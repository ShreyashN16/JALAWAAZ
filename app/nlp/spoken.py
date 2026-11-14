"""Numbers as spoken words, for Timbre.

Gnani's TTS reference asks for numbers to be written as words, and digit runs of some lengths are
read digit by digit while others are read as quantities. To make every reading predictable:
- quantities (days, households) are written as words: 40 -> "चाळीस" (mr) / "चालीस" (hi);
- ticket references are written one digit word at a time with commas: 44712 -> "चार, चार, सात, एक, दोन".
The 1-100 words reuse the tables in numbers.py (also used to *parse* numbers), so speaking and
hearing agree. Native-speaker review is still required (docs/TESTING.md).
"""
from __future__ import annotations

from .numbers import HI_DEV, MR_DEV

DIGITS = {
    "mr": ["शून्य", "एक", "दोन", "तीन", "चार", "पाच", "सहा", "सात", "आठ", "नऊ"],
    "hi": ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ"],
}
_MR = dict(enumerate(MR_DEV, start=1))          # 1..100
_HI = dict(enumerate(HI_DEV, start=1))
MR_HUNDREDS = {1: "एकशे", 2: "दोनशे", 3: "तीनशे", 4: "चारशे", 5: "पाचशे", 6: "सहाशे", 7: "सातशे", 8: "आठशे", 9: "नऊशे"}


def _base(lang: str) -> str:
    return "mr" if lang == "mr" else "hi"


def number_words(n: int, lang: str) -> str:
    """0..99,999 as words. Larger numbers fall back to digits (Timbre normalises them)."""
    n = int(n)
    L = _base(lang)
    if n < 0 or n > 99_999:
        return str(n)
    if n == 0:
        return DIGITS[L][0]
    table = _MR if L == "mr" else _HI
    parts: list[str] = []
    th, rest = divmod(n, 1000)
    if th:
        parts.append(f"{table[th]} {'हजार' if L == 'mr' else 'हज़ार'}")
    h, below = divmod(rest, 100)
    if h:
        if L == "mr":
            parts.append("शंभर" if (h == 1 and below == 0 and not th) else MR_HUNDREDS[h])
        else:
            parts.append("सौ" if (h == 1 and below == 0 and not th) else f"{table[h]} सौ")
    if below:
        parts.append(table[below])
    return " ".join(parts)


def digit_words(ref: str, lang: str) -> str:
    """'44712' -> 'चार, चार, सात, एक, दोन' (one digit at a time, with pauses)."""
    L = _base(lang)
    return ", ".join(DIGITS[L][int(ch)] for ch in str(ref) if ch.isdigit())
