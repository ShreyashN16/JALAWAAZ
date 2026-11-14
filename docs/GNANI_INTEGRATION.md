# Gnani integration: Prisma, Timbre, Evon

Shapes re-checked against docs.gnani.ai on **2026-11-13** (index: `https://docs.gnani.ai/llms.txt`).
If a call fails, re-check the live docs before changing code; the adapters log every request with its
own `X-API-Request-ID`, which you can quote to Gnani support.

## What changed since the original spec, and what v2 does about it

| Change in the Gnani docs | Effect in Jal Awaaz v2 |
|---|---|
| Prisma v3.0 accepts **context hints**: `keyterms` (200 terms), `topic` (1,600 chars), `previous_text` (last 600 chars), `speaker_names` | Every turn sends village names and water words as `keyterms`, a short description of the call as `topic`, and **the question the caller is answering** as `previous_text`. That last one matters most: a bare "40" or "ho" is easier to hear when the model knows the question. Each hint can be turned off in `data/config.json` for A/B testing. |
| `enable_substitution` + `substitution_map` (10 rules) | Two safe rules normalise "hand pump" → "handpump" and "bore well" → "borewell". Configurable. |
| Missing `language_code` returns **422** `{"detail": [...]}`; v3.0 can return **504** `{"error", "code": "UPSTREAM_TIMEOUT"}`; responses can carry `truncated` | `client.explain()` understands both shapes; 504 is retried; a truncated transcript shows a notice. |
| `X-API-Request-ID` header is echoed as `request_id` | Sent on every request (`ja-…`) and stored in `api_calls`. |
| v2.5 `bias_list`: single letter-only words, max 100, needs a positive `bias_score`; ignored on v3.0 when `keyterms` exist | The v2.5 path now filters to valid words and sends `bias_score=1.0` (v1 sent invalid lists that Gnani silently skipped). |
| Timbre containers `mp3`, `ogg`, `raw`, `mulaw`, `alaw`; sample rates 8–48 kHz; `bitrate` for MP3 | The browser phone gets **MP3 at 64 kbit/s, 24 kHz**: about a quarter of the size of 16-bit WAV, faster over a tunnel to a phone. |
| **SSE streaming** endpoint `POST /api/v1/tts/sse` with `start` / `chunk` / `complete` events | Replies stream: the phone starts playing after the first chunk instead of waiting for the whole file (v1 measured about 3.2 s per reply). Any failure before the first byte falls back to the REST endpoint automatically. |
| TTS reference: "write numbers, dates and currency as spoken words"; runs of 4, 6, 10, 12, 16 digits are read digit by digit, others as quantities | Quantities are written as words in Marathi or Hindi (`app/nlp/spoken.py`: 40 → चाळीस / चालीस). Ticket numbers are spoken one digit word at a time with commas (44712 → चार, चार, सात, एक, दोन), so the reading never depends on the length rule. Captions still show digits. |
| Timbre v3.0 **audio tags** (`<pauses>` etc.); v2.5 strips them | A pause marker in templates becomes `<pauses>` before the read-back question and before the ticket number on v3.0, and a comma on v2.5. |
| `speed` 0.85–1.15 | `tts.speed` in config, default 0.95 (slightly slower for clarity on phone lines; review with listeners). |
| Full voice catalogues (v3.0: 13 voices, all languages; v2.5: 42 voices with one preferred language) | `app/gnani/catalog.py` validates the configured voices against the model **before** a request is spent (Gnani returns 400 on a mismatch). |
| `GET /stt/v3/languages` returns supported languages and live audio limits | "Check Gnani key" on `/metrics` and `scripts/doctor.py --online` use it to validate the key without sending audio. |

## Prisma (speech to text)

`POST https://api.vachana.ai/stt/v3`, multipart, header `X-API-Key-ID`.

| Field | Value we send | Why |
|---|---|---|
| `audio_file` | 16 kHz mono WAV from ffmpeg | Phone browsers record webm/mp4, which Prisma does not accept |
| `model` | `prisma-v3.0` (omitted for v2.5) | opt-in model with code-mixing and context |
| `language_code` | first turn `mr-IN,hi-IN,en-IN`; after that only the detected language (`hi-IN,en-IN` for Hinglish) | hints, not locks; a single code settles Hindi/Marathi confusion on short answers |
| `format` | `transcribe` (always explicit) | English words stay Latin, numbers become digits |
| `keyterms` | water words + every village name and spelling variant (≤200, JSON) | village names are rare words |
| `topic` | from `stt.topic` in config, with taluka and district filled in | domain context |
| `previous_text` | the assistant's last question | short answers ("40", "ho") |
| `enable_substitution`, `substitution_map` | from `stt.substitutions` | spelling normalisation |

