"""Call state machine (turn based, push-to-talk). Pure logic; I/O comes through `ctx`.

Report call:  GREET -> COLLECT (one question per turn) -> [VILLAGE_CONFIRM] -> CONFIRM
              -> yes: ticket | no: CORRECTION (once) -> CONFIRM | unclear twice: HANDOFF (no ticket)
Verify call:  VERIFY -> yes: VERIFIED | no: REOPENED | unclear twice: no answer (retry later)

Rules: AI disclosed in the greeting; read back and confirm before any ticket; at most
`max_followups` optional questions and `max_total_questions` in all; silence twice ends the call.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..nlp.extract import detect_lang
from ..nlp.gazetteer import find_in_text, match_village
from ..nlp.yesno import parse_yes_no
from . import templates as tpl
from .validators import REQUIRED, empty_report

ORDER = ["village", "source_type", "fault", "duration_days", "households_affected", "drinking_source", "health_symptoms"]
ASK_KEY = {"village": "ask_village", "source_type": "ask_source", "fault": "ask_fault", "duration_days": "ask_duration",
           "households_affected": "ask_households", "drinking_source": "ask_drinking", "health_symptoms": "ask_symptoms"}


@dataclass
class Reply:
    text: str                           # a templates.Say: caption plus .speech for Timbre
    done: bool = False
    outcome: str | None = None          # ticket | handoff | verified | reopened | no_answer
    ticket_id: int | None = None
    ticket_ref: str | None = None


def new_session(mode: str, lang: str, **kw) -> dict:
    s = {"mode": mode, "lang": lang if lang in ("mr", "hi", "hinglish") else "mr", "lang_locked": False,
         "state": "GREET" if mode == "report" else "VERIFY", "report": empty_report(), "followups": 0,
         "questions": 0, "asked": [], "retries": 0, "unclear": 0, "silent": 0, "village_row": None,
         "village_attempts": 0, "pending_village": None, "expecting": None, "last_question": None,
         "sources": [], "needs_review": False, "transcript": [], "ticket_id": None, "ticket_ref": None, "turns": 0}
    s.update(kw)
    return s


def greeting(sess: dict, ctx) -> str:
    if sess["mode"] == "verify":
        info = ctx.ticket_info(sess["ticket_id"])
        return tpl.t("verify", sess["lang"], digits=tpl.digits(info["ref"], sess["lang"]), village=info["village_spoken"],
                     source=tpl.label("source", info["source_type"], sess["lang"]) or tpl.label("source", "other", sess["lang"]))
    return tpl.t("greet", sess["lang"])


def _ask(sess, key_field: str, text_key: str | None = None) -> Reply:
    sess["expecting"] = key_field
    sess["questions"] += 1
    if key_field not in sess["asked"]:
        sess["asked"].append(key_field)
    q = tpl.t(text_key or ASK_KEY[key_field], sess["lang"])
    sess["last_question"] = q
    return Reply(q)


def _handoff(sess) -> Reply:
    sess["state"] = "HANDOFF"
    return Reply(tpl.t("handoff", sess["lang"]), done=True, outcome="handoff")


def _village_spoken(sess) -> str:
    return tpl.spoken_village(sess["report"], sess["village_row"], sess["lang"])


def _readback(sess) -> Reply:
    sess["state"] = "CONFIRM"
    sess["unclear"] = 0
    sess["expecting"] = "confirm"
    q = tpl.readback(sess["report"], _village_spoken(sess), sess["lang"])
    sess["last_question"] = q
    return Reply(q)


def _resolve_village(sess, text: str, ctx) -> Reply | None:
    """Gazetteer match. May return a confirmation question."""
    if sess["village_row"]:
        return None
    cfg = ctx.cfg["gazetteer"]
    vs = ctx.villages()
    mention = sess["report"].get("village")
    v, score, mode = match_village(mention, vs, cfg["accept"], cfg["confirm"]) if mention else (None, 0.0, "ask")
    v2, score2, mode2 = find_in_text(text, vs, cfg["accept"], cfg["confirm"])
    if score2 > score:
        v, score, mode = v2, score2, mode2
    if mode == "accept":
        sess["village_row"] = v
        sess["report"]["_village_score"] = score
        sess["report"]["village"] = sess["report"].get("village") or v["name"]
        return None
    if mode == "confirm":
        sess["pending_village"] = v
        sess["report"]["_village_score"] = score
        sess["state"] = "VILLAGE_CONFIRM"
        sess["expecting"] = "village_confirm"
        q = tpl.t("confirm_village", sess["lang"], village=tpl.spoken_village({}, v, sess["lang"]))
        sess["last_question"] = q
        sess["questions"] += 1
        return Reply(q)
    if mention and sess["village_attempts"] >= 1:
        sess["needs_review"] = True             # unknown village: keep what was said, location unavailable
        return None
    if mention:
        sess["village_attempts"] += 1
        sess["report"]["village"] = None
        return _ask(sess, "village", "ask_village_again")
    return None


def _next(sess, ctx) -> Reply:
    calling = ctx.cfg["calling"]
    r = sess["report"]
    if sess["questions"] >= calling["max_total_questions"]:
        return _handoff(sess) if any(not r.get(f) for f in REQUIRED) else _readback(sess)
    for f in ORDER:
        if f == "village":
            if not r.get("village"):
                return _ask(sess, f)
            continue
        if f in REQUIRED:
            if not r.get(f):
                return _ask(sess, f)
            continue
        if sess["followups"] >= calling["max_followups"] or f in sess["asked"]:
            continue
        if f == "health_symptoms":
            if not (r.get("drinking_source") and not r.get("health_symptoms")):
                continue
        elif r.get(f) not in (None, []):
            continue
        sess["followups"] += 1
        return _ask(sess, f)
    return _readback(sess)


async def handle_turn(sess: dict, text: str, ctx, stt_lang: str | None = None) -> Reply:
    sess["turns"] += 1
    text = (text or "").strip()
    if text:
        sess["transcript"].append(text)
        sess["silent"] = 0
    lang = sess["lang"]

    # -------------------------------------------------------------- verification call
    if sess["mode"] == "verify":
        yn = parse_yes_no(text, verify=True)
        if yn is None and sess["retries"] < 1:
            sess["retries"] += 1
            return Reply(tpl.t("no_hear" if not text else "yes_or_no", lang))
        result = "yes" if yn is True else "no" if yn is False else "none"
        await ctx.record_verification(sess["ticket_id"], result)
        sess["state"] = "VERIFY_DONE"
        key = {"yes": "verified_thanks", "no": "reopened", "none": "verify_unclear"}[result]
        return Reply(tpl.t(key, lang), done=True, outcome={"yes": "verified", "no": "reopened", "none": "no_answer"}[result],
                     ticket_id=sess["ticket_id"])

    # -------------------------------------------------------------- report call
    if not text:
        sess["silent"] += 1
        if sess["silent"] >= 2:
            return _handoff(sess)
        return Reply(tpl.t("no_hear", lang) + " " + (sess["last_question"] or ""))

    if sess["state"] in ("GREET", "COLLECT", "CORRECTION"):
        correcting = sess["state"] == "CORRECTION"
        if not sess["lang_locked"]:
            sess["lang"] = lang = detect_lang(text, stt_lang, lang)
            sess["lang_locked"] = True
        before_village = sess["report"].get("village")
        sess["report"], meta = await ctx.extract(text, sess["report"], sess["expecting"])
        sess["sources"].append(meta["source"])
        sess["needs_review"] |= bool(meta.get("needs_review"))
        if correcting and sess["report"].get("village") != before_village:
            sess["village_row"] = None                    # caller corrected the village: re-resolve
            sess["village_attempts"] = 0
        sess["state"] = "COLLECT"
        q = _resolve_village(sess, text, ctx)
        if q:
            return q
        return _next(sess, ctx)

    if sess["state"] == "VILLAGE_CONFIRM":
        yn = parse_yes_no(text)
        if yn is True:
            v = sess["pending_village"]
            sess["village_row"], sess["pending_village"] = v, None
            sess["report"]["village"] = sess["report"].get("village") or v["name"]
            sess["state"] = "COLLECT"
            return _next(sess, ctx)
        if yn is False or sess["unclear"] >= 1:
            sess["pending_village"] = None
            sess["report"]["village"] = None
            sess["village_attempts"] += 1
            sess["state"] = "COLLECT"
            if sess["village_attempts"] >= 2:
                return _handoff(sess)
            return _ask(sess, "village", "ask_village_again")
        sess["unclear"] += 1
        return Reply(tpl.t("yes_or_no", lang))

    if sess["state"] == "CONFIRM":
        yn = parse_yes_no(text)
        if yn is True:
            tid, ref = await ctx.create_ticket(sess)
            sess.update(ticket_id=tid, ticket_ref=ref, state="CLOSE")
            msg = tpl.t("ticket", lang, digits=tpl.digits(ref, lang))
            if tpl.needs_safety_line(sess["report"]):
                msg += " " + tpl.t("safety_line", lang)
            return Reply(msg, done=True, outcome="ticket", ticket_id=tid, ticket_ref=ref)
        if yn is False:
            if sess["retries"] < 1:
                sess["retries"] += 1
                sess["state"] = "CORRECTION"
                sess["expecting"] = None
                sess["last_question"] = tpl.t("which_wrong", lang)
                return Reply(sess["last_question"])
            return _handoff(sess)
        if sess["unclear"] < 1:
            sess["unclear"] += 1
            return Reply(tpl.t("yes_or_no", lang))
        return _handoff(sess)

    return _handoff(sess)
