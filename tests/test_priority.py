"""Priority engine: 34 hand-labelled cases covering every rule and the reopened path.
Thresholds (data/config.json): P1 >= 100 households for >= 2 days; P2 >= 3 days or >= 50 households."""
import pytest

from app.config import settings
from app.core.priority import compute_priority, escalate


def R(**kw):
    base = {"source_type": "handpump", "fault": "no_water", "duration_days": None, "households_affected": None,
            "drinking_source": None, "health_symptoms": []}
    base.update(kw)
    return base


CASES = [
    # (report, repeat, reopened, expected priority, reason fragment)
    (R(), False, 0, 3, "default"),
    (R(duration_days=1, households_affected=10), False, 0, 3, "default"),
    (R(duration_days=2, households_affected=49), False, 0, 3, "default"),
    (R(duration_days=3), False, 0, 2, "outage 3 days"),
    (R(duration_days=10), False, 0, 2, "outage"),
    (R(households_affected=50), False, 0, 2, "50 households"),
    (R(households_affected=99, duration_days=1), False, 0, 2, "99 households"),
    (R(households_affected=100, duration_days=2), False, 0, 1, "100 households without water for 2 days"),
    (R(households_affected=250, duration_days=5), False, 0, 1, "250 households"),
    (R(households_affected=100, duration_days=1), False, 0, 2, "100 households (>= 50)"),
    (R(households_affected=100, duration_days=2, source_type="tanker"), False, 0, 2, "households"),
    (R(households_affected=100, duration_days=2, source_type="tap"), False, 0, 1, "households without water"),
    (R(households_affected=100, duration_days=2, source_type="well"), False, 0, 1, "households without water"),
    (R(households_affected=100, duration_days=2, source_type="tank"), False, 0, 1, "households without water"),
    (R(households_affected=100, duration_days=2, source_type="borewell"), False, 0, 1, "households without water"),
    (R(fault="contamination", drinking_source=True), False, 0, 1, "drinking source contaminated"),
    (R(fault="contamination", drinking_source=False), False, 0, 3, "default"),
    (R(fault="contamination", drinking_source=None), False, 0, 3, "default"),
    (R(fault="no_water", drinking_source=True, health_symptoms=["fever"]), False, 0, 1, "symptoms"),
    (R(fault="leakage", drinking_source=True, health_symptoms=["diarrhoea", "vomiting"]), False, 0, 1, "symptoms"),
    (R(fault="no_water", drinking_source=True, health_symptoms=["none"]), False, 0, 3, "default"),
    (R(fault="contamination", health_symptoms=["skin"]), False, 0, 1, "contamination with reported symptoms"),
    (R(fault="no_water", health_symptoms=["fever"]), False, 0, 3, "default"),
    (R(), True, 0, 2, "repeat report"),
    (R(duration_days=3), True, 0, 2, "outage"),
    (R(households_affected=100, duration_days=2), True, 0, 1, "households"),
    (R(), False, 1, 2, "reopened 1x"),
    (R(), False, 2, 1, "reopened 2x"),
    (R(), False, 5, 1, "reopened 5x"),
    (R(duration_days=3), False, 1, 1, "reopened 1x after a false closure (P2 -> P1)"),
    (R(fault="contamination", drinking_source=True), False, 1, 1, "reopened"),
    (R(), True, 1, 1, "repeat"),
    (R(fault=None, source_type=None), False, 0, 3, "default"),
    (R(households_affected=0, duration_days=0), False, 0, 3, "default"),
]


@pytest.mark.parametrize("report,repeat,reopened,expected,frag", CASES)
def test_priority_cases(report, repeat, reopened, expected, frag):
    p, reason = compute_priority(report, repeat, reopened, settings.cfg)
    assert p == expected, reason
    assert frag in reason


def test_case_count():
    assert len(CASES) >= 30


def test_escalate():
    assert [escalate(3), escalate(2), escalate(1)] == [2, 1, 1]
