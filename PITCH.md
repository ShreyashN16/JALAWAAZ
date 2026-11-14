# Jal Awaaz (जल आवाज): one-page pitch

**A water complaint is closed only when the person who reported it says the water runs.**

Voice-first fault reporting and fix verification for village water supply, in Marathi, Hindi and
Hinglish. Built on Gnani Prisma, Timbre and Evon. Independent student prototype for the Great Indian AI
Internship Challenge, not an official government service. Printable version: [PITCH.pdf](PITCH.pdf).

## How a complaint travels

1. **Missed call**, free for the caller, from any phone.
2. **AI callback**: it says it is an AI, then asks one question at a time.
3. **Read-back, then "हो"**: a ticket exists only after the caller confirms.
4. **Engineer reports a fix**: this never closes the ticket.
5. **Second call to the original caller**: "yes" verifies and closes; "no" reopens it one priority higher.

## The problem

When a handpump or tap complaint is marked fixed, usually nobody asks the person who reported it whether
the water came back. Many people who depend on a village source cannot easily use an app or a web portal,
but almost anyone can give a missed call and answer a question in their own language.

## The number it is built to measure

**False-closure rate** = tickets reopened at least once ÷ tickets whose fix the caller answered, always
shown with its n. It is the district dashboard's headline figure. We claim no value for it yet: no pilot
with real callers has been run.

## Gnani models and what each one does

| Model | Role | How Jal Awaaz uses it |
|---|---|---|
| Prisma v3.0 | hears | Speech to text. Each turn sends village names as key terms, the call's topic, and the question just asked as context, so short answers such as "40" or "हो" are heard in context. A telephone mode tests 8 kHz phone-line audio. |
| Timbre v3.0 | speaks | Text to speech, streamed so the voice starts on the first chunk. Numbers spoken as words, ticket numbers digit by digit; mu-law audio for phone lines. |
| Evon v3.3 | extracts | Turns the transcript into fields (village, source, fault, days, households) on a self-hosted server. A rule-based extractor takes over when it is not running. |

## Code decides; models only hear, extract and speak

- **Priority** from fixed rules, each with a stored reason: a contaminated drinking source, 100+ households
  without water for 2+ days, a repeat failure within 30 days, a reopened ticket.
- **SLAs** of 4, 24 and 72 hours by priority, with automatic escalation when one is missed.
- **A database trigger** rejects any illegal state change, so a claimed fix cannot become "verified"
  without the caller.
- **Verification calls**: at most 3 attempts, never between 9 pm and 7 am.

## Measured so far (13 November 2026)

- **318** automated tests, including a browser test of the full report → fix → verify and reopen demo.
- **12 of 15** held-out test calls (text) had village, source and fault all right, using the rule-based
  extractor.
- Speech accuracy on recorded village audio: **not measured yet**.

## Privacy and safety

AI disclosed in the first sentence of every call. Read-back before every ticket. No audio stored. Phone and
device ids kept only as salted hashes; transcripts deleted after 90 days. One fixed health line and no
diagnosis. The public dashboard view shows totals only.

## Next

Native-speaker review of every sentence; a recorded speech benchmark including noisy 8 kHz audio; a small
consented pilot with its n reported; a telephony provider for real missed calls.

---
In the demo the phone calls are simulated in a browser; the speech, language and ticket pipeline is real.
SMS messages are logged, not sent. No complaint reaches any government system. Built with AI assistance
during development; the product itself calls only Gnani models.
