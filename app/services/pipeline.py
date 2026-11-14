"""One call turn end to end: audio -> Prisma -> state machine (Evon extraction inside) -> Timbre.

Honest provider labels travel with every reply: which model transcribed, extracted and spoke, or
which fallback was used. Caller audio is never written anywhere except a temp dir that is deleted.

Latency design: a turn returns as soon as the reply TEXT is known, with an `audio_url`. The browser
fetches that URL and Timbre audio streams into it (see app/services/speech.py and /api/speech).
"""
from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import timedelta

from .. import db
from ..audio import AudioError, to_wav16k, wav_duration, wav_rms
from ..config import settings
from ..core import statemachine as sm
from ..core import templates as tpl
from ..core import tickets
from ..gnani import providers
from ..gnani.base import STTContext
from ..gnani.client import STATE as GNANI_STATE, GnaniError
from ..nlp import extract as ex
from ..nlp.gazetteer import keyterms
from ..security import hash_id, new_token
from . import speech

log = logging.getLogger("jalawaaz.pipeline")
SESSIONS: dict[str, dict] = {}
STT_CODE = {"mr": "mr-IN", "hi": "hi-IN", "hinglish": "hi-IN,en-IN"}
WATER_TERMS = ["हातपंप", "हँडपंप", "हैंडपंप", "बोअरवेल", "बोरवेल", "विहीर", "कुआँ", "नळ", "नल", "टाकी", "टंकी",
               "टँकर", "टैंकर", "पाणी", "पानी", "गढूळ", "गळती", "लीकेज", "handpump", "borewell", "tanker", "pipeline"]
STATIC_TEXTS = {v for row in tpl.T.values() for v in row.values() if "{" not in v}


class TurnError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class CallContext:
    def __init__(self, entry: dict):
        self.entry = entry
        self.cfg = settings.cfg
        self._villages = None
        self.timings = {"llm_ms": 0.0}

    def villages(self):
        if self._villages is None:
            con = db.connect()
            try:
                self._villages = db.villages(con)
            finally:
                con.close()
        return self._villages

    async def extract(self, text, report, expecting):
        llm = await providers.llm()
        r, meta = await ex.extract(text, report, llm, expecting)
        self.timings["llm_ms"] += meta["ms"]
        self.entry["last_extraction"] = meta
        return r, meta

    async def create_ticket(self, sess):
        src = Counter(sess["sources"]).most_common(1)[0][0] if sess["sources"] else "rules"
        con = db.connect()
        try:
            return tickets.create_ticket(con, sess["report"], self.entry["device_hash"], sess["lang"],
                                         " | ".join(sess["transcript"])[:2000], sess["village_row"],
                                         extraction_source=src, needs_review=sess["needs_review"])
        finally:
            con.close()

    async def record_verification(self, tid, result):
        con = db.connect()
        try:
            tickets.record_verification(con, tid, result)
        finally:
            con.close()

    def ticket_info(self, tid):
        con = db.connect()
        try:
            t = tickets.detail(con, tid)
            vrow = next((v for v in db.villages(con) if v["name"] == t["village"]), None)
        finally:
            con.close()
        return {"ref": t["ref"], "source_type": t["source_type"],
                "village_spoken": tpl.spoken_village({"village": t["village"]}, vrow, t["lang"] or "mr")}


def stt_context(entry: dict, ctx: CallContext) -> STTContext:
    """Prisma v3.0 context hints for this turn; each can be switched off in data/config.json."""
    c = (settings.cfg.get("stt", {}).get("context") or {})
    out = STTContext()
    vs = ctx.villages()
    if c.get("keyterms", True):
        out.keyterms = list(dict.fromkeys(WATER_TERMS + keyterms(vs, None)))[:200]
    if c.get("topic", True):
        talukas = Counter(v.get("taluka") for v in vs if v.get("taluka")).most_common(1)
        districts = Counter(v.get("district") for v in vs if v.get("district")).most_common(1)
        tmpl = settings.cfg.get("stt", {}).get("topic") or ""
        out.topic = tmpl.format(taluka=talukas[0][0] if talukas else "the", district=districts[0][0] if districts else "the") or None
    if c.get("previous_text", True):
        out.previous_text = str(entry["sess"].get("last_question") or "") or None
    return out


