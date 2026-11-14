"""Enum and range checks. Anything out of range becomes None; models never bypass this."""
from __future__ import annotations

import math

SOURCE = {"handpump", "tap", "borewell", "well", "tanker", "tank", "other"}
FAULT = {"no_water", "low_pressure", "leakage", "contamination", "broken_part", "power", "other"}
SYMPT = {"diarrhoea", "vomiting", "fever", "skin", "stomach_pain", "none"}
REQUIRED = ["village", "source_type", "fault"]
OPTIONAL = ["duration_days", "households_affected", "drinking_source", "health_symptoms"]
FIELDS = ["village", "taluka", "district", "source_type", "fault", "duration_days", "households_affected",
          "drinking_source", "health_symptoms", "smell_colour_taste", "language_detected", "evidence_quote"]


def empty_report() -> dict:
    return {f: ([] if f == "health_symptoms" else None) for f in FIELDS}


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def clean(r: dict) -> dict:
    r = {**empty_report(), **{k: v for k, v in (r or {}).items() if k in FIELDS or k.startswith("_")}}
    if r.get("source_type") not in SOURCE:
        r["source_type"] = None
    if r.get("fault") not in FAULT:
        r["fault"] = None
    d = _num(r.get("duration_days"))
    r["duration_days"] = int(math.ceil(d)) if d is not None and 0 <= d <= 365 else None   # round days UP
    h = _num(r.get("households_affected"))
    r["households_affected"] = int(round(h)) if h is not None and 1 <= h <= 5000 else None
    if not isinstance(r.get("drinking_source"), bool):
        r["drinking_source"] = None
    s = r.get("health_symptoms") or []
    if isinstance(s, str):
        s = [s]
    s = [x for x in dict.fromkeys(s) if x in SYMPT]
    if len(s) > 1 and "none" in s:
        s.remove("none")
    r["health_symptoms"] = s
    for k in ("village", "taluka", "district", "smell_colour_taste", "evidence_quote"):
        v = r.get(k)
        r[k] = v.strip()[:120] if isinstance(v, str) and v.strip() and v.strip().lower() != "null" else None
    if r.get("language_detected") not in ("mr", "hi", "hinglish", "en"):
        r["language_detected"] = None
    return r


def missing(r: dict) -> list[str]:
    return [f for f in REQUIRED if not r.get(f)]