Silence (under 0.3 s or very quiet) is detected locally and never sent, so it costs nothing.
The phone stops recording at 25 s, and the server refuses anything over 30 s (Prisma's REST limit).

## Timbre (text to speech)

REST `POST https://api.vachana.ai/api/v1/tts/inference`; streaming `POST https://api.vachana.ai/api/v1/tts/sse`.

```json
{"text": "…", "model": "timbre-v3.0", "voice": "Shivani", "language": "mr-IN", "speed": 0.95,
 "audio_config": {"container": "mp3", "sample_rate": 24000, "num_channels": 1, "bitrate": "64k"}}
```

| Situation | Request | What the phone plays |
|---|---|---|
| Normal browser phone | MP3 over SSE, REST fallback | MP3, starts on the first chunk |
| Telephone mode switch on | `{"container": "mulaw"}` (8 kHz G.711, exactly what a phone line carries) | decoded locally to an 8 kHz WAV, so you hear the phone-line quality |
| Fixed prompts (greeting, questions) | REST, cached in `tts_cache/` | from disk, no credit (`scripts/warm_tts.py` pre-records them) |
| No key or credits exhausted (402) | nothing | browser voice, labelled "browser voice" |

### Voices

| Model | Voices | Notes |
|---|---|---|
| `timbre-v3.0` (default) | Avinash, Chetana, Devansh, Kalpana, Lakshmi, Prakash, Riyaa, **Shivani** (default), Shubham, Tarika, Vasudha, Yashraj, Harshad | every voice speaks all 10 languages; audio tags work |
| `timbre-v2.5` | Marathi: **Zahira**, **Ishaan**; Hindi: Nalini, Bhavna, Chitra, Yashvi, Ambuja, Jwala, Urmila…; Hinglish: **Poorvi** (`hi-en`) | one preferred language per voice; tags are stripped |

Pick voices with a native speaker: `python -m scripts.smoke --models` writes the same sentence in
v3.0 Kalpana and v2.5 Zahira to `samples/` for comparison.

## Evon (understanding the complaint)

Evon v3.3 (`gnani/gnani-evon-v3.3-30B-A3B`) is open-weight; the Gnani docs list no hosted endpoint, so you
serve it yourself:

```bash
pip install -U "vllm>=0.12.0"
vllm serve gnani/gnani-evon-v3.3-30B-A3B --served-model-name evon --max-model-len 8192 --port 8001 --trust-remote-code
```

The adapter calls `POST {EVON_BASE_URL}/v1/chat/completions` with `temperature: 0`,
`chat_template_kwargs: {"enable_thinking": false}` and `response_format: {"type": "json_object"}`. A
server that rejects either optional field is retried without it. `<think>` blocks and code fences are
stripped; invalid JSON is retried once; after that the rule-based extractor runs and the call is
labelled. Numbers Evon returns that are not in the transcript are dropped. When Evon is down or
`EVON_ENABLED=0`, the rule-based extractor runs and every screen says "rules".

## Errors and limits

| HTTP | Meaning | What the app does |
|---|---|---|
| 401 | missing or invalid key | no retry; notice "check GNANI_API_KEY"; typed input offered |
| 402 | no credit | no retry; **all further paid calls stop** for this run; text replies |
| 403 | key lacks the model or scope | no retry; notice |
| 422 | validation | no retry; notice |
| 429 | rate limit (some accounts allow one active request) | retried after 0.5 s and 1 s; all Gnani calls are serialised (`GNANI_CONCURRENCY=1`) |
| 500/502/503/504 | transient | retried twice with backoff |

## Checking it on your key

```bash
python -m scripts.doctor --online     # key accepted?
python -m scripts.smoke               # ~8 requests: Timbre file, stream (first-audio time), phone line,
                                      # ticket digits; Prisma on Timbre's audio with and without context
```

Listen to the files in `samples/` and record the results in docs/costs.md.
