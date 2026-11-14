# Changelog

## 2.0.1 (2026-11-14)

Submission kit for the Great Indian AI Internship Challenge, and three fixes found while recording the demo.

- **`PITCH.pdf`** (one A4 page) and **`PITCH.md`** in the repository root, linked at the top of the README.
  Source `docs/pitch/pitch.html`; rebuild with `python -m scripts.make_pitch`, which fails if the pitch no
  longer fits on one page. Replaces `docs/ONE_PAGE_PITCH.md`.
- **Demo videos** (2 min 41 s and 57 s, delivered separately, not in the repository) recorded from the
  running app. `docs/VIDEO_SCRIPT_AND_PITCH.md` now describes them, says plainly that they were recorded
  without a Gnani key, and gives a 20-minute plan for a voiced take with Prisma and Timbre, plus the post
  text for LinkedIn and X.
- `docs/HACKATHON_SUBMISSION_GUIDE.md`: the deadline (15 November 2026, 6:00 pm IST), the form field by
  field, publishing to GitHub without the `.env`, and which award categories fit.
- Fix: "पाणी आलं नाही" (and "आलेलं नाही") was not recognised as "no water", so the assistant repeated the
  fault question. Added with regression case mr-13 (regression set 43/43; held-out unchanged at 12 of 15).
- Fix: tabular figures applied to the whole page widened hyphens in some fonts ("Voice - first"); now only
  tables, times and figures use them.
- Fix: the phone's status-bar clock showed "--:--" for the first second.
- `bench/results/text_eval.json` is now committed, so the evaluation page shows the measured result on a
  fresh clone.

## 2.0.0 (2026-11-13)

### Upgrading from 1.0
1. Keep your `.env`, `jalawaaz.db` and `tts_cache/`; copy the new files over the old ones.
2. Delete files that no longer exist in 2.0: `web/assets/common.js`, `web/assets/style.css`,
   `web/assets/india_map.png`, `docs/architecture.md`, `docs/api.md`, `docs/testing.md`
   (replaced by `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/TESTING.md`).
3. `pip install -r requirements.txt` (no new required packages; `requirements-dev.txt` adds Playwright for the browser test).
4. Start the server once: the database gains its new columns and the gazetteer its coordinates automatically.
5. Optional `.env` additions are listed in `.env.example` (all have defaults). If your `.env` has
   `TTS_TELEPHONE_CONTAINER=wav`, change it to `mulaw` to hear the phone-line audio in telephone mode.
6. `python -m scripts.doctor --online`, then `python -m scripts.warm_tts`.

### Speech (Gnani APIs re-checked on 2026-11-13)
- **Prisma context hints** on every turn: village names and water words as `keyterms`, a call `topic`, and
  the assistant's last question as `previous_text` (short answers such as "40" or "ho"). Each can be turned
  off in `data/config.json`.
- Prisma **substitution map** ("hand pump" → "handpump", "bore well" → "borewell"), `X-API-Request-ID` on
  every request (stored in the call log), 422 and 504 error shapes understood, 504 retried, `truncated`
  reported. Prisma v2.5 fallback now sends a valid `bias_list` with `bias_score`.
- **Streamed replies**: Timbre SSE, MP3 at 64 kbit/s. The turn returns text at once; the voice starts on the
  first chunk instead of after the whole file. Automatic REST fallback.
- **Numbers spoken as words** in Marathi and Hindi; ticket numbers read one digit at a time; `<pauses>`
  before the read-back question and the ticket number on timbre-v3.0; speed 0.95.
- **Telephone mode** asks Timbre for G.711 mu-law (8 kHz) and plays it back as a phone line would sound.
- Full voice catalogues for timbre-v3.0 (13) and v2.5 (42); a voice/model mismatch is caught before it costs
  a request.
- Evon: JSON mode (`response_format`), dropped automatically when a server rejects it.
- `scripts/smoke.py` rewritten: no recordings needed (Timbre speaks, Prisma transcribes it with and without
  context), measures time to first audio. New `scripts/warm_tts.py` and `scripts/doctor.py`.

