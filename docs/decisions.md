# Decisions log

Where the build spec (docs/SPEC.md) and the master directive disagreed, or left a gap, the final
decision is recorded here. Edit this file, not the chat, when a decision changes.

| # | Topic | Decision | Why |
|---|---|---|---|
| D1 | Web framework | **Starlette** (the ASGI toolkit FastAPI is built on) with Pydantic models for request validation, instead of FastAPI itself. | The build sandbox could not install FastAPI, and the directive says nothing counts as done until it is tested. Starlette let the whole HTTP layer, including the five-act demo, be tested end to end. Routes are thin; moving to FastAPI is a mechanical change (decorators, `Form`/`File`) if wanted for auto `/docs`. |
| D2 | HTTP client | `httpx` (falls back to the API-compatible `httpx2` only where `httpx` is absent). | Same reason as D1. |
| D3 | Village matching | `rapidfuzz` when installed; otherwise a pure-Python scorer with the same definitions (`ratio`, `token_set_ratio`). | Removes a hard dependency; scores are close but not identical, so thresholds should be re-checked once rapidfuzz is installed. |
| D4 | WER | Own implementation in `bench/wer.py` with documented normalisation (identical maths to jiwer). | Normalisation must be visible for Devanagari (danda, nukta, digits). |
| D5 | Number ranges | "do teen din", "चार पाच घरे" become the higher value. | Conservative for priority; the read-back lets the caller correct it. |
| D6 | Fractions | Kept as decimals by the normaliser; durations are rounded **up** by validators. | "dhai din" (2.5) should not become 2 days. |
| D7 | Hindi "tera" / "तेरा" | Never parsed as Marathi 13. | It is the Hindi word "your". |
| D8 | Symptom schema | Added `stomach_pain` to the allowed symptoms. | The spec's own question asks about पोटदुखी and its few-shot example is "pot dukhtay"; without the enum value it would be silently dropped. |
| D9 | Ticket number | Random 5-digit reference, spoken digit by digit and repeated once. | Short enough to write down; not sequential (no enumeration of tickets). |
| D10 | Follow-up limits | Max 3 optional questions and max 5 questions in total; required fields (village, source, fault) are always asked within that budget, then hand off with no ticket. | The spec's sketch could loop forever on a missing required field. |
| D11 | Unknown village | Ask once more; on a second unknown name keep what was said, flag the report for review, location shown as unavailable. | Never invent a location; never block a real complaint just because the gazetteer is incomplete. |
| D12 | Coordinates | v1: two villages with cited coordinates. **v2:** six of nine (2 cited from Wikipedia, 4 marked `approximate` from a PIN directory or place-centre source, each checked against the census distance from Pune), plus Khadakwasla added. Sources that return a default point for unknown places (one placed Sangrun and Donje in central Pune) were rejected. Sangrun, Khanapur and Malkhed stay off the map. | Never invent coordinates; label quality where it appears. |
| D13 | Verification attempts | An attempt is counted when the call is queued. After `max_verify_attempts` (3) with no yes/no answer, UNVERIFIED. Unclear answers twice = no answer for that attempt. | Matches "no answer after retries" without a separate call-status channel. |
| D14 | Reopen priority | Recomputed with `reopened_count`, and never lower than the current priority. | A reopen must never make a ticket less urgent. |
| D15 | P1 SLA | A P1 ticket past its SLA is logged as an `sla_breach_p1` event without changing the reason text. | P1 cannot go higher; avoids an ever-growing reason string. |
| D16 | Quiet hours in demo | `DEMO_IGNORE_QUIET_HOURS=1` only when `DEMO_MODE=1`, and the demo is labelled "time compressed". | A night-time demo would otherwise never ring. Real mode always defers to 07:00 IST. |
| D17 | TTS caching | Only static template sentences are cached to disk. Read-backs and ticket numbers (caller data) are never cached. | Directive: never retain dynamic caller audio. |
| D18 | Missing Gnani key | Voice input is disabled with a clear message and the caller can type; the browser's own voice reads replies, labelled "browser voice (Timbre off)". No other STT is ever substituted. | Directive: never silently substitute a model. |
| D19 | Staff auth | PIN login (engineer or officer role) with a signed, SameSite=Strict cookie and a CSRF header on every state change. Officers can view; only engineers can change tickets. | Simplest real RBAC for a prototype; PINs live in `.env`. |
| D20 | Language for Hinglish replies | Code-mixed Hindi written in Devanagari, spoken with `hi-IN`. | Timbre reads Devanagari reliably; `hi-en` with Poorvi is available if `GNANI_TTS_MODEL=timbre-v2.5`. |
| D21 | Anti-hallucination | Numbers Evon returns that do not appear in the transcript are dropped (rules refill from the transcript); the read-back is a template. | Evon never invents a household count or a duration that reaches a ticket. |