# ------------------------------------------------------------------ outbox (simulated calls)
def missed_call(device: str) -> dict:
    dh = hash_id(device)
    con = db.connect()
    try:
        con.execute("DELETE FROM outbox WHERE device_hash=? AND kind='callback' AND delivered=0", (dh,))
        ready = db.now() + timedelta(seconds=settings.DEMO_CALLBACK_DELAY_SEC)
        con.execute("INSERT INTO outbox(device_hash, kind, ready_at) VALUES (?,?,?)", (dh, "callback", db.ts(ready)))
    finally:
        con.close()
    return {"queued": True, "callback_in_sec": settings.DEMO_CALLBACK_DELAY_SEC, "simulated": True}


def poll(device: str) -> dict:
    dh = hash_id(device)
    con = db.connect()
    try:
        row = con.execute("SELECT * FROM outbox WHERE device_hash=? AND delivered=0 AND ready_at<=? ORDER BY id LIMIT 1",
                          (dh, db.ts())).fetchone()
        pending = con.execute("SELECT kind, ready_at FROM outbox WHERE device_hash=? AND delivered=0 AND ready_at>?"
                              " ORDER BY ready_at LIMIT 1", (dh, db.ts())).fetchone()
        if not row:
            out = {"incoming": None}
            if pending:
                wait = (db.parse_ts(pending["ready_at"]) - db.now()).total_seconds()
                out["next"] = {"kind": pending["kind"], "in_sec": max(0, round(wait))}
            return out
        con.execute("UPDATE outbox SET delivered=1, delivered_at=? WHERE id=?", (db.ts(), row["id"]))
        out = {"incoming": row["kind"], "ticket_id": row["ticket_id"], "simulated": True}
        if row["ticket_id"]:
            t = con.execute("SELECT ref, lang FROM tickets WHERE id=?", (row["ticket_id"],)).fetchone()
            out.update(ticket_ref=t["ref"], lang=t["lang"])
        return out
    finally:
        con.close()