### Interface (rebuilt)
- New design system (`web/assets/app.css`, `app.js`): neel, chuna, kumkum, haldi palette; Bahnschrift and
  Nirmala UI; no external fonts or scripts.
- **Overview page** with the live report → fix → verification loop and a "what is real" table read from
  the server.
- **Villager phone**: Marathi/Hindi/Hinglish screens, ringing callback with ringtone, call screen with
  ripple, auto-listen with voice-activity detection, tap / hold / type, हो-नाही buttons, replay, result
  screen with the ticket number, "my complaints" status, and a "behind the call" rail for demo viewers.
- **District dashboard**: figure strip led by the false-closure rate with n, map with one pin per village
  (state colour, ripple for P1/reopened, ring for repeat failures, approximate positions marked), filterable
  queue, ticket drawer with audit timeline, verification attempts and SMS, 14-day trend, fault and source
  mix, SLA breaches, activity feed, SMS log, public view, CSV export, demo data menu.
- **Engineer queue**: phone-first job cards, SLA countdown, reason for the priority, confirmation sheet that
  explains a fix report does not close the ticket, note chips, directions, reopen alerts.
- **Evaluation page**: only measured numbers with n; text evaluation (held-out and regression), audio
  benchmark when run, live Gnani latency including time to first audio, call outcomes, system status.
- **API reference** at `/docs`, 404 page, mobile menu, WCAG AA contrast, reduced-motion support.
- Own map engine (`map.js`): OpenStreetMap tiles when online, exact positions on an offline basemap when not.

### Removed
- Fabricated figures from v1 pages ("94.2% dialect word accuracy", "98.7% village resolution", "1.4 s",
  "100% zero false closures", "1,480+ missed calls", invented state-level statistics on an India map).
- Government branding ("Jal Jeevan Mission · Department of Drinking Water and Sanitation", "Government AI
  Water Helpline") and the clip-art India map.
- Wrong demo PINs on the sign-in page (4400/2200 did not match `.env`).
- A real Gnani key that was present in `.env.example`. **Revoke it at app.gnani.ai if that file was shared.**

### Backend
- New endpoints: `/api/speech/{id}`, `/api/my-tickets`, `/api/villages`, `/api/map-config`, `/api/activity`,
  `/api/export/tickets.csv`, `/api/bench/run-text`, `/api/system`, `/api/system/check-gnani`,
  `/api/demo/seed`, `/api/demo/clear`, `/api/openapi.json`. Tickets carry `sla_due_at` and `sla_overdue`;
  metrics carry 14-day series, fault/source/village breakdowns and loop counts.
- Database migrates in place (new columns added, no data dropped); the gazetteer syncs on start-up without
  changing village ids.
- Gazetteer: six of nine villages located with cited or approximate sources; Khadakwasla added.
- Language layer fixes found by the text evaluation: names ending in a suffix-like syllable (खडकवासला),
  "आला नाही / नहीं आया" (no water), "फुटली / फट गया / burst" (leakage), "पानी कम / पाणी कमी" (low
  pressure), "कुएँ" (well). "Tanker did not come" now means no water.

### Evaluation (measured 2026-11-13, rule-based extractor)
- Held-out text set: village, source and fault all right in **12 of 15**. Misses: "पाणीच नाही",
  "पानी बह रहा है", "pipeline toot gayi". Left unfixed on purpose so the set stays held out.
- Regression set: 42 of 42 (used while fixing the rules; not a fair test).
- Speech accuracy on recorded audio: not measured yet.

### Tests
- 317 unit/API tests (was 282) and a browser test of the full five-act demo (`tests/e2e`).

## 1.0.0 (2026-11-02)
First prototype: Prisma/Timbre/Evon adapters, number normaliser, gazetteer, extraction with fallback,
state machine, priority engine, ticket lifecycle with database guard, scheduler, phone/engineer/dashboard
pages, benchmark scaffolding, 282 tests.
