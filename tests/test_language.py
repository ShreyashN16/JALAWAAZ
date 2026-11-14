import asyncio
import json

import pytest

from app import db
from app.core.validators import clean, missing
from app.nlp import gazetteer
from app.nlp.extract import detect_lang, extract, parse_json, rule_extract
from app.nlp.yesno import parse_yes_no


@pytest.fixture
def villages(con):
    return db.villages(con)


# ------------------------------------------------------------- gazetteer
@pytest.mark.parametrize("mention,expected", [
    ("Shivapur", "Khed Shivapur"), ("शिवापूर", "Khed Shivapur"), ("शिवापुर", "Khed Shivapur"),
    ("Shivapur gaon", "Khed Shivapur"), ("शिवापूरमध्ये", "Khed Shivapur"), ("Donje", "Donje"),
    ("Donaje", "Donje"), ("डोणजे", "Donje"), ("Kondhanpur", "Kondhanpur"), ("Gorhe Budruk", "Gorhe Budruk"),
])
def test_match_accept(villages, mention, expected):
    v, score, mode = gazetteer.match_village(mention, villages)
    assert v["name"] == expected and mode == "accept", (mention, score, mode)


def test_match_confirm_band(villages):
    v, score, mode = gazetteer.match_village("Shivpuri", villages)       # near miss
    assert mode in ("confirm", "accept") and v["name"] == "Khed Shivapur"
    v, score, mode = gazetteer.match_village("सिवापुर", villages)          # STT spelling error
    assert mode in ("confirm", "accept") and v["name"] == "Khed Shivapur"


def test_match_reject(villages):
    assert gazetteer.match_village("Mumbai", villages)[2] == "ask"
    assert gazetteer.match_village("", villages)[2] == "ask"
    assert gazetteer.match_village(None, villages)[2] == "ask"


@pytest.mark.parametrize("text,expected", [
    ("Shivapur madhe handpump 3 divas band aahe", "Khed Shivapur"),
    ("शिवापूर मध्ये हातपंप तीन दिवस बंद आहे", "Khed Shivapur"),
    ("Donje gaon mein nal se ganda paani", "Donje"),
    ("आमच्या कुडजे गावात विहीर आटली", "Kudje"),
])
def test_find_in_text(villages, text, expected):
    v, score, mode = gazetteer.find_in_text(text, villages)
    assert v and v["name"] == expected and mode == "accept"


def test_find_in_text_none(villages):
    assert gazetteer.find_in_text("pump kharab hai 3 din se", villages)[2] == "ask"


def test_keyterms_cap(villages):
    kt = gazetteer.keyterms(villages, extra=["हातपंप"] * 500)
    assert len(kt) <= 200 and "शिवापूर" in kt and len(kt) == len(set(kt))


# ------------------------------------------------------------- yes / no
@pytest.mark.parametrize("text,expected", [
    ("ho", True), ("हो", True), ("होय", True), ("हो बरोबर आहे", True), ("haan ji", True), ("हाँ", True),
    ("yes", True), ("ok", True), ("barobar", True), ("sahi hai", True),
    ("nahi", False), ("नाही", False), ("नहीं", False), ("nako", False), ("galat hai", False), ("no", False),
    ("ji nahi", False), ("चुकीचे आहे", False),
    ("", None), ("kya?", None), ("ho nahi", None), ("hmm", None),
])
def test_yes_no(text, expected):
    assert parse_yes_no(text) is expected


@pytest.mark.parametrize("text,expected", [
    ("चालू झाला", True), ("pump chalu hai", True), ("पाणी येतंय", True),
    ("अजून बंद आहे", False), ("abhi bhi band hai", False), ("chalu nahi", False),
    ("haan, abhi bhi band hai", None), ("हो पण अजून बंद", None),
])
def test_yes_no_verify_context(text, expected):
    assert parse_yes_no(text, verify=True) is expected


# ------------------------------------------------------------- validators
def test_validators_ranges_and_enums():
    r = clean({"source_type": "pond", "fault": "no_water", "duration_days": 400, "households_affected": 0,
               "drinking_source": "yes", "health_symptoms": ["fever", "cough", "none"], "village": "  "})
    assert r["source_type"] is None and r["fault"] == "no_water"
    assert r["duration_days"] is None and r["households_affected"] is None
    assert r["drinking_source"] is None and r["health_symptoms"] == ["fever"] and r["village"] is None
    assert clean({"duration_days": 2.5})["duration_days"] == 3          # days round up
    assert clean({"duration_days": "3"})["duration_days"] == 3
    assert clean({"households_affected": 5001})["households_affected"] is None
    assert missing(clean({"village": "x"})) == ["source_type", "fault"]


