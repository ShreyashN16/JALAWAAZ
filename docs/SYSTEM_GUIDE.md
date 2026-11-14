# Jal Awaaz system guide

A plain-language tour of the whole system. Engineers wanting detail should read
[ARCHITECTURE.md](ARCHITECTURE.md); people using the screens should read [USER_GUIDE.md](USER_GUIDE.md).

## The problem it addresses

Water complaints can be marked "fixed" without the water coming back, and people who cannot use a text
portal or an app have no easy way to report or to say that a fix did not work. Jal Awaaz tests one idea:
**let the person who reported the fault decide whether it is fixed**, by voice, in their language.

## The loop

1. **Missed call.** Free for the caller. (Simulated in this prototype: a browser page plays the phone.)
2. **AI callback.** The assistant says it is an AI and asks what is wrong, one question at a time, in
   Marathi, Hindi or Hinglish. Gnani Prisma turns speech into text; Evon (on your own server) or a
   rule-based extractor turns the text into fields: village, water source, fault, days, households,
   drinking water, symptoms.
3. **Read-back.** A fixed template, not a model sentence, repeats the details. A ticket is created only
   when the caller says yes. The ticket number is spoken twice, digit by digit, by Gnani Timbre.
4. **Priority.** Rules in code, with the reason stored and shown: P1 for drinking water with symptoms or
   contamination, or ≥100 households without water for ≥2 days; P2 for ≥3 days, ≥50 households or a repeat
   report within 30 days; P3 otherwise (all thresholds in `data/config.json`).
5. **Engineer.** Sees the ticket with its reason and SLA (P1 4 h, P2 24 h, P3 72 h). Acknowledges, repairs,
   reports the fix. A missed SLA raises the priority one level.
6. **Verification call.** After a fix is reported, the assistant calls the original caller (only that
   device can answer it; never 21:00–07:00 in real mode; at most 3 attempts).
   - "Yes": **VERIFIED**, closed.
   - "No": **REOPENED**, back to the engineer one priority level higher, and the false-closure rate moves.
   - No answer after 3 attempts: **UNVERIFIED**, not counted as fixed.

## The headline number

**False-closure rate** = tickets reopened at least once ÷ tickets whose fix the caller answered (yes or
no). It is always shown with its n, because a rate from 3 answers means little.

## What runs where

| Piece | Runs | Notes |
|---|---|---|
| Server | your laptop (Python, Starlette, SQLite) | one process, scheduler inside |
| Speech to text | Gnani Prisma v3.0 (cloud) | needs `GNANI_API_KEY` |
| Voice | Gnani Timbre v3.0 (cloud), streamed | needs `GNANI_API_KEY` |
| Understanding | Evon v3.3 on a GPU server you run, or built-in rules | the UI says which ran |
| Phone | a browser page (simulated calls) | a real telephony provider can reuse the same pipeline |
| SMS | written to a log | no SMS provider is wired in |

## What it deliberately does not do

- It does not let a model set priority or close a ticket.
- It does not store the caller's voice, name, Aadhaar or bank details.
- It does not give health advice beyond one fixed informational line.
- It does not send anything to a government system.
- It does not show numbers it did not measure.
