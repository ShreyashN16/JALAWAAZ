# API

The live reference is at **`/docs`** (rendered from `app/openapi.py`, which a test keeps in step with the
routes). This page adds examples. Base URL below: `http://localhost:8000`.

## Conventions

- JSON in and out, except `/api/turn` (multipart), `/api/speech/{id}` (audio) and the CSV export.
- Errors: `{"error": {"code": "bad_transition", "message": "cannot move ticket from NEW to VERIFIED", "request_id": "3f…"}}`.
  Every response has an `X-Request-ID` header that matches the server log.
- Staff endpoints need the `ja_session` cookie from `POST /api/login`. Endpoints that change data also need
  `X-CSRF-Token: <csrf from login or /api/me>`.
- Public phone endpoints are rate limited per IP (`rate_limit.per_minute`, default 60).
- Times are UTC strings `YYYY-MM-DD HH:MM:SS`; the pages show them in IST.

## A complete call with curl (typed turns, no audio)

```bash
DEV=my-test-device-01
curl -s -X POST localhost:8000/api/missed-call -H 'content-type: application/json' -d "{\"device\":\"$DEV\"}"
# {"queued": true, "callback_in_sec": 5, "simulated": true}
sleep 6; curl -s "localhost:8000/api/poll?device=$DEV"
# {"incoming": "callback", "ticket_id": null, "simulated": true}
SID=$(curl -s -X POST localhost:8000/api/session -H 'content-type: application/json' \
      -d "{\"device\":\"$DEV\",\"mode\":\"report\",\"lang\":\"mr\"}" | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s -X POST localhost:8000/api/turn -F session_id=$SID -F "text=Shivapur madhe handpump 3 divas band aahe, 40 ghar"
curl -s -X POST localhost:8000/api/turn -F session_id=$SID -F text=nahi     # not drinking water
curl -s -X POST localhost:8000/api/turn -F session_id=$SID -F text=ho       # confirms the read-back
# {"done": true, "outcome": "ticket", "ticket_ref": "40712", "reply_text": "… तक्रार क्रमांक 40712 …", ...}
```

Send audio instead of text with `-F audio=@answer.webm`. Any format ffmpeg reads works; the server converts
it to 16 kHz WAV, transcribes it with Prisma and deletes it.

## Phone endpoints

### `POST /api/session`

```json
{"device": "my-test-device-01", "mode": "report", "lang": "mr", "telephone": false}
```

`mode: "verify"` needs `ticket_id` and only works from the device that reported the ticket (403 otherwise)
and only while the ticket is `FIX_CLAIMED` (409 otherwise). Returns:

```json
{"session_id": "…", "reply_text": "नमस्कार, मी जल आवाज, एक एआय सहायक आहे. …",
 "speech_text": "…", "audio_url": "/api/speech/kq3…", "mime": "audio/mpeg", "browser_voice": false,
 "state": "GREET", "lang": "mr", "simulated_call": true, "telephone": false}
```

### `POST /api/turn` (multipart: `session_id` and `audio` or `text`)

```json
{"transcript": "Shivapur madhe handpump 3 divas band aahe, 40 ghar",
 "reply_text": "हे पिण्याचे पाणी आहे का?", "speech_text": "…", "audio_url": "/api/speech/…",
 "done": false, "state": "COLLECT", "expecting": "drinking_source",
 "report": {"village": "Shivapur", "village_matched": "Khed Shivapur", "village_on_map": true,
            "source_type": "handpump", "fault": "no_water", "duration_days": 3, "households_affected": 40, "…": "…"},
 "providers": {"stt": "prisma", "llm": "rules", "tts": "timbre"},
 "stt": {"model": "prisma-v3.0", "detected": "mr-IN", "language_code": "mr-IN", "context": ["keyterms", "topic", "previous_text"]},
 "timings_ms": {"stt_ms": 1090, "llm_ms": 0, "until_text_ms": 1130}, "notices": []}
```

`outcome` on the last turn is `ticket`, `handoff`, `verified`, `reopened`, `no_answer` or `error`.

### `GET /api/speech/{id}`

Audio for one reply. Streams MP3 while Timbre synthesises (header `X-Speech-Mode: stream`), or serves a
cached prompt (`cache`) or the in-memory copy on replay (`memory`). 404 after three minutes; 503 JSON if
Timbre failed (the text is already on screen).

### `GET /api/my-tickets?device=…`

Status of tickets reported from that device only: ref, state, priority, village, source, fault, times.

## Staff endpoints

```bash
curl -s -c jar -X POST localhost:8000/api/login -H 'content-type: application/json' -d '{"pin":"2468"}'
# {"role": "engineer", "csrf": "Zt…"}
curl -s -b jar localhost:8000/api/tickets
curl -s -b jar -X POST localhost:8000/api/tickets/7/ack -H 'X-CSRF-Token: Zt…'
curl -s -b jar -X POST localhost:8000/api/tickets/7/fix-claimed -H 'X-CSRF-Token: Zt…' \
     -H 'content-type: application/json' -d '{"note":"washer replaced"}'
```

| Endpoint | Role | Notes |
|---|---|---|
| `GET /api/tickets?synthetic=0\|1` | engineer, officer | includes `priority_reason`, `sla_due_at`, `sla_overdue`, village coordinates and their source. Never the caller hash. |
| `GET /api/tickets/{id}` | engineer, officer | plus `events` (audit), `verifications`, `sms` |
| `POST /api/tickets/{id}/ack` | engineer + CSRF | `NEW` or `REOPENED` → `ACKED`; 409 otherwise |
| `POST /api/tickets/{id}/fix-claimed` | engineer + CSRF | → `FIX_CLAIMED`, queues the verification call; auto-acknowledges a `NEW` ticket |
| `POST /api/tickets/{id}/note` | engineer + CSRF | appends a timestamped note |
| `GET /api/metrics` | engineer, officer | headline numbers with n, `repeat_sources`, `insights` (14-day series, fault and source mix, per-village counts, SLA overdue list), `loop` counts |
| `GET /api/activity?limit=40` | engineer, officer | audit events with ticket ref and village |
| `GET /api/sms` | engineer, officer | simulated SMS log |
| `GET /api/export/tickets.csv` | officer | fields and timestamps; no caller hash, no transcript |
| `POST /api/bench/run-text` | engineer, officer + CSRF | runs the text evaluation (no credits) |
| `GET /api/system` | engineer, officer | providers, warnings, thresholds, counts |
| `POST /api/system/check-gnani` | officer + CSRF | validates the key with Prisma's language list |
| `POST /api/demo/seed`, `/api/demo/clear` | officer + CSRF, `DEMO_MODE=1` only | add or remove the 14 synthetic tickets |

## Public, read-only

`GET /health`, `/api/status`, `/api/villages`, `/api/map-config`, `/api/public/summary` (aggregates only,
safe for a wall screen), `/api/bench` (evaluation results and live latency), `/api/openapi.json`.
