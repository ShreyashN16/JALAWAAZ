# Recording the demo video

The demo videos were made by driving the real app in a browser (the same steps as
`tests/e2e/test_five_act_demo.py`), taking a screenshot at each moment, adding a caption band and
encoding the stills with crossfades. Nothing on screen is mocked up. There is no sound: the caller's
words are typed, because the run uses no Gnani key.

Needs Playwright (`requirements-dev.txt`) and ffmpeg on PATH.

**1. Start a fresh demo server** (empty database, short delays, no key), from the project root.
PowerShell:

```
$env:DB_PATH="$env:TEMP\ja_video.db"; $env:GNANI_API_KEY=""; $env:EVON_ENABLED="0"; $env:DEMO_MODE="1"
$env:DEMO_CALLBACK_DELAY_SEC="3"; $env:DEMO_VERIFY_DELAY_SEC="3"; $env:DEMO_IGNORE_QUIET_HOURS="1"
python -m uvicorn app.main:app --port 8030
```

Delete that database file before each recording: the captions expect the first two tickets.

**2. In a second terminal**, from `scripts/demo_video/`:

```
python capture.py                 # drives the app, writes raw/
python compose.py frames full     # captioned 1920x1080 stills, frames/full/
python compose.py render full     # out/jalawaaz_demo_2min.mp4
python compose.py frames short
python compose.py render short    # out/jalawaaz_demo_60s.mp4
```

Set `JA_CHROME` to a Chrome or Edge executable to use an installed browser, and `JA_BASE` if the server
is not on port 8030. Captions and timings are the `FULL` and `SHORT` lists in `compose.py`. Look at a few
files in `frames/` before rendering: the captions name the villages and the priority change seen in this
run.
