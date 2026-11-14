"""HTTP layer (Starlette, the ASGI toolkit FastAPI is built on; see docs/decisions.md D1).

Thin: all logic lives in app/core, app/nlp, app/gnani and app/services. Every endpoint is listed in
app/openapi.py and rendered at /docs.  Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import platform
import secrets
import sys
import uuid
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import db, openapi
from .audio import ffmpeg_available
from .config import ROOT, VERSION, settings
from .core import scheduler, tickets
from .gnani import providers
from .gnani.client import STATE as GNANI_STATE, GnaniError
from .security import RateLimiter, hash_id, role_for_pin
from .services import demo, evaluation, pipeline, speech

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("jalawaaz")
WEB = ROOT / "web"
limiter = RateLimiter(settings.cfg["rate_limit"]["per_minute"])


# ------------------------------------------------------------------ helpers
def err(code: str, message: str, status: int = 400, request: Request | None = None) -> JSONResponse:
    rid = getattr(request.state, "rid", None) if request else None
    return JSONResponse({"error": {"code": code, "message": message, "request_id": rid}}, status_code=status)


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


class Device(BaseModel):
    device: str = Field(min_length=8, max_length=80)


class SessionIn(Device):
    mode: str = Field(pattern="^(report|verify)$")
    lang: str = Field(default="mr", pattern="^(mr|hi|hinglish)$")
    ticket_id: int | None = None
    telephone: bool | None = None


class Decline(Device):
    ticket_id: int | None = None


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=500)


class PinIn(BaseModel):
    pin: str = Field(min_length=1, max_length=20)


async def body(request: Request, model):
    try:
        return model.model_validate(await request.json())
    except (ValidationError, json.JSONDecodeError, ValueError) as e:
        raise ApiError("bad_request", f"Invalid request body: {str(e)[:200]}", 422)


def client_ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


def limit(request: Request):
    if not limiter.allow(client_ip(request)):
        raise ApiError("rate_limited", "Too many requests. Wait a minute and try again.", 429)


def require(request: Request, *roles: str, csrf: bool = False) -> str:
    role = request.session.get("role")
    if role not in roles:
        raise ApiError("unauthorised", "Sign in with an engineer or officer PIN.", 401 if not role else 403)
    if csrf and request.headers.get("x-csrf-token") != request.session.get("csrf"):
        raise ApiError("csrf", "Your session token is out of date. Reload the page.", 403)
    return role


def synthetic_flag(request: Request) -> bool:
    return request.query_params.get("synthetic", "1") != "0"


def device_param(request: Request) -> str:
    dev = request.query_params.get("device", "")
    if not (8 <= len(dev) <= 80):
        raise ApiError("bad_request", "device id required")
    return dev


def page(name: str):
    async def handler(request: Request):
        return FileResponse(WEB / name, headers={"Cache-Control": "no-store"})
    return handler


def protected_page(name: str, roles: tuple[str, ...]):
    async def handler(request: Request):
        if request.session.get("role") not in roles:
            return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
        return FileResponse(WEB / name, headers={"Cache-Control": "no-store"})
    return handler


def with_con(fn):
    con = db.connect()
    try:
        return fn(con)
    finally:
        con.close()


# ------------------------------------------------------------------ public / phone
async def health(request: Request):
    try:
        db_ok = with_con(lambda c: c.execute("SELECT 1").fetchone() is not None)
    except Exception:
        db_ok = False
    return JSONResponse({"ok": db_ok, "db": db_ok, "ffmpeg": ffmpeg_available(), "version": VERSION,
                         "providers": await providers.status(), "demo_mode": settings.DEMO_MODE,
                         "telephone_mode_default": settings.TELEPHONE_MODE,
                         "label": "Independent prototype, not an official service"})


async def status(request: Request):
    return JSONResponse({"providers": await providers.status(), "demo_mode": settings.DEMO_MODE,
                         "callback_delay_sec": settings.DEMO_CALLBACK_DELAY_SEC,
                         "verify_delay_sec": settings.DEMO_VERIFY_DELAY_SEC if settings.DEMO_MODE else None,
                         "verify_delay_hours": None if settings.DEMO_MODE else settings.cfg["calling"]["verify_delay_hours"],
                         "telephone_mode_default": settings.TELEPHONE_MODE, "ffmpeg": ffmpeg_available(),
                         "max_utterance_seconds": settings.cfg["calling"]["max_utterance_seconds"],
                         "silence_seconds": settings.cfg["calling"]["silence_seconds"], "version": VERSION})


async def missed_call(request: Request):
    limit(request)
    d = await body(request, Device)
    return JSONResponse(pipeline.missed_call(d.device))


async def poll(request: Request):
    return JSONResponse(pipeline.poll(device_param(request)))


async def start_session(request: Request):
    limit(request)
    d = await body(request, SessionIn)
    try:
        return JSONResponse(await pipeline.start_session(d.device, d.mode, d.lang, d.ticket_id, d.telephone))
    except pipeline.TurnError as e:
        raise ApiError(e.code, e.message, e.status)


async def turn(request: Request):
    limit(request)
    if int(request.headers.get("content-length") or 0) > settings.MAX_UPLOAD_BYTES + 10_000:
        raise ApiError("too_large", "Recording too large", 413)
    form = await request.form(max_files=1, max_fields=5)
    sid = str(form.get("session_id") or "")
    audio = form.get("audio")
    text = form.get("text")
    try:
        if audio is not None and hasattr(audio, "read"):
            raw = await audio.read()
            await audio.close()
            return JSONResponse(await pipeline.run_turn(sid, audio=raw))
        if text is not None:
            return JSONResponse(await pipeline.run_turn(sid, typed=str(text)))
        raise ApiError("bad_request", "Send `audio` (file) or `text`.")
    except pipeline.TurnError as e:
        raise ApiError(e.code, e.message, e.status)


async def speech_audio(request: Request):
    item = speech.get(request.path_params["sid"])
    if not item:
        raise ApiError("not_found", "This reply has expired.", 404)
    try:
        first, rest, stats = await pipeline.speech_stream(item)
    except GnaniError as e:
        return err("tts_failed", f"Timbre could not speak this reply ({e.status} {e.kind}). {e.user_hint}", 503, request)
    except StopAsyncIteration:
        return err("tts_failed", "Timbre returned no audio.", 503, request)
    tts = providers.tts()
    mime = item.mime or (tts.mime_for(item.telephone) if tts else "audio/mpeg")

    async def gen():
        yield first
        async for chunk in rest:
            yield chunk
    headers = {"Cache-Control": "no-store", "X-Speech-Mode": str(stats.get("mode", "stream"))}
    if item.audio is not None:
        return Response(item.audio, media_type=mime, headers=headers)
    return StreamingResponse(gen(), media_type=mime, headers=headers)


async def decline(request: Request):
    d = await body(request, Decline)
    if d.ticket_id:
        def go(con):
            t = con.execute("SELECT caller_hash FROM tickets WHERE id=?", (d.ticket_id,)).fetchone()
            if t and t["caller_hash"] == hash_id(d.device):
                tickets._event(con, d.ticket_id, "caller", "verify_declined", detail="caller declined the verification call")
        with_con(go)
    return JSONResponse({"ok": True})


async def my_tickets(request: Request):
    return JSONResponse(pipeline.my_tickets(device_param(request)))


async def villages(request: Request):
    rows = with_con(db.villages)
    keep = ("id", "name", "taluka", "district", "lat", "lon", "coord_source", "coord_quality")
    return JSONResponse([{k: v.get(k) for k in keep} for v in rows])


def _loop_counts(con, synthetic: bool) -> dict:
    where = "" if synthetic else " WHERE is_synthetic=0"
    calls = con.execute("SELECT COUNT(*) FROM calls WHERE kind='report' AND turns>0").fetchone()[0]
    verify_calls = con.execute("SELECT COUNT(*) FROM calls WHERE kind='verify' AND turns>0").fetchone()[0]
    t = con.execute("SELECT COUNT(*) AS n, SUM(ack_at IS NOT NULL) AS acked, SUM(fix_claimed_at IS NOT NULL) AS claimed,"
                    " SUM(state='VERIFIED') AS verified, SUM(reopened_count>0) AS reopened FROM tickets" + where).fetchone()
    return {"report_calls": calls, "verification_calls": verify_calls, "tickets": t["n"] or 0,
            "acknowledged": t["acked"] or 0, "fix_claimed": t["claimed"] or 0, "verified": t["verified"] or 0,
            "reopened": t["reopened"] or 0}


async def public_summary(request: Request):
    syn = synthetic_flag(request)

    def go(con):
        m = tickets.metrics(con, include_synthetic=syn)
        keep = {k: m[k] for k in ("total", "open", "by_state", "p1_open", "median_ack_min", "n_ack",
                                  "median_fix_to_verified_min", "n_fix_verified", "false_closure", "synthetic_tickets")}
        keep["repeat_sources"] = len(m["repeat_sources"])
        keep["loop"] = _loop_counts(con, syn)
        return keep
    return JSONResponse(with_con(go))


# ------------------------------------------------------------------ auth
async def login(request: Request):
    limit(request)
    d = await body(request, PinIn)
    role = role_for_pin(d.pin)
    if not role:
        raise ApiError("bad_pin", "That PIN is not recognised.", 401)
    request.session.clear()
    request.session.update(role=role, csrf=secrets.token_urlsafe(16))
    return JSONResponse({"role": role, "csrf": request.session["csrf"]})


async def logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})


async def me(request: Request):
    out = {"role": request.session.get("role"), "csrf": request.session.get("csrf"), "demo_mode": settings.DEMO_MODE}
    defaults = settings.defaults_in_use
    if settings.DEMO_MODE and "ENGINEER_PIN" in defaults and "OFFICER_PIN" in defaults:
        out["demo_pins"] = {"engineer": settings.ENGINEER_PIN, "officer": settings.OFFICER_PIN}
    return JSONResponse(out)


# ------------------------------------------------------------------ officer + engineer
async def list_tickets(request: Request):
    require(request, "officer", "engineer")
    syn = synthetic_flag(request)
    return JSONResponse(with_con(lambda c: tickets.with_sla(tickets.list_tickets(c, include_synthetic=syn))))


async def ticket_detail(request: Request):
    require(request, "officer", "engineer")
    tid = int(request.path_params["tid"])

    def go(con):
        t = tickets.detail(con, tid)
        tickets.with_sla([t])
        t["sms"] = [dict(r) for r in con.execute("SELECT at, to_role, body FROM sms_log WHERE ticket_id=? ORDER BY id", (tid,))]
        return t
    try:
        return JSONResponse(with_con(go))
    except tickets.TransitionError as e:
        raise ApiError("not_found", str(e), 404)


def _engineer_action(fn):
    async def handler(request: Request):
        require(request, "engineer", csrf=True)
        tid = int(request.path_params["tid"])
        note = ""
        if request.headers.get("content-type", "").startswith("application/json"):
            note = (await body(request, NoteIn)).note

        def go(con):
            fn(con, tid, note)
            t = tickets.detail(con, tid)
            tickets.with_sla([t])
            return t
        try:
            return JSONResponse(with_con(go))
        except tickets.TransitionError as e:
            raise ApiError("bad_transition", str(e), 409)
    return handler


async def metrics(request: Request):
    require(request, "officer", "engineer")
    syn = synthetic_flag(request)

    def go(con):
        m = tickets.metrics(con, include_synthetic=syn)
        m["insights"] = tickets.insights(con, include_synthetic=syn)
        m["loop"] = _loop_counts(con, syn)
        return m
    return JSONResponse(with_con(go))


async def activity(request: Request):
    require(request, "officer", "engineer")
    n = max(1, min(200, int(request.query_params.get("limit", "40") or 40)))
    syn = synthetic_flag(request)
    return JSONResponse(with_con(lambda c: tickets.activity(c, include_synthetic=syn, limit=n)))


async def sms_log(request: Request):
    require(request, "officer", "engineer")
    return JSONResponse(with_con(lambda c: [dict(r) for r in c.execute(
        "SELECT s.*, t.ref, t.is_synthetic FROM sms_log s LEFT JOIN tickets t ON t.id=s.ticket_id"
        " ORDER BY s.id DESC LIMIT 30")]))


async def export_csv(request: Request):
    require(request, "officer")
    syn = synthetic_flag(request)
    rows = with_con(lambda c: tickets.list_tickets(c, include_synthetic=syn))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(tickets.EXPORT_COLUMNS)
    for r in rows:
        w.writerow([r.get(k) for k in tickets.EXPORT_COLUMNS])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="jalawaaz_tickets.csv"'})


async def bench(request: Request):
    """Measured evaluation results plus live, logged Gnani call statistics."""
    f = ROOT / "bench" / "results" / "latest.json"
    results = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def go(con):
        live = [dict(r) for r in con.execute(
            "SELECT service, model, COUNT(*) AS calls, SUM(ok) AS ok, SUM(cached) AS cached,"
            " ROUND(AVG(CASE WHEN ok=1 THEN ms END),0) AS avg_ms, MIN(at) AS first_at, MAX(at) AS last_at"
            " FROM api_calls GROUP BY service, model ORDER BY service")]
        lat = {}
        for svc in ("stt", "tts", "tts-stream", "llm"):
            ms = sorted(r[0] for r in con.execute("SELECT ms FROM api_calls WHERE service=? AND ok=1", (svc,)))
            if ms:
                lat[svc] = {"n": len(ms), "p50": round(ms[len(ms) // 2]), "p95": round(ms[min(len(ms) - 1, int(len(ms) * .95))])}
        tt = sorted(r[0] for r in con.execute("SELECT ttfb_ms FROM api_calls WHERE service='tts-stream' AND ok=1 AND ttfb_ms IS NOT NULL"))
        if tt:
            lat["tts-first-audio"] = {"n": len(tt), "p50": round(tt[len(tt) // 2]), "p95": round(tt[min(len(tt) - 1, int(len(tt) * .95))])}
        errors = [dict(r) for r in con.execute(
            "SELECT service, status, error_kind, COUNT(*) AS n, MAX(at) AS last_at FROM api_calls WHERE ok=0"
            " GROUP BY service, status, error_kind ORDER BY last_at DESC LIMIT 10")]
        calls = [dict(r) for r in con.execute(
            "SELECT kind, COUNT(*) AS n, ROUND(AVG(turns),1) AS avg_turns, ROUND(AVG(total_ms/turns),0) AS avg_turn_ms,"
            " SUM(outcome='ticket') AS tickets, SUM(outcome='handoff') AS handoffs, SUM(outcome='verified') AS verified,"
            " SUM(outcome='reopened') AS reopened, SUM(telephone) AS telephone FROM calls WHERE turns>0 GROUP BY kind")]
        return live, lat, errors, calls
    live, lat, errors, calls = with_con(go)
    return JSONResponse({"text_eval": evaluation.latest(), "benchmark": results, "live_api_calls": live,
                         "live_latency_ms": lat, "api_errors": errors, "calls": calls,
                         "credits_exhausted": GNANI_STATE["credits_exhausted"]})


async def bench_run_text(request: Request):
    require(request, "officer", "engineer", csrf=True)
    return JSONResponse(await evaluation.run())


async def system(request: Request):
    require(request, "officer", "engineer")

    def go(con):
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("tickets", "reports", "calls", "api_calls", "villages", "sms_log")}
        counts["synthetic_tickets"] = demo.count(con)
        counts["villages_on_map"] = con.execute("SELECT COUNT(*) FROM villages WHERE lat IS NOT NULL").fetchone()[0]
        return counts
    cfg = settings.cfg
    warnings = []
    for name in settings.defaults_in_use:
        warnings.append(f"{name} still has its example value; set your own in .env before showing anyone.")
    if not settings.gnani_configured:
        warnings.append("GNANI_API_KEY is empty: voice input is off and replies use the browser voice.")
    if not ffmpeg_available():
        warnings.append("ffmpeg was not found: phone recordings cannot be converted for Prisma.")
    st = await providers.status()
    if st["tts"]["voice_config_error"]:
        warnings.append(st["tts"]["voice_config_error"])
    return JSONResponse({
        "version": VERSION, "python": sys.version.split()[0], "platform": platform.platform(terse=True),
        "demo_mode": settings.DEMO_MODE, "telephone_mode_default": settings.TELEPHONE_MODE,
        "providers": st, "counts": with_con(go), "warnings": warnings,
        "timings": {"callback_delay_sec": settings.DEMO_CALLBACK_DELAY_SEC, "verify_delay_sec": settings.DEMO_VERIFY_DELAY_SEC,
                    "verify_retry_sec": settings.DEMO_VERIFY_RETRY_SEC, "ignore_quiet_hours": settings.DEMO_IGNORE_QUIET_HOURS},
        "config": {k: cfg[k] for k in ("priority", "sla_hours", "calling", "gazetteer", "privacy") if k in cfg},
        "stt": {k: v for k, v in cfg.get("stt", {}).items() if k != "topic"}, "tts": cfg.get("tts"),
        "map": {"tile_url": settings.MAP_TILE_URL, "attribution": settings.MAP_TILE_ATTRIBUTION},
    })


async def check_gnani(request: Request):
    require(request, "officer", csrf=True)
    return JSONResponse(await providers.check_gnani())


async def demo_seed(request: Request):
    require(request, "officer", csrf=True)
    if not settings.DEMO_MODE:
        raise ApiError("not_demo", "Demo data can only be added when DEMO_MODE=1.", 409)
    return JSONResponse({"added": with_con(demo.seed)})


async def demo_clear(request: Request):
    require(request, "officer", csrf=True)
    if not settings.DEMO_MODE:
        raise ApiError("not_demo", "Demo data can only be removed when DEMO_MODE=1.", 409)
    return JSONResponse({"removed": with_con(demo.clear)})


async def openapi_json(request: Request):
    return JSONResponse(openapi.spec())


async def map_config(request: Request):
    return JSONResponse({"tile_url": settings.MAP_TILE_URL, "attribution": settings.MAP_TILE_ATTRIBUTION})


# ------------------------------------------------------------------ middleware + app
class RequestMeta(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.rid = uuid.uuid4().hex[:12]
        try:
            resp = await call_next(request)
        except ApiError as e:
            resp = err(e.code, e.message, e.status, request)
        except Exception:
            log.exception("unhandled error rid=%s path=%s", request.state.rid, request.url.path)
            resp = err("server_error", "Something went wrong on the server. The request id is logged.", 500, request)
        resp.headers["X-Request-ID"] = request.state.rid
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
        return resp


async def api_error(request: Request, exc: ApiError):
    return err(exc.code, exc.message, exc.status, request)


async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return err("not_found", "No such endpoint. See /docs.", 404, request)
    return FileResponse(WEB / "404.html", status_code=404)


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    for name in settings.defaults_in_use:
        log.warning("%s is still the example value. Set a real value in .env before any pilot.", name)
    task = asyncio.create_task(scheduler.run_forever())
    log.info("Jal Awaaz %s up. Providers: %s", VERSION, json.dumps(await providers.status(), default=str))
    yield
    task.cancel()


routes = [
    Route("/", page("index.html")),
    Route("/phone", page("phone.html")),
    Route("/login", page("login.html")),
    Route("/docs", page("docs.html")),
    Route("/dashboard", protected_page("dashboard.html", ("officer", "engineer"))),
    Route("/engineer", protected_page("engineer.html", ("engineer",))),
    Route("/metrics", page("metrics.html")),
    Route("/favicon.ico", lambda r: FileResponse(WEB / "assets" / "favicon.svg", media_type="image/svg+xml")),
    Route("/health", health),
    Route("/api/status", status),
    Route("/api/missed-call", missed_call, methods=["POST"]),
    Route("/api/poll", poll),
    Route("/api/session", start_session, methods=["POST"]),
    Route("/api/turn", turn, methods=["POST"]),
    Route("/api/speech/{sid}", speech_audio),
    Route("/api/decline", decline, methods=["POST"]),
    Route("/api/my-tickets", my_tickets),
    Route("/api/villages", villages),
    Route("/api/map-config", map_config),
    Route("/api/public/summary", public_summary),
    Route("/api/login", login, methods=["POST"]),
    Route("/api/logout", logout, methods=["POST"]),
    Route("/api/me", me),
    Route("/api/tickets", list_tickets),
    Route("/api/tickets/{tid:int}", ticket_detail),
    Route("/api/tickets/{tid:int}/ack", _engineer_action(lambda c, t, n: tickets.ack(c, t)), methods=["POST"]),
    Route("/api/tickets/{tid:int}/fix-claimed", _engineer_action(lambda c, t, n: tickets.fix_claimed(c, t, note=n)), methods=["POST"]),
    Route("/api/tickets/{tid:int}/note", _engineer_action(lambda c, t, n: tickets.add_note(c, t, n)), methods=["POST"]),
    Route("/api/metrics", metrics),
    Route("/api/activity", activity),
    Route("/api/sms", sms_log),
    Route("/api/export/tickets.csv", export_csv),
    Route("/api/bench", bench),
    Route("/api/bench/run-text", bench_run_text, methods=["POST"]),
    Route("/api/system", system),
    Route("/api/system/check-gnani", check_gnani, methods=["POST"]),
    Route("/api/demo/seed", demo_seed, methods=["POST"]),
    Route("/api/demo/clear", demo_clear, methods=["POST"]),
    Route("/api/openapi.json", openapi_json),
    Mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets"),
]

app = Starlette(
    routes=routes, lifespan=lifespan,
    middleware=[Middleware(RequestMeta),
                Middleware(SessionMiddleware, secret_key=settings.APP_SECRET, session_cookie="ja_session",
                           max_age=8 * 3600, same_site="strict", https_only=False)],
    exception_handlers={ApiError: api_error, 404: not_found},
)
