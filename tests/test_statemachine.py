"""Scripted conversations through the real pipeline (typed turns, rule extraction, no network)."""
import asyncio

import pytest

from app import db
from app.core import tickets
from app.gnani import providers
from app.services import pipeline


@pytest.fixture(autouse=True)
def no_providers():
    providers.set_providers(stt=None, tts=None, llm=None)
    yield
    providers.set_providers()


def run(c):
    return asyncio.run(c)


def call(device, turns, lang="mr", mode="report", ticket_id=None):
    s = run(pipeline.start_session(device, mode, lang, ticket_id))
    out = [s]
    for t in turns:
        r = run(pipeline.run_turn(s["session_id"], typed=t))
        out.append(r)
        if r["done"]:
            break
    return out


def test_full_report_marathi_one_utterance():
    out = call("d1", ["Shivapur madhe handpump 3 divas band aahe, 40 ghar", "nahi", "ho"])
    assert "एआय सहायक" in out[0]["reply_text"]                         # AI disclosed first
    # after the main utterance the assistant asks the one remaining optional question (drinking)
    assert out[1]["expecting"] == "drinking_source"
    assert "बरोबर आहे का" in out[2]["reply_text"] and "शिवापूर" in out[2]["reply_text"]
    last = out[3]
    assert last["done"] and last["outcome"] == "ticket" and last["ticket_ref"]
    assert last["ticket_ref"] in last["reply_text"]                       # caption shows the number
    assert "चार" in last["speech_text"] or "," in last["speech_text"]     # Timbre gets digit words
    con = db.connect()
    t = tickets.detail(con, last["ticket_id"])
    con.close()
    assert t["village"] == "Khed Shivapur" and t["source_type"] == "handpump" and t["households"] == 40
    assert t["extraction_source"] == "rules" and t["priority"] == 2


def test_followups_one_question_per_turn_hindi():
    out = call("d2", ["हैंडपंप खराब है", "Donje", "पाँच दिन", "पचास", "नहीं", "हाँ"], lang="hi")
    asked = [o.get("expecting") for o in out[1:]]
    assert asked[:4] == ["village", "duration_days", "households_affected", "drinking_source"]
    assert out[-1]["outcome"] == "ticket"


def test_no_ticket_without_confirmation_and_one_correction():
    out = call("d3", ["Shivapur madhe handpump band aahe", "3", "40", "nahi", "nahi",
                      "nal aahe", "nahi"])
    states = [o.get("state") for o in out]
    assert "CORRECTION" in states
    assert out[-1]["outcome"] == "handoff" and out[-1]["ticket_id"] is None
    con = db.connect()
    assert con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0
    con.close()


def test_correction_changes_field_then_ticket():
    out = call("d4", ["Shivapur madhe handpump 3 divas band aahe, 40 ghar", "nahi", "nahi", "borewell aahe", "ho"])
    assert out[-1]["outcome"] == "ticket"
    con = db.connect()
    t = tickets.detail(con, out[-1]["ticket_id"])
    con.close()
    assert t["source_type"] == "borewell"


def test_unknown_village_asks_again_then_flags_review():
    out = call("d5", ["Handpump band aahe", "Mumbai", "Mumbai", "3", "10", "nahi", "ho"])
    assert out[2]["expecting"] == "village"                              # asked again once
    assert out[-1]["outcome"] == "ticket"
    con = db.connect()
    r = con.execute("SELECT village_id, village_text, needs_review FROM reports").fetchone()
    con.close()
    assert r["village_id"] is None and r["needs_review"] == 1


def test_fuzzy_village_confirmation():
    out = call("d6", ["Shivpuri gavat nal band aahe"])
    s = out[1]
    assert s["state"] in ("VILLAGE_CONFIRM", "COLLECT")


def test_silent_caller_twice_hands_off():
    out = call("d7", ["", ""])
    assert out[-1]["outcome"] == "handoff"


def test_unclear_readback_answer_asks_once_then_hands_off():
    out = call("d8", ["Shivapur madhe handpump 3 divas band aahe, 40 ghar", "nahi", "hmm", "kya"])
    assert out[-1]["outcome"] == "handoff"


def test_safety_line_only_for_drinking_with_symptoms():
    out = call("d9", ["Donje gaon mein nal se ganda paani, bachchon ko ulti, yahi paani peete hain, 2 din se, 20 ghar",
                      "haan"], lang="hi")
    assert out[-1]["outcome"] == "ticket" and "उबाल" in out[-1]["reply_text"]
    con = db.connect()
    assert con.execute("SELECT priority FROM tickets").fetchone()[0] == 1
    con.close()


def _ticket_for_verify(device):
    out = call(device, ["Shivapur madhe handpump 3 divas band aahe, 40 ghar", "nahi", "ho"])
    tid = out[-1]["ticket_id"]
    con = db.connect()
    tickets.fix_claimed(con, tid)
    con.close()
    return tid


@pytest.mark.parametrize("answer,state,outcome", [("ho, chalu jhala", "VERIFIED", "verified"),
                                                  ("nahi, ajun band aahe", "ACKED", "reopened")])
def test_verification_call(answer, state, outcome):
    tid = _ticket_for_verify("dv")
    out = call("dv", [answer], mode="verify", ticket_id=tid)
    assert "एआय सहायक" in out[0]["reply_text"] and "हातपंप" in out[0]["reply_text"]
    assert out[-1]["outcome"] == outcome
    con = db.connect()
    assert tickets.get(con, tid)["state"] == state
    con.close()


def test_verification_unclear_twice_is_no_answer():
    tid = _ticket_for_verify("dv2")
    out = call("dv2", ["hmm", "kya"], mode="verify", ticket_id=tid)
    assert out[-1]["outcome"] == "no_answer"
    con = db.connect()
    assert tickets.get(con, tid)["state"] == "FIX_CLAIMED"
    con.close()


def test_only_original_device_can_verify():
    tid = _ticket_for_verify("owner")
    with pytest.raises(pipeline.TurnError) as e:
        run(pipeline.start_session("someone-else", "verify", "mr", tid))
    assert e.value.status == 403


def test_evon_path_labelled(monkeypatch):
    import json

    class FakeEvon:
        async def complete(self, system, user, max_tokens=400):
            return json.dumps({"village": "शिवापूर", "source_type": "handpump", "fault": "no_water",
                               "duration_days": 3, "households_affected": 40, "drinking_source": False,
                               "health_symptoms": [], "evidence_quote": "शिवापूर"}, ensure_ascii=False)
    providers.set_providers(stt=None, tts=None, llm=FakeEvon())
    out = call("de", ["शिवापूर मध्ये हातपंप 3 दिवस बंद आहे, 40 घरे", "हो"])
    assert out[1]["providers"]["llm"] == "evon" and out[-1]["outcome"] == "ticket"
