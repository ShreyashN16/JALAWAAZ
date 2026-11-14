"""Configuration: environment variables (.env) plus data/config.json.

Every threshold in data/config.json is a prototype assumption to be reviewed with a Jal Mitra or an
engineer. Nothing here is validated field data. See docs/CONFIGURATION.md for every setting.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "2.0.1"


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (no dependency). Existing environment variables win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


def _b(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Gnani speech APIs
    GNANI_API_KEY: str = ""
    GNANI_STT_URL: str = "https://api.vachana.ai/stt/v3"
    GNANI_STT_LANGUAGES_URL: str = "https://api.vachana.ai/stt/v3/languages"
    GNANI_STT_MODEL: str = "prisma-v3.0"
    GNANI_TTS_URL: str = "https://api.vachana.ai/api/v1/tts/inference"
    GNANI_TTS_SSE_URL: str = "https://api.vachana.ai/api/v1/tts/sse"
    GNANI_TTS_MODEL: str = "timbre-v3.0"
    GNANI_CONCURRENCY: int = 1
    GNANI_TIMEOUT_SEC: float = 45.0
    TTS_VOICE_MR: str = "Shivani"
    TTS_VOICE_HI: str = "Shivani"
    TTS_VOICE_HIEN: str = "Poorvi"
    TTS_FORMAT: str = "mp3"                 # browser audio: mp3 (small, streams) | wav | ogg
    TTS_SAMPLE_RATE: int = 24000
    TTS_BITRATE: str = "64k"
    TTS_STREAMING: bool = True              # Timbre SSE; falls back to REST automatically
    TTS_TELEPHONE_CONTAINER: str = "mulaw"  # used when a call runs in telephone (8 kHz) mode
    # Evon (self-hosted, OpenAI-compatible)
    EVON_ENABLED: bool = True
    EVON_BASE_URL: str = "http://localhost:8001"
    EVON_SERVED_NAME: str = "evon"
    EVON_API_KEY: str = ""
    EVON_TIMEOUT_SEC: float = 20.0
    EVON_JSON_MODE: bool = True             # ask the server for response_format=json_object
    # App
    APP_SALT: str = "change-me"
    APP_SECRET: str = "change-me-too"
    ENGINEER_PIN: str = "2468"
    OFFICER_PIN: str = "1357"
    DB_PATH: str = str(ROOT / "jalawaaz.db")
    TELEPHONE_MODE: bool = False
    DEMO_MODE: bool = True
    DEMO_CALLBACK_DELAY_SEC: int = 5
    DEMO_VERIFY_DELAY_SEC: int = 8
    DEMO_VERIFY_RETRY_SEC: int = 30
    DEMO_IGNORE_QUIET_HOURS: bool = True
    SMS_PROVIDER: str = "console"
    MAP_TILE_URL: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    MAP_TILE_ATTRIBUTION: str = "© OpenStreetMap contributors"
    TTS_CACHE_DIR: str = str(ROOT / "tts_cache")
    API_LOG_PATH: str = str(ROOT / "logs" / "gnani_calls.jsonl")
    MAX_UPLOAD_BYTES: int = 2_000_000
    cfg: dict = field(default_factory=dict)

    @property
    def gnani_configured(self) -> bool:
        return bool(self.GNANI_API_KEY)

    @property
    def defaults_in_use(self) -> list[str]:
        out = []
        if self.APP_SALT in ("", "change-me"):
            out.append("APP_SALT")
        if self.APP_SECRET in ("", "change-me-too"):
            out.append("APP_SECRET")
        if self.ENGINEER_PIN == "2468":
            out.append("ENGINEER_PIN")
        if self.OFFICER_PIN == "1357":
            out.append("OFFICER_PIN")
        return out


DEFAULT_CFG = {
    "stt": {"first_turn_languages": "mr-IN,hi-IN,en-IN", "format": "transcribe", "max_clip_seconds": 30,
            "context": {"keyterms": True, "topic": True, "previous_text": True},
            "substitutions": []},
    "tts": {"speed": 1.0, "spell_numbers": True, "audio_tags": True},
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_cfg() -> dict:
    raw = json.loads((ROOT / "data" / "config.json").read_text(encoding="utf-8"))
    return _deep_merge(DEFAULT_CFG, raw)


def build_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    s = Settings()
    for name in Settings.__dataclass_fields__:
        if name == "cfg" or name not in os.environ:
            continue
        cur = getattr(s, name)
        raw = os.environ[name]
        try:
            if isinstance(cur, bool):
                setattr(s, name, _b(name, "0"))
            elif isinstance(cur, int):
                setattr(s, name, int(raw))
            elif isinstance(cur, float):
                setattr(s, name, float(raw))
            else:
                setattr(s, name, raw)
        except ValueError:
            raise SystemExit(f"Invalid value for {name} in .env: {raw!r}")
    s.cfg = load_cfg()
    return s


settings = build_settings()


def reload_settings(**overrides) -> Settings:
    """Rebuild settings in place (used by tests); keeps the same object identity."""
    fresh = build_settings()
    for k, v in vars(fresh).items():
        setattr(settings, k, v)
    for k, v in overrides.items():
        setattr(settings, k, v)
    return settings
