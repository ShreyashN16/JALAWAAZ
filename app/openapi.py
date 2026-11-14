"""OpenAPI 3.1 description of the HTTP API, served at /api/openapi.json and rendered at /docs.

Kept by hand next to the routes in app/main.py; tests/test_docs.py fails if a route is missing here.
Auth: "public" needs nothing; "staff" needs an engineer or officer session cookie; "engineer" /
"officer" need that role; state-changing staff calls also need the X-CSRF-Token header from /api/login.
"""
from __future__ import annotations

from .config import VERSION

# (method, path, auth, tag, summary, request description, response description)
ENDPOINTS = [
    ("GET", "/health", "public", "System", "Liveness and dependency check",
     None, "ok, db, ffmpeg, providers, demo_mode, version"),
    ("GET", "/api/status", "public", "System", "Which model serves each role right now, and demo timings",
     None, "providers {stt, tts, llm}, demo_mode, callback_delay_sec, verify_delay_sec, max_utterance_seconds"),
    ("POST", "/api/missed-call", "public", "Phone", "Ask for a (simulated) callback",
     '{"device": "<8-80 chars>"}', "queued, callback_in_sec, simulated: true"),
    ("GET", "/api/poll", "public", "Phone", "Phone polls for an incoming simulated call",
     "query: device", "incoming: null | callback | verification, ticket_id?, ticket_ref?, lang?, next {kind, in_sec}?"),
    ("POST", "/api/session", "public", "Phone", "Answer a call: start a report or verification session",
     '{"device", "mode": "report|verify", "lang": "mr|hi|hinglish", "ticket_id"?, "telephone"?}',
     "session_id, reply_text (caption), speech_text, audio_url, mime, browser_voice, state, lang"),
    ("POST", "/api/turn", "public", "Phone", "One caller turn: audio (multipart file) or typed text",
     "multipart: session_id, audio (webm/mp4/wav, max 25 s) OR text",
     "transcript, reply_text, audio_url, done, outcome, ticket_ref, report (fields so far), providers, stt, timings_ms"),
    ("GET", "/api/speech/{speech_id}", "public", "Phone", "Spoken reply audio, streamed as Timbre synthesises it",
     None, "audio/mpeg (or audio/wav in telephone mode); 503 JSON if TTS failed"),
    ("POST", "/api/decline", "public", "Phone", "Caller declined a call",
     '{"device", "ticket_id"?}', "ok"),
    ("GET", "/api/my-tickets", "public", "Phone", "Tickets reported from this device (status only)",
     "query: device", "[{ref, state, priority, village, source_type, fault, created_at, ...}]"),
    ("GET", "/api/villages", "public", "Map", "Gazetteer: villages, coordinates and their sources",
     None, "[{id, name, taluka, district, lat, lon, coord_source, coord_quality}]"),
    ("GET", "/api/map-config", "public", "Map", "Map tile URL and attribution from .env", None, "tile_url, attribution"),
    ("GET", "/api/public/summary", "public", "Metrics", "Aggregates only, safe for a public screen",
     "query: synthetic=0|1", "total, open, by_state, p1_open, median times with n, false_closure, loop counts"),
    ("GET", "/api/bench", "public", "Metrics", "Measured evaluation: text evaluation, audio benchmark, live API latency",
     None, "text_eval, benchmark, live_api_calls, live_latency_ms, calls"),
    ("POST", "/api/login", "public", "Auth", "Sign in with an engineer or officer PIN",
     '{"pin"}', "role, csrf"),
    ("POST", "/api/logout", "public", "Auth", "Sign out", None, "ok"),
    ("GET", "/api/me", "public", "Auth", "Current role and CSRF token", None, "role, csrf, demo_pins?"),
    ("GET", "/api/tickets", "staff", "Tickets", "All tickets with fields, priority reason, SLA due time, location",
     "query: synthetic=0|1", "[ticket]"),
    ("GET", "/api/tickets/{id}", "staff", "Tickets", "One ticket with its audit timeline and verification attempts",
     None, "ticket + events[] + verifications[] + sms[]"),
    ("POST", "/api/tickets/{id}/ack", "engineer", "Tickets", "Acknowledge (NEW or REOPENED -> ACKED)",
     "header X-CSRF-Token", "ticket"),
    ("POST", "/api/tickets/{id}/fix-claimed", "engineer", "Tickets",
     "Report a fix. Never closes the ticket: it queues a verification call to the original caller",
     'header X-CSRF-Token; optional {"note"}', "ticket (state FIX_CLAIMED, next_verify_at)"),
    ("POST", "/api/tickets/{id}/note", "engineer", "Tickets", "Add a field note", 'X-CSRF-Token; {"note"}', "ticket"),
    ("GET", "/api/metrics", "staff", "Metrics", "Headline numbers with n, plus trends and breakdowns",
     "query: synthetic=0|1", "open, median_ack_min, median_fix_to_verified_min, false_closure, repeat_sources, insights"),
    ("GET", "/api/activity", "staff", "Tickets", "Recent audited ticket events", "query: synthetic, limit", "[event]"),
    ("GET", "/api/sms", "staff", "Tickets", "Simulated SMS log (no SMS is really sent)", None, "[sms]"),
    ("GET", "/api/export/tickets.csv", "officer", "Tickets", "CSV export without caller identifiers or transcripts",
     "query: synthetic=0|1", "text/csv"),
    ("POST", "/api/bench/run-text", "staff", "Metrics", "Run the text evaluation now (no Gnani credits)",
     "header X-CSRF-Token", "text evaluation result"),
    ("GET", "/api/system", "staff", "System", "Configuration summary, warnings, versions and counts", None, "system report"),
    ("POST", "/api/system/check-gnani", "officer", "System", "Validate the Gnani key with a metadata call",
     "header X-CSRF-Token", "ok, status, message"),
    ("POST", "/api/demo/seed", "officer", "System", "Add labelled synthetic demo tickets (demo mode only)",
     "header X-CSRF-Token", "added"),
    ("POST", "/api/demo/clear", "officer", "System", "Remove all synthetic tickets (demo mode only)",
     "header X-CSRF-Token", "removed"),
    ("GET", "/api/openapi.json", "public", "System", "This description", None, "OpenAPI 3.1 JSON"),
]

