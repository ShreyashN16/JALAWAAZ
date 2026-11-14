# Privacy and security

Jal Awaaz is a prototype. Use consenting test users and synthetic data, never route real complaints to
an authority, and do not put real villager data through a public tunnel.

## What is stored

| Data | Stored? | Where / how long |
|---|---|---|
| Caller's voice | **No** | In memory and a temporary folder during transcription, then deleted |
| Reply audio (Timbre) | Fixed prompts only | `tts_cache/` on disk; replies with caller details stay in memory for 3 minutes, never on disk |
| Phone number / device id | **Only as a salted HMAC-SHA256 hash** | `tickets.caller_hash`, `calls`, `outbox`. Never returned by any API. |
| Transcript of the report | Yes | `reports.transcript`, erased after `privacy.transcript_retention_days` (90). Hidden in the dashboard's public view; not in CSV exports |
| Complaint fields | Yes | village, source, fault, days, households, drinking, symptoms (only what the caller said) |
| Audit trail | Yes | `ticket_events`: who did what and when (roles, not names) |
| Gnani/Evon call log | Status, latency, request id | `api_calls`; never audio or text |
| Names, Aadhaar, bank details | **Never asked, never stored** | |

The device id on the phone page is a random UUID kept in the browser's local storage; it stands in for a
phone number in the simulated callback.

## Who can see what

| | Public (no sign-in) | Engineer | Officer |
|---|---|---|---|
| Phone, own complaint status | yes (own device only) | | |
| Aggregates (`/api/public/summary`, overview page) | yes | yes | yes |
| Evaluation and latency (`/metrics`) | yes | yes + system | yes + system, key check |
| Ticket list and details, activity, SMS | no | yes | yes |
| Acknowledge, report fix, notes | no | yes | no (view only) |
| CSV export, demo data controls | no | no | yes |

## Controls in the code

- **Staff sign-in**: PIN → role (`security.role_for_pin`, constant-time compare). Signed session cookie
  (`ja_session`, HttpOnly, SameSite=Strict, 8 hours). Every state-changing staff request needs the
  `X-CSRF-Token` from the session.
- **Verification only by the original caller**: `/api/session` with `mode=verify` checks the device hash
  against the ticket (403 otherwise).
- **Illegal state changes are impossible**: Python checks plus a database trigger.
- **Input limits**: Pydantic validation; recordings ≤ 2 MB and ≤ 30 s; typed answers ≤ 500 characters;
  notes ≤ 500 characters; per-IP rate limit on public endpoints.
- **No HTML injection**: the pages build every element with `textContent` (the `h()` helper); caller text
  is never inserted as HTML.
- **Headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`,
  `Permissions-Policy: microphone=(self)`, `Cache-Control: no-store` on pages.
- **Errors**: users see a plain message and a request id; the stack trace goes only to the server log, and
  logs never contain transcripts.
- **Secrets**: `.env` is git-ignored. `.env.example` contains no key. `scripts/doctor.py` warns while
  `APP_SALT`, `APP_SECRET` or the PINs are still example values; the sign-in page shows demo PINs only
  while they are unchanged and `DEMO_MODE=1`.

**Action for you:** an earlier version of `.env.example` in this folder contained a real Gnani key. If that
file was ever shared or committed anywhere, revoke the key at app.gnani.ai and create a new one.

## Known gaps (prototype)

- PINs, not user accounts: no per-person audit, no lockout beyond the rate limit.
- No HTTPS of its own: use a tunnel or a reverse proxy for anything beyond localhost.
- SQLite file is not encrypted at rest.
- The in-memory rate limiter and call sessions reset when the server restarts.

## Safety

- The assistant gives one fixed informational line, only for drinking-water reports with symptoms or
  contamination (boil the water or use another source, and tell the health worker). No diagnosis, no other
  health advice. The wording must be checked against official guidance before any pilot.
- AI is disclosed in the first sentence of every call, and "independent prototype, not an official
  service" is visible on every page.
- Verification calls: at most 3 attempts, never 21:00–07:00 in real mode.
- Public view shows aggregates only, so a reporter cannot be identified from a wall screen.
