"""Gnani model, voice and language catalogue.

Copied from docs.gnani.ai (Available Voices, TTS REST, STT REST, Prisma v3.0 pages), re-checked on
2026-11-13. Used to validate configuration *before* a request costs a credit, and to label the UI.
If Gnani adds voices, extend these sets; a voice that is not listed is reported as a warning, not
blocked, so a newer voice still works.
"""
from __future__ import annotations

DOCS_CHECKED = "2026-11-13"

STT_MODELS = {"prisma-v3.0", "prisma-v2.5"}
STT_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"}
STT_FORMATS_V3 = {"verbatim", "transcribe", "codemix", "transliterate"}
STT_FORMATS_V25 = {"verbatim", "transcribe"}
KEYTERMS_MAX = 200            # v3.0 keyterms (words or short phrases)
BIAS_LIST_MAX = 100           # v2.5 bias_list (single words, letters only)
TOPIC_MAX_CHARS = 1600
PREVIOUS_TEXT_KEEP = 600      # Prisma keeps only the last 600 characters
SUBSTITUTION_MAX_RULES = 10
REST_MAX_SECONDS = 30.0

TTS_MODELS = {"timbre-v3.0", "timbre-v2.5"}
TTS_LANGS = {"auto", "hi-IN", "en-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "bn-IN", "gu-IN", "hi-en"}
TTS_CONTAINERS = {"wav", "raw", "mp3", "ogg", "mulaw", "alaw"}
TTS_SAMPLE_RATES = {8000, 16000, 22050, 24000, 44100, 48000}
TTS_BITRATES = {"32k", "64k", "96k", "128k", "192k"}
TTS_SPEED_RANGE = (0.85, 1.15)
CONTAINER_MIME = {"wav": "audio/wav", "raw": "application/octet-stream", "mp3": "audio/mpeg",
                  "ogg": "audio/ogg", "mulaw": "audio/basic", "alaw": "audio/alaw"}

# Timbre v3.0: 13 voices, every voice speaks all 10 languages. Audio tags work only on v3.0.
V30_VOICES = {
    "Avinash": "male, professional", "Chetana": "female, warm, healthcare/telecom care",
    "Devansh": "male, conversational", "Kalpana": "female, warm, customer care",
    "Lakshmi": "female, expressive, narration", "Prakash": "male, professional",
    "Riyaa": "female, confident", "Shivani": "female, warm, inbound support",
    "Shubham": "male, expressive", "Tarika": "female, warm, customer care",
    "Vasudha": "female, expressive, narration", "Yashraj": "male, warm, IVR narration",
    "Harshad": "male, professional",
}

# Timbre v2.5: 42 voices, each with one preferred language.
V25_VOICES = {
    "Ambuja": "hi-IN", "Asmita": "ta-IN", "Bhavna": "hi-IN", "Brinda": "ta-IN", "Chitra": "hi-IN",
    "Deepak": "hi-IN", "Devika": "en-IN", "Dhruva": "bn-IN", "Falak": "gu-IN", "Girish": "en-IN",
    "Hemraj": "hi-IN", "Ishaan": "mr-IN", "Jalaj": "hi-IN", "Jwala": "hi-IN", "Kaveri": "en-IN",
    "Kavin": "kn-IN", "Kirra": "bn-IN", "Lavanya": "te-IN", "Lehara": "te-IN", "Mehuli": "pa-IN",
    "Nalini": "hi-IN", "Noopur": "ta-IN", "Omkar": "hi-IN", "Poorvi": "hi-en", "Pranav": "en-IN",
    "Reshma": "ml-IN", "Riyaan": "ml-IN", "Roopesh": "hi-IN", "Saanvi": "kn-IN", "Shlok": "en-IN",
    "Suhana": "te-IN", "Trisha": "ta-IN", "Trupti": "en-IN", "Urmila": "hi-IN", "Varuni": "te-IN",
    "Vedika": "ta-IN", "Veera": "gu-IN", "Vikrant": "hi-IN", "Yashvi": "hi-IN", "Yukti": "te-IN",
    "Zahira": "mr-IN", "Zayan": "pa-IN",
}

AUDIO_TAGS_V30 = {"<laugh>", "<giggle>", "<sigh>", "<exhales>", "<sniffles>", "<yawns>", "<coughs>",
                  "<clears throat>", "<whispers>", "<shouting>", "<excited>", "<slow>", "<pauses>"}

# Neutral pause marker used by app/core/templates.py. The Timbre adapter turns it into the
# <pauses> audio tag on v3.0 and into a comma everywhere else (v2.5, browser voice, captions).
PAUSE = "⏸"


def voices_for(model: str) -> dict:
    return V30_VOICES if model == "timbre-v3.0" else V25_VOICES if model == "timbre-v2.5" else {}


def voice_problem(model: str, voice: str) -> str | None:
    """None when the voice belongs to the model; otherwise a human explanation."""
    if model not in TTS_MODELS:
        return f"Unknown TTS model {model!r}; use timbre-v3.0 or timbre-v2.5"
    if voice in voices_for(model):
        return None
    other = "timbre-v2.5" if model == "timbre-v3.0" else "timbre-v3.0"
    if voice in voices_for(other):
        return f"Voice {voice!r} belongs to {other}, but GNANI_TTS_MODEL is {model} (Gnani returns 400)"
    return f"Voice {voice!r} is not in the documented {model} catalogue (checked {DOCS_CHECKED})"


def pauses_as_commas(text: str) -> str:
    """Replace pause markers with commas, without leaving ' ,' or ',,' behind."""
    import re
    t = text.replace(PAUSE, ",")
    t = re.sub(r"\s*,(?:\s*,)+", ",", t)       # ,, -> ,
    t = re.sub(r"\s+,", ",", t)                # 'x ,' -> 'x,'
    t = re.sub(r"([।.?!])\s*,", r"\1", t)      # sentence end followed by a pause: keep the full stop
    t = re.sub(r",(?=[^\s\d])", ", ", t)
    return re.sub(r"\s{2,}", " ", t).strip(" ,")