PAGES = [("/", "Overview and live loop"), ("/phone", "Villager phone (simulated callback)"),
         ("/engineer", "Engineer queue (engineer PIN)"), ("/dashboard", "District dashboard (officer or engineer PIN)"),
         ("/metrics", "Evaluation and system status"), ("/docs", "This API reference"), ("/login", "Staff sign-in")]


def spec() -> dict:
    paths: dict = {}
    for method, path, auth, tag, summary, req, resp in ENDPOINTS:
        op = {"tags": [tag], "summary": summary, "x-auth": auth,
              "responses": {"200": {"description": resp or "OK"}}}
        if req:
            op["x-request"] = req
        if auth != "public":
            op["security"] = [{"session": []}]
            op["responses"]["401"] = {"description": "Not signed in"}
            op["responses"]["403"] = {"description": "Wrong role or missing CSRF token"}
        params = [{"name": p.strip("{}"), "in": "path", "required": True, "schema": {"type": "string"}}
                  for p in path.split("/") if p.startswith("{")]
        if params:
            op["parameters"] = params
        paths.setdefault(path, {})[method.lower()] = op
    return {
        "openapi": "3.1.0",
        "info": {"title": "Jal Awaaz API", "version": VERSION,
                 "description": "Voice-first water fault reporting and caller verification. Independent prototype, "
                                "not an official service. Errors use {\"error\": {\"code\", \"message\", \"request_id\"}}."},
        "components": {"securitySchemes": {"session": {"type": "apiKey", "in": "cookie", "name": "ja_session"}}},
        "paths": paths, "x-pages": [{"path": p, "description": d} for p, d in PAGES],
    }
