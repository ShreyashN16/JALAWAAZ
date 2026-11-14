# Runbook: set up, run the demo, fix problems

## 1. One-time setup (Windows, matching `D:\jalawaaz`)

```bat
cd D:\jalawaaz\jalawaaz
python -m venv ..\.venv                 REM skip if ..\.venv already exists
..\.venv\Scripts\activate
run.bat install                         REM pip install -r requirements-dev.txt
copy .env.example .env                  REM skip if .env exists; never copy the key into .env.example
notepad .env                            REM GNANI_API_KEY, APP_SALT, APP_SECRET, PINs
run.bat doctor                          REM fix every FAIL it prints
```

Optional, for the browser test: `python -m playwright install chromium`.

`APP_SALT` and `APP_SECRET`: any long random strings, e.g. `python -c "import secrets;print(secrets.token_urlsafe(32))"`.
Set the salt once; changing it later disconnects old tickets from their callers' devices.

## 2. Before each demo (10 minutes)

- [ ] `python -m scripts.doctor --online`: every check passes and Gnani accepts the key.
- [ ] `run.bat warm`: pre-records the fixed prompts so they play instantly (spends credits once per voice/format).
- [ ] `run.bat` to start the server. Open `http://localhost:8000` and check the "What is real" table.
- [ ] Dashboard: decide whether to show synthetic demo tickets (switch at the top) or start empty (Demo data → Remove).
- [ ] Phone: `run.bat tunnel`, open the `https://…trycloudflare.com/phone` address on the phone, allow the microphone.
- [ ] Laptop: sign in as officer on `/dashboard` in one window and as engineer on `/engineer` in another (two browser profiles, or one private window).
- [ ] Turn the phone's volume up and silence other notifications.

## 3. The five acts (script)

| Act | Where | Do | Say on camera |
|---|---|---|---|
| 1 | Phone | Pick मराठी, tap the call button | "A missed call is free. The callback is simulated in this browser." |
| 2 | Phone | Answer. After the greeting, speak; listen to the read-back; say "ho" | "It says it is an AI first, and reads everything back before opening a ticket." |
| 3 | Laptop | Dashboard: point at the new pin and the reason string | "Priority is set by rules in code, not by the model. Here is the reason." |
| 4 | Laptop | Engineer: Acknowledge, Report fix | "Reporting a fix does not close it." |
| 5 | Phone | It rings again. Answer "ho"; later run again and answer "nahi" | "Only the caller can close it. A 'no' reopens it at higher priority, and the false-closure rate moves." |

Optional sixth act: `/metrics` shows the measured evaluation with n and the live Gnani latency.

Talking tips for the phone: speak after the assistant finishes (the mic opens by itself and closes when you
pause); or tap the big button to start and stop; or hold it while speaking. The हो / नाही buttons and the
keyboard button are there for noisy rooms.

## 4. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Phone shows "Microphone is off" | Page not on HTTPS, or permission denied | Use the tunnel's https address; allow the mic in the browser's site settings |
| Replies are text only, "browser voice" | No `GNANI_API_KEY`, or credits exhausted (402) | Fill `.env` and restart; `/metrics` shows 402 errors |
| "Speech recognition failed (401 …)" | Key wrong or expired | Create a new key at app.gnani.ai; `python -m scripts.doctor --online` |
| "… (403 …)" for `prisma-v3.0` | Key not enabled for v3.0 | Set `GNANI_STT_MODEL=prisma-v2.5` or ask Gnani to enable v3.0 |
| Timbre 400 mentioning a voice | Voice from the other model | `run.bat doctor` names the mismatch; pick a voice for your model |
| Reply audio starts late | Streaming off or falling back | Check `TTS_STREAMING=1`, `TTS_FORMAT=mp3`; `/metrics` shows "Timbre voice (streamed)" first-audio time |
| "429 rate limit" notices | Two requests at once on a one-at-a-time account | Keep `GNANI_CONCURRENCY=1`; don't run the benchmark during a demo |
| Callback never rings | Phone page has a different device id than the one that gave the missed call, or the server restarted | Use the same browser tab; reload `/phone` and tap the call button again |
| Verification call never rings | Ticket is not `FIX_CLAIMED`, quiet hours in real mode, or it was answered already | Engineer tab shows the ticket under "Awaiting caller" with the next attempt time |
| Map background is grey with a dashed notice | No internet for map tiles | Positions are still exact; the notice says so. Connect to the internet for street tiles |
| A village has no pin | No verified coordinates in `data/villages.csv` | Listed under the map as "Not on the map". Add coordinates with a source |
| "ffmpeg was not found" | ffmpeg missing | `pip install imageio-ffmpeg` (bundled), or install ffmpeg on PATH |
| Evon "not reachable" | Your vLLM server is down or `EVON_BASE_URL` is wrong | Start it, or set `EVON_ENABLED=0`; the UI then says "rules" |
| Sign-in page shows no demo PINs | You changed the PINs (good) | Use your own PINs from `.env` |
| `database is locked` | Two servers on the same `DB_PATH` | Stop the other server |

## 5. Resetting

- Remove synthetic tickets: Dashboard → Demo data → Remove (or `run.bat unseed`).
- Start from an empty database: stop the server, rename `jalawaaz.db`, start again (villages are re-loaded).
- Clear cached prompts after changing voice or model: delete the `tts_cache` folder, then `run.bat warm`.
