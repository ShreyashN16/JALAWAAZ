# Submission guide

**Project**: Jal Awaaz (जल आवाज)
**Tagline**: A water complaint is closed only when the person who reported it says the water runs.
**Built with**: Gnani Prisma v3.0 (speech to text), Gnani Timbre v3.0 (text to speech, streamed), Evon v3.3
(self-hosted, with a rule-based fallback), Python, Starlette, SQLite, HTML/CSS/JavaScript.
**Status**: independent working prototype; simulated callbacks in a browser phone; no real-user pilot yet.

## Deadline and order of work

The challenge page (gnani.ai/internship, checked 14 November 2026) gives the deadline as
**15 November 2026, 6:00 pm IST**. It also says the programme terms on the registration page are final,
so check there if in doubt. Shortlisting starts with an engagement check on the nominated post, so the post
should go up as early as possible.

1. Revoke the Gnani key that was in the old `.env.example`; create a new one and put it only in `.env`.
2. Record the voiced take and build the 2–3 minute video (`docs/VIDEO_SCRIPT_AND_PITCH.md`).
3. Publish the repository (below) and upload the video.
4. Put the video link in `README.md` (replace `VIDEO_LINK`) and push again.
5. Publish the LinkedIn post (and X if you like): tag Gnani AI, both hashtags, video attached.
6. Fill in the submission form. Each person or team submits one entry.

## The submission form, field by field

| Field | What to enter |
|---|---|
| 1. Full name | Your name as registered |
| 2. Registered email | The email used on the "Register to Build" form (contest mail goes to the primary registrant) |
| 3. Teammate's registered email | Team of two: their registered email. Solo: "Not applicable (solo entry)" |
| 4. Higher education institution | Your college or university |
| 5. Project URL | The public GitHub repository. `PITCH.pdf` (one page) is in its root and linked at the top of the README |
| 6. Video demo link | YouTube (unlisted is fine) or Google Drive set to "Anyone with the link can view". 2–3 minutes |
| 7. LinkedIn post | The post's own link (⋯ → "Copy link to post"), not your profile |

Team entries: record who did what. Each member is interviewed separately. The pitch does not name people,
so add a "Team" line to `README.md` if you are two.

## Publishing the repository

Create an empty **public** repository on github.com (no README, no licence), then in the project folder:

```
git init
git add .
git status
```

Check that `.env`, `jalawaaz.db` and `tts_cache/` are **not** listed (`.gitignore` excludes them). Then:

```
git commit -m "Jal Awaaz 2.0.1"
git branch -M main
git remote add origin https://github.com/<your-user>/jalawaaz.git
git push -u origin main
```

If an older version was ever pushed with the key in `.env.example`, the key stays in that history:
revoking it at app.gnani.ai is what makes it safe.

## Award categories this entry fits

Ten awards of ₹50,000; an entry can win at most one. Closest fits: **Real Deal** (most useful real-world
problem), **Main Character** (regional or low-resource language: Marathi), **Mixed Vibes** (code-mixed:
Hinglish), **Solo Ninja** or **Two-Person Army**, and **Demo Day Drop** (best 60-second video). **Noise
Canceller** needs measured results on noisy telephone audio, which this entry does not have yet.

## Summary (about 100 words)

Jal Awaaz lets a villager report a broken handpump, tap, well or borewell by voice and decides that the
fault is fixed only when that same person says so. A missed call brings an AI callback in Marathi, Hindi
or Hinglish that discloses it is an AI, asks one question at a time, reads the complaint back and opens a
ticket only after "yes". Priority, SLAs and ticket state are deterministic code. When the engineer reports
a fix, the assistant calls the reporter again: "yes" verifies the ticket, "no" reopens it at higher
priority. The district dashboard leads with the false-closure rate, always shown with its n.

## Description (about 400 words)

**Problem.** A complaint system can mark a fault fixed without asking the person who has no water. People
who cannot read a portal or use an app also find it hard to report in the first place.

**What we built.** Four screens on one Python server. The villager phone (a browser page standing in for a
phone) gives a missed call and receives a simulated callback. Gnani Prisma v3.0 transcribes each answer,
using the pilot villages' names as keyterms, a description of the call as topic, and the question being
answered as previous_text. Evon v3.3 on our own OpenAI-compatible server, or a rule-based extractor when it
is unavailable, turns the words into fields; validators and guards in code drop anything not supported by
the transcript. A template reads the complaint back. Gnani Timbre speaks every reply, streamed as MP3 so
playback starts on the first chunk; numbers are spoken as words and ticket numbers digit by digit.

Priority rules, SLA escalation and the ticket state machine are plain Python, with a database trigger that
rejects any illegal state change and an audit trail for every change. The engineer queue shows the reason
for every priority. Reporting a fix queues a verification call to the original caller only; three
unanswered attempts leave the ticket unverified rather than fixed.

The district dashboard shows one pin per village on a map, the false-closure rate with its n, SLA breaches,
repeat failures, a 14-day trend and the full record of each ticket, with a public view that hides
individual records. The evaluation page shows only measured numbers.

**Honesty labels.** The phone call is simulated in the browser; SMS is logged, not sent; demo tickets are
labelled synthetic; villages without verified coordinates are not placed on the map.

## Evidence

| Claim | Evidence |
|---|---|
| End-to-end loop works | `tests/e2e/test_five_act_demo.py` drives it in a browser: report, fix, "yes" verifies, "no" reopens, dashboard shows the false-closure rate with n. The recorded demo video follows the same steps |
| Code decides, models do not | `app/core/priority.py`, `tickets.py`, the trigger in `app/db.py`; 34 hand-labelled priority tests |
| Gnani use is real | `api_calls` table and `/metrics` (status and latency per request, with request ids); `scripts/smoke.py`; the voiced take in the video |
| Language layer accuracy | held-out synthetic text: 12 of 15 calls fully right (rule-based extractor, never tuned on); regression set 43 of 43 (used while fixing, not a fair test). Results in `bench/results/text_eval.json` and on `/metrics` |
| Not yet measured | Prisma accuracy on recorded or noisy audio; Timbre pronunciation of village names; any real-user outcome |
| Tests | 317 unit/API tests and 1 browser test |

## Demo for evaluators

1. `run.bat doctor`, then `run.bat` (or `make run`). Open `http://localhost:8000`.
2. `/phone`: pick मराठी, tap the call button, answer, speak or type
   *"खेड शिवापूरमध्ये हातपंप 3 दिवस बंद आहे, 40 घरं"*, answer the question, hear the read-back, say *"हो"*.
3. `/dashboard` (officer PIN from `.env`, demo `1357`): the pin and the priority reason.
4. `/engineer` (engineer PIN, demo `2468`): Acknowledge, Report fix.
5. `/phone` rings again (time compressed): *"हो"* verifies; repeat with *"नाही"* to see the reopen.
6. `/metrics`: measured evaluation and live latency.

## FAQ

**How would a villager without internet use it?** Through a telephony provider: the same pipeline would
take 8 kHz call audio instead of the browser's (the telephone-mode switch already tests that path), and
the outbox rows would become real outbound calls. This prototype does not include a telephony provider.

**What about dialects and noise?** Prisma v3.0 is given context hints, and the gazetteer matches spelling
variants of village names. How well this works on real village speech is not measured yet; the benchmark
scripts are ready for recorded, consented clips.

**What is stored?** No audio. Phone numbers and device ids only as salted hashes. Transcripts are erased
after 90 days; fields and the audit trail remain. No Aadhaar, bank details or names are asked for.

**Was AI used to build it?** Yes, as a development tool (Claude). The product itself calls only Gnani
models and its own rules.
