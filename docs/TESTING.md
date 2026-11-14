# Testing and evaluation

## Automated tests

```bash
python -m pytest -q --ignore=tests/e2e     # 317 tests, about 5 seconds, no network, no credits
python -m pytest -q tests/e2e              # browser test of the five-act demo (needs playwright + Chromium)
```

No test calls a real Gnani API: HTTP is mocked with `httpx.MockTransport` and providers are replaced with
fakes. Each test gets its own temporary database.

| File | What it proves |
|---|---|
| `test_foundation.py` | schema, the illegal-transition trigger, priority CHECK, salted hashing, PIN roles, rate limit, ffmpeg conversion and the 8 kHz telephone path |
| `test_gnani_adapters.py` | Prisma/Timbre/Evon request shapes; 401 not retried; 402 stops all further paid calls; 429 and 500 retried; three 503s fail; error envelopes; voice mismatch; static-only TTS cache; Evon `<think>` stripping |
| `test_gnani_current_api.py` | the 2026-11 API features: `topic`, `previous_text`, `keyterms`, substitution map and request id sent; context limits and forbidden tokens; v2.5 single language and valid `bias_list`; 422 list and 504 shapes; 504 retried; `truncated`; SSE chunks in order; SSE failure and SSE error event fall back to REST; telephone mode requests mu-law and returns playable WAV; mu-law decoder values; `<pauses>` only on v3.0; voice catalogue both ways; numbers spelled and ticket digits one by one; `Say` survives concatenation; Evon JSON mode dropped when rejected; key check |
| `test_numbers.py` | 102 curated phrases (Marathi, Hindi, Hinglish, English, fractions, hundreds, ranges) and 1–100 round trips |
| `test_language.py` | gazetteer accept / confirm / reject and transcript scan, yes/no including verification phrasing, validators, Evon JSON handling, fallback, hallucinated-number guard |
| `test_priority.py` | 34 hand-labelled priority cases including reopened and repeat paths |
| `test_tickets_scheduler.py` | a fix claim never closes; yes → VERIFIED; no → REOPENED → ACKED at higher priority; false-closure maths; three unanswered calls → UNVERIFIED; quiet hours; SLA escalation; transcript retention |
| `test_statemachine.py` | scripted calls: one-shot Marathi report, one question per turn in Hindi, correction, no ticket without yes, unknown village, silence, safety line, verification yes/no/unclear, only the original device can verify |
| `test_api.py` | the five-act demo over HTTP, auth and CSRF, validation errors, an audio turn through ffmpeg with Prisma context and language switching, typing offered without a key |
| `test_api_v2.py` | streamed speech endpoint (stream, cache, memory replay, 503 on failure, 404), browser-voice fallback, my-tickets isolation, village sources, insights and SLA fields, activity and SMS, CSV export without caller data, text evaluation, system warnings, demo seed/clear labelled and real tickets untouched, every route documented, all pages load, 404s, **an old v1 database migrates in place** |
| `test_bench.py` | WER normalisation and maths |
| `e2e/test_five_act_demo.py` | headless Chromium: missed call → ringing → answer → AI disclosure → report → read-back → ticket; engineer acknowledges and reports a fix; phone rings; "ho" verifies; second ticket "nahi" reopens; dashboard shows 50% false closure with "1 reopened of 2"; no page errors |

## Text evaluation (no credits)

```bash
python -m bench.text_eval        # or "Run now" on /metrics
```

Runs the language layer (number normaliser, extraction, validators, village matching) on synthetic text
cases and reports accuracy per field with n, the rule-only baseline, per language, and every failing case.

- **Held-out set** (`bench/text_cases_holdout.csv`, 15 cases): written once and never used to change the
  rules. On 2026-11-13 with the rule-based extractor: village, source and fault all right in 12 of 15.
- **Regression set** (`bench/text_cases.csv` plus `bench/clips/gold.csv`, 42 cases at first): the first run found 8
  failures (a suffix-stripping bug on "खडकवासला" and missing phrasings such as "आला नाही", "फुटली",
  "पानी कम", "कुएँ"). The rules were fixed and the set passed 42/42. On 2026-11-14 recording the demo found
  one more ("पाणी आलं नाही", the spoken form of "did not come"); it was added as case mr-13 with the fix,
  so the set is now 43 cases and passes 43/43. Because it was used for tuning it is a regression guard, not
  a fair test. The held-out result did not change (12 of 15).

Keep the held-out set honest: when you add cases to it, record the result before changing any rule, then
move those cases to the regression set and write a new held-out batch.

## Audio benchmark (spends credits)

```bash
# 1. put consented or synthetic clips in bench/clips/ and list them in bench/clips/gold.csv
python -m bench.make_noisy        # clean, 10 dB and 5 dB noise, each also through an 8 kHz mu-law line
python -m bench.run_bench         # Prisma on every derived clip (cached, never paid twice), then the pipeline
python -m bench.run_bench --format verbatim     # ablation: numbers as words + our normaliser
python -m bench.run_bench --no-keyterms         # ablation: without keyterms
```

Results go to `bench/results/latest.json` (shown on `/metrics`) and `latest.md`, with real and synthetic
clips reported separately and failure rows listed. Synthetic clips can be produced with Timbre
(`scripts/smoke.py` writes some to `samples/`); label them `synthetic` in gold.csv.

## Live check against Gnani

```bash
python -m scripts.smoke           # ~8 requests
```

Checks the key, Timbre (file, SSE stream with first-audio time, telephone mu-law, ticket digits), and Prisma
on Timbre's own audio with and without context hints, plus Evon if enabled. Writes audio to `samples/`.

## Before any pilot: native-speaker review (not done yet)

- [ ] Every sentence in `app/core/templates.py` (Marathi, Hindi, Hinglish), listened to through Timbre
- [ ] Number words in `app/nlp/numbers.py` / `app/nlp/spoken.py` (hundreds and thousands phrasing)
- [ ] Yes/no word lists in `app/nlp/yesno.py`
- [ ] Rule keywords in `app/nlp/extract.py`
- [ ] Phone-page strings in `web/assets/phone.js` (UI object)
- [ ] The safety line against official guidance
- [ ] Timbre pronunciation of every village name in `data/villages.csv`
- [ ] Voice choice (`python -m scripts.smoke --models`)

## Manual checks

- Phone in a real noisy place, through the tunnel: mic opens after the reply, closes on a pause.
- Telephone mode switch on: same report still works, reply sounds like a phone line.
- Dashboard public view on a second screen shows no individual record.
- Old database: copy a v1 `jalawaaz.db`, start the server, check tickets are still there.
