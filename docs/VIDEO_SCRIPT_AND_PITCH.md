# Demo video and post

Three pieces: the **recorded demo** (made from the running app, no sound), a **voiced take** you record
with a Gnani key so the judges hear Prisma and Timbre working, and the **post** that nominates the entry.

## 1. The recorded demo

| File | Length | Use |
|---|---|---|
| `jalawaaz_demo_2min.mp4` | 2 min 41 s | Submission form ("2–3 minute demo video") |
| `jalawaaz_demo_60s.mp4` | 57 s | LinkedIn/X post; the Demo Day Drop award is for a 60-second video |

Both were made on 14 November 2026 by driving the real app in a headless browser (the same steps as
`tests/e2e/test_five_act_demo.py`) and captioning each screen. 1920×1080, 30 fps, H.264, silent audio track.

What they show, in order: missed call and simulated callback; the AI disclosure; the caller's sentence and
the fields understood; the read-back; the ticket number; the red pin and the priority reason on the
dashboard; the engineer's acknowledge and "Report fix" sheet; the amber pin; the verification call and
"हो"; the green pin; a second complaint where the caller says "नाही" and the ticket reopens P2 → P1; the
false-closure rate at 50 %, n = 2; the dashboard with 14 labelled synthetic tickets; the evaluation page.

**What they do not show: Gnani running.** They were recorded without an API key, so the screen says
"Speech: off, type instead", "Voice: browser" and "Understanding: rules", and the caller's words are typed.
The challenge's eligibility check is genuine use of Gnani technology, so record the voiced take below and
put it in the submitted video.

## 2. The voiced take (about 20 minutes)

Goal: 40–70 seconds in which a person speaks Marathi to the phone page, Prisma's transcript appears, and
Timbre's voice answers out loud.

**Set up**
1. Create a new key at app.gnani.ai (the old one was in `.env.example` and must be revoked). Put it in
   `.env` as `GNANI_API_KEY=`.
2. `python -m scripts.doctor --online` must pass. Then `python -m scripts.warm_tts --yes` so the fixed
   prompts are cached (fewer credits, faster replies).
3. `run.bat`, then open `http://localhost:8000/phone` in Chrome or Edge and allow the microphone. The badges
   should now read "Speech: Prisma prisma-v3.0" and "Voice: Timbre streamed".
4. Set Windows sound output to speakers or headphones that the recorder can capture.

**Record** with the Xbox Game Bar (Win + Alt + R starts and stops; it records the browser window with its
sound) or OBS. Speak clearly, close to the microphone.

| Step | Do | Say |
|---|---|---|
| 1 | Pick मराठी, tap मिस्ड कॉल द्या, then answer the call | — |
| 2 | Let the greeting play (it says it is an AI) | — |
| 3 | Hold the talk button | "खेड शिवापूरमध्ये हातपंप तीन दिवस बंद आहे, चाळीस घरं" |
| 4 | Answer the follow-up question | "हो" or "नाही" |
| 5 | Let the read-back play, then confirm | "हो" |
| 6 | Let the ticket number play digit by digit | — |

Optional second clip: after "Report fix" on `/engineer`, the verification call rings; answer "हो".

**Put it together** in Clipchamp (free in Windows 11) or any editor: title card from the recorded demo
(0:00–0:06), then your voiced take, then the recorded demo from the dashboard onwards (0:48 to the
end). Keep the total between 2 and 3 minutes; trim acts 1–2 of the recorded demo if needed. If there is no
time to edit, submit the voiced take as its own video and link the recorded demo in the README.

## 3. The post

Rules from gnani.ai/internship (checked 14 November 2026): post the demo on LinkedIn, X or both; the post
must be **live before you submit**; explain what you built and which Gnani technology you used; **tag
Gnani AI** and use **both** hashtags, #GreatIndianAIInternshipChallenge and #GnaniAI; nominate the post in
the submission form. Shortlisting starts with an engagement check on nominated posts, so post early and
share it with your real network (bought likes, bots and engagement swaps are excluded).

Attach `jalawaaz_demo_60s.mp4` (or your edited cut). On LinkedIn, type "@Gnani" and pick Gnani's company
page from the list so it becomes a real tag.

**LinkedIn**

> A water complaint marked "fixed" should mean the water runs.
>
> When a handpump or tap complaint is closed, usually nobody asks the person who reported it whether the
> water came back. So I built Jal Awaaz (जल आवाज) for the Great Indian AI Internship Challenge:
>
> 1. Give a missed call. An AI assistant calls back in Marathi, Hindi or Hinglish and says it is an AI.
> 2. It asks one question at a time, reads the complaint back, and opens a ticket only after "हो".
> 3. The engineer reports a fix. That does not close the ticket.
> 4. The assistant calls the original caller again. "Yes" closes it. "No" reopens it, one priority level
>    higher.
>
> Built on @Gnani AI:
> • Prisma v3.0 hears the caller, with village names and the question just asked as context
> • Timbre v3.0 speaks, streamed so replies start quickly, ticket numbers read digit by digit
> • Evon v3.3 turns the words into complaint fields, with a rule-based fallback
>
> Priority, SLAs and closure are plain code, not model output. The district dashboard leads with one
> number: the false-closure rate, always shown with its n.
>
> Where it stands: a working prototype with the phone simulated in a browser. 318 automated tests. On a
> held-out text set, village, source and fault are all right in 12 of 15 calls. Speech accuracy on real
> village audio is not measured yet; that comes next, with a native-speaker review and a small consented
> pilot.
>
> Code and one-page pitch: [repository link]
>
> #GreatIndianAIInternshipChallenge #GnaniAI

**X** (278 characters)

> A water complaint marked "fixed" should mean the water runs. Jal Awaaz: missed call, AI callback in
> Marathi, Hindi or Hinglish, ticket, fix, then the AI asks the caller again. "No" reopens it. Built on
> @GnaniAi Prisma, Timbre and Evon. #GreatIndianAIInternshipChallenge #GnaniAI

## Words to avoid and what to say instead (from the spec)

| Avoid | Say |
|---|---|
| "Zero false closures", "eliminates ghost repairs" | "We measure false closures, with n" |
| "Understands any dialect / noisy rural speech" | "Prisma v3.0 with context hints; speech accuracy on real audio is not measured yet" |
| "Production-ready", "deployed", "national" | "Working prototype", with the exact number of real users (none yet) |
| Any statistic about rural water failures | Leave it out unless the source is checked and cited |
| Official-sounding names, government logos | "Independent prototype, not an official service" |
| "Real phone calls" | "Browser phone with a simulated callback; the speech pipeline is real" |
