"""Yes / no parsing for Marathi, Hindi, Hinglish and English.

Explicit answer words decide first. For verification calls, content words also count
("चालू झाला" = working, "अजून बंद" = still broken). A NO word wins over a working word
("chalu nahi"); a YES word with a broken word ("haan, abhi bhi band hai") is unclear -> ask again.
"""
from __future__ import annotations

import re

YES = {"ho", "hoy", "haan", "han", "ha", "haa", "haanji", "ji", "jee", "barobar", "bilkul", "sahi", "theek",
       "thik", "yes", "yeah", "yep", "y", "ok", "okay", "correct", "right",
       "हो", "होय", "हाँ", "हां", "हा", "जी", "बरोबर", "बिलकुल", "बिल्कुल", "सही", "ठीक", "होय़"}
NO = {"nahi", "nahin", "nai", "nako", "na", "no", "nope", "naa", "galat", "chuk", "chukicha", "chukiche",
      "wrong", "नाही", "नहीं", "नही", "ना", "नको", "गलत", "चूक", "चुकीचे", "चुकीचा", "चुकीची"}
WORKING = {"chalu", "chaalu", "sur", "suru", "chalto", "chalte", "chalta", "aata", "yetay", "yete", "aa", "raha",
           "working", "fixed", "running", "चालू", "सुरू", "सुरु", "येतंय", "येते", "आलं", "आले", "चल", "रहा", "आ"}
BROKEN = {"band", "bandh", "ajun", "ajunhi", "abhi", "bhi", "still", "kharab", "broken", "same",
          "बंद", "अजून", "अजूनही", "अभी", "भी", "खराब", "तसाच", "वैसा"}
TOK = re.compile(r"[A-Za-z]+|[ऀ-ॣॱ-ॿ]+")


def _toks(text: str) -> set[str]:
    return {t.lower() for t in TOK.findall(text or "")}


def parse_yes_no(text: str, verify: bool = False) -> bool | None:
    t = _toks(text)
    y, n = bool(t & YES), bool(t & NO)
    if y and not n:
        if verify and (t & {"band", "bandh", "बंद", "kharab", "खराब", "still", "ajun", "अजून"}):
            return None
        return True
    if n and not y:
        return False
    if y and n:
        if t & YES <= {"ji", "jee", "जी"}:      # "ji nahi" = polite no
            return False
        return None
    if verify:
        w = bool(t & WORKING)
        b = bool(t & {"band", "bandh", "बंद", "kharab", "खराब", "broken", "still", "ajun", "अजून", "अजूनही", "तसाच"})
        if w and not b:
            return True
        if b and not w:
            return False
    return None
