"""Deterministic priority engine. 1 = most urgent (P1), 3 = normal (P3).

Evon never sets priority. Every ticket stores the reason string shown on the dashboard.
Thresholds come from data/config.json and are prototype assumptions.
"""
from __future__ import annotations


def compute_priority(r: dict, repeat_report: bool, reopened_count: int, cfg: dict) -> tuple[int, str]:
    c = cfg["priority"]
    reasons: list[str] = []
    p = 3
    sym = [s for s in (r.get("health_symptoms") or []) if s != "none"]
    if r.get("drinking_source") and (sym or r.get("fault") == "contamination"):
        p = 1
        reasons.append("drinking source with reported symptoms" if sym else "drinking source contaminated")
    elif r.get("fault") == "contamination" and sym:
        p = 1
        reasons.append("contamination with reported symptoms")
    hh, dd = r.get("households_affected") or 0, r.get("duration_days") or 0
    if (r.get("source_type") in {"handpump", "tap", "well", "tank", "borewell"}
            and hh >= c["p1_households"] and dd >= c["p1_duration_days"]):
        p = 1
        reasons.append(f"{hh} households without water for {dd} days (>= {c['p1_households']} for >= {c['p1_duration_days']})")
    if p > 2 and (dd >= c["p2_duration_days"] or hh >= c["p2_households"]):
        p = 2
        why = []
        if dd >= c["p2_duration_days"]:
            why.append(f"outage {dd} days (>= {c['p2_duration_days']})")
        if hh >= c["p2_households"]:
            why.append(f"{hh} households (>= {c['p2_households']})")
        reasons.append(" and ".join(why))
    if p > 2 and repeat_report:
        p = 2
        reasons.append(f"repeat report on the same village and source within {c['repeat_window_days']} days")
    if reopened_count:
        before = p
        p = max(1, p - reopened_count)
        reasons.append(f"reopened {reopened_count}x after a false closure (P{before} -> P{p})")
    if not reasons:
        reasons.append("default: no urgency rule matched")
    return p, "; ".join(reasons)


def escalate(priority: int) -> int:
    return max(1, priority - 1)
