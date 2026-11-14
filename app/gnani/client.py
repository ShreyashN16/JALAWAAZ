"""Shared Gnani HTTP client: serialised (semaphore), retried, timed, logged.

Shapes and status codes follow docs.gnani.ai (re-checked 2026-11-13, see docs/GNANI_INTEGRATION.md):
  401 MISSING_API_KEY / INVALID_API_KEY, 402 no credit, 403 SCOPE_NOT_ALLOWED,
  422 {"detail": [...]} validation (e.g. missing language_code), 429 RATE_LIMITED (some accounts
  allow one active request), 500/502/503/504 transient (504 on Prisma v3.0 is
  {"error": "Gateway Timeout", "code": "UPSTREAM_TIMEOUT", ...}).
Only 429 and 5xx are retried (0.5 s, 1 s backoff; three tries). Other 4xx are never retried.

Every request carries our own X-API-Request-ID so a failing call can be quoted to Gnani support;
the id, status and latency (never audio or text) go to the api_calls table.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from typing import AsyncIterator

try:  # the real package; httpx2 is an API-compatible fallback used in the build sandbox
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    import httpx2 as httpx  # type: ignore

from .. import db
from ..config import settings

RETRYABLE = {429, 500, 502, 503, 504}
TRANSPORT = None          # tests inject httpx.MockTransport here; None = real network
STATE = {"credits_exhausted": False, "last_error": None, "last_ok_at": None}
_sems: dict[int, asyncio.Semaphore] = {}


class GnaniError(Exception):
    def __init__(self, status: int, kind: str, message: str = "", request_id: str | None = None):
        super().__init__(f"{status} {kind}: {message}")
        self.status, self.kind, self.message, self.request_id = status, kind, message, request_id

    @property
    def user_hint(self) -> str:
        return {
            0: "Gnani did not respond. Check the internet connection.",
            401: "Gnani API key missing or invalid. Check GNANI_API_KEY in .env.",
            402: "Gnani credits exhausted. Replies switch to on-screen text.",
            403: "This API key lacks access to the requested model or scope.",
            422: "Gnani rejected the request format.",
            429: "Gnani rate limit reached (one request at a time). Try again in a moment.",
            504: "Gnani timed out. Try a shorter answer.",
        }.get(self.status, "Gnani service error.")


def _sem() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    s = _sems.get(id(loop))
    if s is None:
        s = _sems[id(loop)] = asyncio.Semaphore(max(1, settings.GNANI_CONCURRENCY))
    return s


def explain(r, request_id: str | None = None) -> GnaniError:
    """Turn any documented Gnani error body into a GnaniError."""
    try:
        j = r.json()
    except Exception:
        return GnaniError(r.status_code, "HTTP", (r.text or "")[:200], request_id)
    if not isinstance(j, dict):
        return GnaniError(r.status_code, "ERROR", str(j)[:300], request_id)
    if isinstance(j.get("detail"), list):                       # 422 validation
        msgs = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in j["detail"])
        return GnaniError(r.status_code, "VALIDATION", msgs[:300], request_id)
    if isinstance(j.get("error"), str) and j.get("code"):     # 504 UPSTREAM_TIMEOUT
        return GnaniError(r.status_code, str(j["code"]), str(j.get("message") or j["error"])[:300], request_id)
    err = j.get("error") or j.get("detail") or j
    if isinstance(err, dict):
        kind = err.get("type") or err.get("error_code") or "ERROR"
        return GnaniError(r.status_code, str(kind), str(err.get("message", ""))[:300], request_id)
    return GnaniError(r.status_code, "ERROR", str(err)[:300], request_id)


def make_client(timeout: float):
    kw = {"timeout": timeout}
    if TRANSPORT is not None:
        kw["transport"] = TRANSPORT
    return httpx.AsyncClient(**kw)


def _headers(extra: dict | None, rid: str) -> dict:
    h = {"X-API-Key-ID": settings.GNANI_API_KEY, "X-API-Request-ID": rid}
    h.update(extra or {})
    return h


def _precheck() -> None:
    if STATE["credits_exhausted"]:
        raise GnaniError(402, "NO_CREDIT", "credits exhausted earlier in this run")
    if not settings.GNANI_API_KEY:
        raise GnaniError(401, "NO_KEY", "GNANI_API_KEY is not set")


async def call(method: str, url: str, *, service: str, model: str, **kw):
    """Returns (response, ms). Raises GnaniError on exhausted credits or no response."""
    _precheck()
    rid = "ja-" + uuid.uuid4().hex[:16]
    headers = _headers(kw.pop("headers", None), rid)
    delay = 0.5
    r = None
    async with _sem():
        for attempt in range(3):
            t0 = time.perf_counter()
            r = None
            try:
                async with make_client(settings.GNANI_TIMEOUT_SEC) as c:
                    r = await c.request(method, url, headers=headers, **kw)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
                r = None
            ms = (time.perf_counter() - t0) * 1000
            status = r.status_code if r is not None else 0
            final = r is not None and status not in RETRYABLE
            db.log_api_call(service, model, status, ok=(status == 200), ms=ms, attempt=attempt,
                            error_kind=None if status == 200 else ("NETWORK" if r is None else str(status)),
                            request_id=rid)
            if final:
                if status == 402:
                    STATE["credits_exhausted"] = True
                if status == 200:
                    STATE["last_ok_at"] = time.time()
                else:
                    STATE["last_error"] = {"service": service, "status": status, "at": time.time()}
                return r, ms
            if attempt < 2:
                await asyncio.sleep(delay)
                delay *= 2
    STATE["last_error"] = {"service": service, "status": r.status_code if r is not None else 0, "at": time.time()}
    if r is not None:
        raise explain(r, rid)
    raise GnaniError(0, "UNAVAILABLE", "Gnani API did not respond after 3 tries", rid)


def parse_sse(lines: list[str]) -> tuple[str | None, dict | None]:
    """One SSE event block -> (event name, JSON payload)."""
    event, data = None, []
    for ln in lines:
        if ln.startswith("event:"):
            event = ln[6:].strip()
        elif ln.startswith("data:"):
            data.append(ln[5:].strip())
    payload = None
    if data:
        try:
            payload = json.loads("\n".join(data))
        except json.JSONDecodeError:
            payload = {"raw": "\n".join(data)}
    if event is None and isinstance(payload, dict):     # some servers put the type in the payload
        event = payload.get("type") or ("complete" if payload.get("is_final") else "chunk" if "audio" in payload else None)
    return event, payload


async def stream_sse(url: str, *, service: str, model: str, json_body: dict, stats: dict | None = None) -> AsyncIterator[bytes]:
    """POST to a Gnani SSE endpoint and yield decoded audio bytes as they arrive.

    Retries (429/5xx/network) happen only before the first audio byte. Raises GnaniError if no
    audio could be produced, so callers can fall back to the REST endpoint. `stats` receives
    ttfb_ms, ms and bytes for the call log and the latency panel.
    """
    _precheck()
    rid = "ja-" + uuid.uuid4().hex[:16]
    headers = _headers({"Accept": "text/event-stream"}, rid)
    stats = stats if stats is not None else {}
    delay = 0.5
    async with _sem():
        for attempt in range(3):
            t0 = time.perf_counter()
            got = 0
            status = 0
            try:
                async with make_client(settings.GNANI_TIMEOUT_SEC) as c:
                    async with c.stream("POST", url, headers=headers, json=json_body) as r:
                        status = r.status_code
                        if status != 200:
                            await r.aread()
                            if status in RETRYABLE and attempt < 2:
                                db.log_api_call(service, model, status, False, (time.perf_counter() - t0) * 1000,
                                                attempt, str(status), rid)
                                await asyncio.sleep(delay)
                                delay *= 2
                                continue
                            if status == 402:
                                STATE["credits_exhausted"] = True
                            db.log_api_call(service, model, status, False, (time.perf_counter() - t0) * 1000,
                                            attempt, str(status), rid)
                            raise explain(r, rid)
                        block: list[str] = []
                        async for line in r.aiter_lines():
                            if line.strip():
                                block.append(line)
                                continue
                            if not block:
                                continue
                            event, payload = parse_sse(block)
                            block = []
                            if event == "error":
                                msg = (payload or {}).get("message", "stream error")
                                if got == 0:
                                    raise GnaniError(500, "STREAM_ERROR", str(msg)[:300], rid)
                                stats["stream_error"] = str(msg)[:200]
                                continue
                            audio_b64 = (payload or {}).get("audio") or ""
                            if audio_b64:
                                chunk = base64.b64decode(audio_b64)
                                if got == 0:
                                    stats["ttfb_ms"] = (time.perf_counter() - t0) * 1000
                                got += len(chunk)
                                yield chunk
                            if event == "complete" or (payload or {}).get("is_final"):
                                break
                        if block:                                     # stream ended without a blank line
                            event, payload = parse_sse(block)
                            audio_b64 = (payload or {}).get("audio") or ""
                            if audio_b64:
                                chunk = base64.b64decode(audio_b64)
                                stats.setdefault("ttfb_ms", (time.perf_counter() - t0) * 1000)
                                got += len(chunk)
                                yield chunk
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                ms = (time.perf_counter() - t0) * 1000
                db.log_api_call(service, model, 0, False, ms, attempt, "NETWORK", rid)
                if got == 0 and attempt < 2:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                if got == 0:
                    raise GnaniError(0, "UNAVAILABLE", f"stream failed: {type(e).__name__}", rid)
                stats["stream_error"] = type(e).__name__
            ms = (time.perf_counter() - t0) * 1000
            stats.update(ms=ms, bytes=got, request_id=rid)
            if got == 0:
                db.log_api_call(service, model, 200, False, ms, attempt, "EMPTY_STREAM", rid)
                raise GnaniError(200, "EMPTY_AUDIO", "Timbre stream returned no audio", rid)
            db.log_api_call(service, model, 200, True, ms, attempt, None, rid, ttfb_ms=stats.get("ttfb_ms"))
            STATE["last_ok_at"] = time.time()
            return