## v2.0.0 (2026-11-13)

| # | Topic | Decision | Why |
|---|---|---|---|
| D22 | Gnani API refresh | Re-read docs.gnani.ai on 2026-11-13 and adopted: Prisma `topic`, `previous_text`, substitution map, `X-API-Request-ID`, 422/504 shapes, `truncated`; Timbre MP3/mu-law containers, SSE streaming, audio tags, speed; full voice catalogues. | The spec predates these features; each one improves accuracy, latency or error handling (docs/GNANI_INTEGRATION.md). |
| D23 | `previous_text` = the assistant's last question | Sent on every turn. | Short answers ("40", "ho") are the hardest to transcribe and the easiest to disambiguate with the question. |
| D24 | Browser audio = MP3 streamed over SSE | Turn returns text immediately with an `audio_url`; `/api/speech/<id>` streams Timbre's MP3 chunks; REST fallback before the first byte. | v1 waited ~3.2 s for the full WAV before anything played. MP3 is ~4x smaller over a tunnel. |
| D25 | Numbers spoken as words, ticket digits one by one | `app/nlp/spoken.py` reuses the parser's 1–100 tables. Captions keep digits. | Timbre's reference asks for words; its digit-run rule reads 5-digit refs as a quantity. |
| D26 | Reply audio retention | Dynamic reply audio lives in memory for 3 minutes (replay without a new credit), never on disk. | Extends D17 without keeping caller details on disk. |
| D27 | Telephone mode asks Timbre for mu-law | Decoded locally to an 8 kHz WAV for the browser. | The demo then plays exactly the audio a phone line would carry. |
| D28 | Evon JSON mode | `response_format: json_object` with automatic removal if a server rejects it. | Fewer invalid-JSON retries on servers that support it. |
| D29 | Own map engine | `web/assets/map.js` instead of Leaflet from a CDN. | No external JavaScript; works offline (positions exact on a graticule when tiles are unreachable); testable without internet. |
| D30 | Remove fabricated numbers and government branding from the UI | v1 pages showed fixed values ("94.2% accuracy", "98.7% village resolution", "1,480+ calls"), invented state-level statistics, and "Jal Jeevan Mission / Department of Drinking Water and Sanitation" branding. All removed; every figure is computed from the database or a measured run and shows its n. | Hard rules 5 and 7; a judged prototype must not imply official status or unmeasured results. |
| D31 | Held-out text evaluation | Rules were improved on the regression set (8 fixes); a separate held-out set (15 cases) is never used for tuning and is reported separately (12/15 on 2026-11-13). | Tuning on the test set would make the number meaningless. |
| D32 | "Tanker did not come" = `no_water` | v1 deliberately returned no fault. | For a tanker-supplied village it means no water; the caller still confirms the read-back. |
| D33 | Gazetteer suffix stripping | Match both the stripped and the raw token. | "खडकवासला" ends in "-ला" and was stripped to "खडकवास" (failed every time). |
| D34 | Demo data in the app | Officer-only "Demo data" menu (demo mode) adds/removes 14 synthetic tickets covering every lifecycle path; all labelled. | A demo can start empty or full without the command line; real tickets are never touched. |
| D35 | Auto-listen on the phone | After the assistant speaks, the mic opens and closes on a 1.3 s pause (voice activity detection); tap, hold and typing remain. | Feels like a call instead of a walkie-talkie; the spec's push-to-talk is still there. |
| D36 | Starlette stays | FastAPI is still not installable in the build sandbox (D1). An OpenAPI 3.1 description is maintained by hand in `app/openapi.py`, rendered at `/docs`, and a test fails if a route is missing from it. | Same benefit as FastAPI's /docs without an untested dependency. |