# ------------------------------------------------------------- extraction
class FakeLLM:
    def __init__(self, *outs):
        self.outs, self.calls = list(outs), []

    async def complete(self, system, user, max_tokens=400):
        self.calls.append(user)
        o = self.outs.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


GOOD = json.dumps({"village": "शिवापूर", "source_type": "handpump", "fault": "no_water", "duration_days": 3,
                   "households_affected": 40, "drinking_source": None, "health_symptoms": [],
                   "language_detected": "mr", "evidence_quote": "शिवापूर मध्ये हातपंप",
                   "missing_fields": ["nonsense"]}, ensure_ascii=False)
TEXT = "शिवापूर मध्ये हातपंप तीन दिवस बंद आहे, चाळीस घरे"


def run(c):
    return asyncio.run(c)


def test_extract_evon_good_json():
    r, meta = run(extract(TEXT, None, FakeLLM(GOOD)))
    assert meta["source"] == "evon" and r["village"] == "शिवापूर" and r["duration_days"] == 3
    assert r["households_affected"] == 40 and r["_missing"] == []       # recomputed, model's list ignored


def test_extract_strips_fences_and_think():
    r, meta = run(extract(TEXT, None, FakeLLM("<think>x</think>```json\n" + GOOD + "\n```")))
    assert meta["source"] == "evon" and r["fault"] == "no_water"


def test_extract_retry_then_ok():
    llm = FakeLLM("Sure! here you go", GOOD)
    r, meta = run(extract(TEXT, None, llm))
    assert meta["source"] == "evon" and len(llm.calls) == 2


def test_extract_falls_back_to_rules_after_two_bad():
    r, meta = run(extract(TEXT, None, FakeLLM("garbage", "still garbage")))
    assert meta["source"].endswith("rules") and meta["needs_review"]
    assert r["source_type"] == "handpump" and r["duration_days"] == 3 and r["households_affected"] == 40


def test_extract_falls_back_on_llm_error():
    r, meta = run(extract(TEXT, None, FakeLLM(ConnectionError("down"))))
    assert meta["source"] == "evon-error→rules" and r["fault"] == "no_water"


def test_extract_no_llm_is_labelled_rules():
    r, meta = run(extract("pump kharab hai, 3 din se pani nahi", None, None))
    assert meta["source"] == "rules" and r["fault"] == "broken_part" and r["duration_days"] == 3


def test_guard_drops_hallucinated_numbers():
    bad = json.loads(GOOD)
    bad.update(duration_days=9, households_affected=400)
    r, meta = run(extract(TEXT, None, FakeLLM(json.dumps(bad, ensure_ascii=False))))
    assert r["duration_days"] == 3 and r["households_affected"] == 40      # rules refill from transcript
    assert any("dropped" in f for f in meta["flags"])


def test_merge_keeps_previous_values():
    first, _ = run(extract(TEXT, None, None))
    second, _ = run(extract("pinyache pani aahe", first, None, expecting="drinking_source"))
    assert second["households_affected"] == 40 and second["drinking_source"] is True


@pytest.mark.parametrize("expecting,text,field,value", [
    ("duration_days", "चार", "duration_days", 4), ("households_affected", "pachas", "households_affected", 50),
    ("drinking_source", "हो", "drinking_source", True), ("drinking_source", "nahi", "drinking_source", False),
    ("health_symptoms", "नाही", "health_symptoms", ["none"]), ("village", "Donje", "village", "Donje"),
])
def test_contextual_answers(expecting, text, field, value):
    r, _ = run(extract(text, None, None, expecting=expecting))
    assert r[field] == value


def test_parse_json_and_lang():
    assert parse_json('x {"a": 1} y') == {"a": 1}
    assert parse_json("[1,2]") is None and parse_json("") is None
    assert detect_lang("शिवापूर मध्ये हातपंप बंद आहे", "mr-IN", "hi") == "mr"
    assert detect_lang("गाँव में पानी नहीं है", "hi-IN", "mr") == "hi"
    assert detect_lang("pump kharab hai pani nahi", "hi-IN", "mr") == "hinglish"
    assert detect_lang("Shivapur madhe pani nahi aahe", "", "hi") == "mr"


@pytest.mark.parametrize("text,src,fault", [
    ("borewell chi motor jalali, light nahi", "borewell", "power"),
    ("टँकर आला नाही", "tanker", "no_water"),       # v2: the tanker not coming means no water (was None in v1)
    ("नळाला कमी दाब आहे", "tap", "low_pressure"),
    ("handpump ka handle toot gaya", "handpump", "broken_part"),
    ("विहिरीचे पाणी गढूळ", "well", "contamination"),
    ("tanki se paani leak ho raha", "tank", "leakage"),
])
def test_rule_extract_matrix(text, src, fault):
    r = rule_extract(text)
    assert r["source_type"] == src and r["fault"] == fault