def my_tickets(device: str) -> list[dict]:
    """Status of the tickets this device reported (for the villager's phone). No other caller's data."""
    dh = hash_id(device)
    con = db.connect()
    try:
        rows = con.execute(
            "SELECT t.id, t.ref, t.state, t.priority, t.created_at, t.ack_at, t.fix_claimed_at, t.verified_at,"
            " t.reopened_count, t.lang, r.source_type, r.fault, coalesce(v.name, r.village_text) AS village"
            " FROM tickets t JOIN reports r ON r.id=t.report_id LEFT JOIN villages v ON v.id=r.village_id"
            " WHERE t.caller_hash=? ORDER BY t.id DESC LIMIT 20", (dh,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# ------------------------------------------------------------------ sessions
def _prune():
    nowm = time.time()
    for k in [k for k, v in SESSIONS.items() if v["expires"] < nowm]:
        SESSIONS.pop(k, None)


def _voice(text, lang: str, entry: dict, notices: list) -> dict:
    """Register the reply for speaking. Returns the audio fields of the response."""
    tts = providers.tts()
    plain = tpl.plain_speech(text)
    if tts is None:
        if settings.gnani_configured and GNANI_STATE["credits_exhausted"]:
            notices.append("Gnani credits exhausted: replies are on screen only.")
        return {"audio_url": None, "mime": None, "speech_text": plain, "browser_voice": True,
                "tts": "browser-fallback"}
    static = str(text) in STATIC_TEXTS
    sid = speech.register(tpl.speech_of(text), lang, telephone=entry["telephone"], static=static,
                          call_id=entry.get("call_id"))
    if static and hasattr(tts, "cached"):
        cached_bytes = tts.cached(tpl.speech_of(text), lang, telephone=entry["telephone"])
        if cached_bytes:
            item = speech.get(sid)
            if item:
                item.audio = cached_bytes
                item.mime = tts.mime_for(entry["telephone"])
    return {"audio_url": f"/api/speech/{sid}", "mime": tts.mime_for(entry["telephone"]), "speech_text": plain,
            "browser_voice": False, "tts": getattr(tts, "name", "tts")}


async def start_session(device: str, mode: str, lang: str, ticket_id: int | None = None, telephone: bool | None = None) -> dict:
    _prune()
    if mode not in ("report", "verify"):
        raise TurnError("bad_mode", "mode must be report or verify")
    dh = hash_id(device)
    if mode == "verify":
        con = db.connect()
        try:
            t = con.execute("SELECT * FROM tickets WHERE id=?", (ticket_id or 0,)).fetchone()
            if not t or t["caller_hash"] != dh:
                raise TurnError("not_caller", "Only the original reporter's device can verify this ticket", 403)
            if t["state"] != "FIX_CLAIMED":
                raise TurnError("not_pending", f"Ticket is {t['state']}, not awaiting verification", 409)
            lang = t["lang"] or lang
        finally:
            con.close()
    sid = new_token()
    sess = sm.new_session(mode, lang, ticket_id=ticket_id)
    tel = settings.TELEPHONE_MODE if telephone is None else bool(telephone)
    entry = {"sess": sess, "device_hash": dh, "expires": time.time() + settings.cfg["privacy"]["session_ttl_minutes"] * 60,
             "telephone": tel, "started": time.time()}
    con = db.connect()
    try:
        cur = con.execute("INSERT INTO calls(session_id, direction, kind, caller_hash, lang, created_at, telephone)"
                          " VALUES (?,?,?,?,?,?,?)", (sid[:8], "outbound-simulated", mode, dh, lang, db.ts(), int(tel)))
        entry["call_id"] = cur.lastrowid
    finally:
        con.close()
    SESSIONS[sid] = entry
    ctx = CallContext(entry)
    text = sm.greeting(sess, ctx)
    sess["last_question"] = text
    notices: list[str] = []
    voice = _voice(text, sess["lang"], entry, notices)
    return {"session_id": sid, "reply_text": str(text), **voice, "done": False,
            "state": sess["state"], "lang": sess["lang"], "mode": mode, "notices": notices,
            "providers": {"tts": voice["tts"]}, "simulated_call": True, "telephone": tel,
            "expecting": sess.get("expecting")}


def _early(sess, entry, text, notices, providers_info, offer_text=True):
    voice = _voice(text, sess["lang"], entry, notices)
    return {"transcript": None, "reply_text": str(text), **voice, "done": False, "state": sess["state"],
            "lang": sess["lang"], "offer_text": offer_text, "notices": notices, "providers": providers_info,
            "expecting": sess.get("expecting")}


async def run_turn(sid: str, audio: bytes | None = None, typed: str | None = None) -> dict:
    _prune()
    entry = SESSIONS.get(sid)
    if not entry:
        raise TurnError("no_session", "Call session expired or unknown. Start a new call.", 404)
    entry["expires"] = time.time() + settings.cfg["privacy"]["session_ttl_minutes"] * 60
    sess = entry["sess"]
    if sess["state"] in ("CLOSE", "HANDOFF", "VERIFY_DONE"):
        raise TurnError("call_over", "This call has ended.", 409)
    notices: list[str] = []
    timings = {"stt_ms": 0.0, "llm_ms": 0.0}
    t0 = time.perf_counter()
    stt_info: dict = {"provider": "typed" if typed is not None else "prisma"}
    transcript, stt_lang = "", None
    ctx = CallContext(entry)

    if typed is not None:
        transcript = typed.strip()[:500]
    else:
        if not audio:
            raise TurnError("no_audio", "No audio received")
        if len(audio) > settings.MAX_UPLOAD_BYTES:
            raise TurnError("too_large", "Recording too large", 413)
        try:
            wav = to_wav16k(audio, telephone=entry["telephone"])
            dur = wav_duration(wav)
        except AudioError as e:
            raise TurnError("bad_audio", f"Could not read the recording ({e})")
        if dur > settings.cfg["stt"]["max_clip_seconds"]:
            raise TurnError("too_long", "Please keep each answer under 25 seconds")
        stt = providers.stt()
        stt_info["seconds"] = round(dur, 1)
        if dur < 0.3 or wav_rms(wav) < 0.003:
            stt_info["provider"] = "silence-detected"         # do not spend a credit on silence
        elif stt is None:
            del wav
            notices.append("Voice input needs a Gnani Prisma key (GNANI_API_KEY). Type your answer instead.")
            return _early(sess, entry, tpl.t("no_hear", sess["lang"]), notices, {"stt": "none"})
        else:
            code = STT_CODE[sess["lang"]] if sess["lang_locked"] else settings.cfg["stt"]["first_turn_languages"]
            try:
                r = await stt.transcribe(wav, code, None, stt_context(entry, ctx))
                transcript, stt_lang = r.text, r.lang
                timings["stt_ms"] = r.ms
                stt_info.update(model=r.model, detected=r.lang, language_code=code, context=r.context_used,
                                request_id=r.request_id)
                if r.truncated:
                    notices.append("Prisma cut the transcript short (token limit). Shorter answers work better.")
            except GnaniError as e:
                notices.append(f"Speech recognition failed ({e.status} {e.kind}). {e.user_hint}")
                del wav
                return _early(sess, entry, tpl.t("no_hear", sess["lang"]), notices, {"stt": "prisma-error"})
        del wav                                              # audio discarded after transcription

    try:
        reply = await sm.handle_turn(sess, transcript, ctx, stt_lang)
    except Exception:
        log.exception("turn failed")                          # no transcript in logs
        sess["state"] = "HANDOFF"
        reply = sm.Reply(tpl.t("handoff", sess["lang"]), done=True, outcome="error")
    timings["llm_ms"] = ctx.timings["llm_ms"]
    voice = _voice(reply.text, sess["lang"], entry, notices)
    total = (time.perf_counter() - t0) * 1000
    meta = entry.get("last_extraction") or {}
    con = db.connect()
    try:
        con.execute("UPDATE calls SET turns=turns+1, lang=?, stt_ms=stt_ms+?, llm_ms=llm_ms+?,"
                    " total_ms=total_ms+?, providers=?, outcome=coalesce(?, outcome), ticket_id=coalesce(?, ticket_id),"
                    " ended_at=CASE WHEN ? THEN ? ELSE ended_at END, duration_s=? WHERE id=?",
                    (sess["lang"], timings["stt_ms"], timings["llm_ms"], total,
                     f"stt={stt_info['provider']};llm={meta.get('source', '-')};tts={voice['tts']}",
                     reply.outcome, reply.ticket_id, int(reply.done), db.ts(), round(time.time() - entry["started"], 1),
                     entry["call_id"]))
    finally:
        con.close()
    if reply.done:
        SESSIONS.pop(sid, None)
    preview = {k: v for k, v in sess["report"].items() if not k.startswith("_")}
    if sess["village_row"]:
        preview["village_matched"] = sess["village_row"]["name"]
        preview["village_on_map"] = sess["village_row"].get("lat") is not None
    return {"transcript": transcript, "reply_text": str(reply.text), **voice,
            "done": reply.done, "outcome": reply.outcome, "ticket_id": reply.ticket_id, "ticket_ref": reply.ticket_ref,
            "state": sess["state"], "lang": sess["lang"], "expecting": sess.get("expecting"),
            "report": preview if sess["mode"] == "report" else None, "notices": notices,
            "providers": {"stt": stt_info["provider"], "llm": meta.get("source") if sess["mode"] == "report" else None,
                          "tts": voice["tts"]},
            "stt": {k: v for k, v in stt_info.items() if k != "provider"},
            "timings_ms": {k: round(v) for k, v in {**timings, "until_text_ms": total}.items()}}


async def speech_stream(item: speech.SpeechItem):
    """(first_chunk, async iterator of the rest, stats). Raises GnaniError before any audio exists."""
    tts = providers.tts()
    if tts is None:
        raise GnaniError(503, "NO_TTS", "Timbre is not configured")
    stats: dict = {}
    if item.audio is not None:                       # replay from memory, no new credit
        async def done():
            if False:
                yield b""
        return item.audio, done(), {"mode": "memory"}
    if item.static:                                  # template sentence: disk cache
        r = await tts.speak(item.text, item.lang, cache=True, telephone=item.telephone)
        item.audio, item.mime = r.audio, r.mime
        _record_tts(item, {"mode": "cache" if r.cached else "rest", "ms": r.ms, "ttfb_ms": r.ms})

        async def none():
            if False:
                yield b""
        return r.audio, none(), {"mode": "cache" if r.cached else "rest"}
    agen = tts.stream(item.text, item.lang, telephone=item.telephone, stats=stats)
    first = await agen.__anext__()
    t0 = time.perf_counter()

    async def rest():
        buf = [first]
        try:
            async for chunk in agen:
                buf.append(chunk)
                yield chunk
            item.audio = b"".join(buf)
        finally:
            stats.setdefault("ms", (time.perf_counter() - t0) * 1000 + (stats.get("ttfb_ms") or 0))
            _record_tts(item, stats)
    return first, rest(), stats


def _record_tts(item: speech.SpeechItem, stats: dict) -> None:
    if not item.call_id:
        return
    con = db.connect()
    try:
        con.execute("UPDATE calls SET tts_ms=tts_ms+?, tts_ttfb_ms=coalesce(tts_ttfb_ms, ?) WHERE id=?",
                    (float(stats.get("ms") or 0), stats.get("ttfb_ms"), item.call_id))
    finally:
        con.close()
