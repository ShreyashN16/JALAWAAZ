# Configuration

Two places: `.env` (secrets, URLs, modes; copy from `.env.example`) and `data/config.json` (thresholds and
behaviour). Restart the server after changing either. `python -m scripts.doctor` checks both.

## `.env`

| Setting | Default | Meaning |
|---|---|---|
| `GNANI_API_KEY` | empty | Key from app.gnani.ai, sent as `X-API-Key-ID`. Empty = typed answers and browser voice. **Keep it secret; never put it in `.env.example`.** |
| `GNANI_STT_MODEL` | `prisma-v3.0` | `prisma-v2.5` if your key returns `INVALID_MODEL` for v3.0 |
| `GNANI_TTS_MODEL` | `timbre-v3.0` | or `timbre-v2.5`; voices must belong to the model |
| `TTS_VOICE_MR`, `TTS_VOICE_HI` | `Shivani` | voices for Marathi and Hindi/Hinglish (see GNANI_INTEGRATION.md) |
| `TTS_VOICE_HIEN` | `Poorvi` | Hinglish voice, used only with timbre-v2.5 (`hi-en`) |
| `TTS_FORMAT` | `mp3` | browser audio: `mp3` (small, streams), `wav`, `ogg` |
| `TTS_SAMPLE_RATE`, `TTS_BITRATE` | `24000`, `64k` | MP3 settings |
| `TTS_STREAMING` | `1` | Timbre SSE streaming (MP3 only); falls back to the file endpoint |
| `TTS_TELEPHONE_CONTAINER` | `mulaw` | what telephone mode requests (`mulaw` or `alaw`, 8 kHz) |
| `GNANI_CONCURRENCY` | `1` | simultaneous Gnani requests; raise only if your account allows it |
| `GNANI_TIMEOUT_SEC` | `45` | per request |
| `GNANI_STT_URL`, `GNANI_TTS_URL`, `GNANI_TTS_SSE_URL`, `GNANI_STT_LANGUAGES_URL` | Gnani endpoints | change only if Gnani moves them |
| `EVON_ENABLED` | `1` | `0` = rule-based extraction only |
| `EVON_BASE_URL` | `http://localhost:8001` | your vLLM/SGLang server |
| `EVON_SERVED_NAME` | `evon` | `--served-model-name` you used |
| `EVON_API_KEY` | empty | bearer token if your server needs one |
| `EVON_TIMEOUT_SEC` | `20` | |
| `EVON_JSON_MODE` | `1` | ask for `response_format=json_object` (dropped automatically if unsupported) |
| `APP_SALT` | `change-me` | salt for hashing device ids / phone numbers. **Changing it later breaks the link between old tickets and their callers.** |
| `APP_SECRET` | `change-me-too` | signs staff session cookies |
| `ENGINEER_PIN`, `OFFICER_PIN` | `2468`, `1357` | staff PINs. While both are unchanged and `DEMO_MODE=1`, the sign-in page shows them. |
| `DB_PATH` | `./jalawaaz.db` | SQLite file |
| `DEMO_MODE` | `1` | compressed time (seconds instead of hours); enables the demo-data menu |
| `DEMO_CALLBACK_DELAY_SEC` | `5` | missed call → callback |
| `DEMO_VERIFY_DELAY_SEC` | `8` | fix claimed → verification call |
| `DEMO_VERIFY_RETRY_SEC` | `30` | unanswered verification → next attempt |
| `DEMO_IGNORE_QUIET_HOURS` | `1` | demo only; real mode never calls 21:00–07:00 IST |
| `TELEPHONE_MODE` | `0` | default position of the phone page's 8 kHz switch |
| `SMS_PROVIDER` | `console` | logs SMS; no provider is wired in |
| `MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION` | OpenStreetMap | any XYZ tile server you are allowed to use |
| `MAX_UPLOAD_BYTES` | `2000000` | largest accepted recording |

## `data/config.json`

Every number here is a **prototype assumption** to review with a Jal Mitra or an engineer.

| Key | Default | Meaning |
|---|---|---|
| `priority.p1_households`, `p1_duration_days` | 100, 2 | P1 when at least this many households are without water for at least this many days |
| `priority.p2_duration_days`, `p2_households` | 3, 50 | P2 thresholds |
| `priority.repeat_window_days` | 30 | a second report on the same village and source within this window is P2 |
| `sla_hours` | P1 4, P2 24, P3 72 | time to act before priority rises one level |
| `calling.max_followups` | 3 | optional questions per call |
| `calling.max_total_questions` | 5 | after this, read back (or hand off if a required field is missing) |
| `calling.max_verify_attempts` | 3 | then `UNVERIFIED` |
| `calling.verify_delay_hours`, `verify_retry_hours` | 6, 3 | real mode timings |
| `calling.quiet_hours` | 21:00–07:00 | no verification calls (IST, `tz_offset_minutes` 330) |
| `calling.silence_seconds` | 6 | the phone ends a turn after this long without speech |
| `calling.max_utterance_seconds` | 25 | longest answer the phone records |
| `gazetteer.accept`, `confirm` | 88, 70 | village match scores: accept, ask to confirm, or ask again |
| `stt.first_turn_languages` | `mr-IN,hi-IN,en-IN` | Prisma language hint before the language is known |
| `stt.format` | `transcribe` | digits for numbers, Latin for English words |
| `stt.context.keyterms` / `topic` / `previous_text` | all `true` | Prisma v3.0 context hints (turn off one at a time to A/B) |
| `stt.topic` | call description | `{taluka}` and `{district}` are filled from the gazetteer |
| `stt.substitutions` | 2 rules | Prisma substitution map, max 10 rules |
| `tts.speed` | 0.95 | 0.85–1.15 |
| `tts.spell_numbers` | `true` | quantities spoken as words in Marathi/Hindi |
| `tts.audio_tags` | `true` | `<pauses>` on timbre-v3.0 |
| `privacy.transcript_retention_days` | 90 | transcripts erased after this |
| `privacy.session_ttl_minutes` | 15 | an idle call session expires |
| `rate_limit.per_minute` | 60 | public requests per IP per minute |

## `data/villages.csv`

`name, variants (| separated, Latin and Devanagari spellings), taluka, district, lat, lon, coord_source, coord_quality`.
Leave `lat`/`lon` empty rather than guessing; `coord_quality` is `cited` or `approximate`. The server
syncs this file into the database at start-up (existing village ids never change). Add spelling
variants as pilot users actually say them.
