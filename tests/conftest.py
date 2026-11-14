import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Tests never touch the real API key, the real DB or the TTS cache.
os.environ["GNANI_API_KEY"] = ""
os.environ["EVON_ENABLED"] = "0"


@pytest.fixture(autouse=True)
def fresh_env(tmp_path, monkeypatch):
    from app.config import reload_settings
    from app import db
    reload_settings(DB_PATH=str(tmp_path / "test.db"), GNANI_API_KEY="", EVON_ENABLED=False,
                    TTS_CACHE_DIR=str(tmp_path / "tts"), API_LOG_PATH=str(tmp_path / "calls.jsonl"),
                    APP_SALT="test-salt", APP_SECRET="test-secret", DEMO_MODE=True,
                    DEMO_IGNORE_QUIET_HOURS=True, DEMO_CALLBACK_DELAY_SEC=0, DEMO_VERIFY_DELAY_SEC=0)
    db.init_db()
    yield


@pytest.fixture
def con():
    from app import db
    c = db.connect()
    yield c
    c.close()
