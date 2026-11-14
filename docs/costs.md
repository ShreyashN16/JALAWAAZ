# Gnani credits: measured, not assumed

**Status: not yet measured.** Gnani's docs do not state the credit unit, so this file stays empty until you
measure it. Do not quote any cost per report before then.

## How to measure

1. Note your balance at app.gnani.ai.
2. Run `python -m scripts.smoke`. It makes a known set of requests:
   1 key check (metadata), 4 Timbre requests (file, stream, mu-law, ticket digits; about 15–25 words each),
   2 Prisma requests on a ~5 s clip.
3. Note the balance again.
4. To separate Timbre from Prisma: delete the `tts_cache` folder, run `python -m scripts.warm_tts --yes`
   (Timbre only; it prints how many prompts it synthesised) and note the balance before and after.
5. Fill in:

| Call | Text / clip | Requests | Credits before | Credits after | Credits per request |
|---|---|---|---|---|---|
| Timbre v3.0 (file or stream) | ~20 words Marathi | | | | |
| Prisma v3.0 | ~5 s | | | | |
| Key check (languages) | none | 1 | | | |

## What a report costs (formula)

A typical report call is 3–5 Prisma turns and 4–6 Timbre replies. The greeting and the fixed questions are
cached after their first use (`scripts/warm_tts.py` pre-records them), so only read-backs and the ticket
sentence cost Timbre credits. A verification call is 1–2 Prisma turns and 1–2 uncached Timbre replies.

Cost per report = Prisma turns × Prisma cost + uncached Timbre replies × Timbre cost.
`/metrics` shows the real counts per service from the call log. Evon is self-hosted: its cost is your GPU
time, not Gnani credits.

Silence is detected locally and never sent to Prisma. On HTTP 402 the app stops every paid request and
switches to typed input and on-screen text.
