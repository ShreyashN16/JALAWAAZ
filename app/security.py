"""Identity hashing, tokens, PIN login checks and a small in-memory rate limiter."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from .config import settings


def hash_id(raw: str) -> str:
    """Salted, keyed hash of a phone number or device id. The raw value is never stored."""
    return hmac.new(settings.APP_SALT.encode(), (raw or "").strip().encode(), hashlib.sha256).hexdigest()[:32]


def new_token(n: int = 18) -> str:
    return secrets.token_urlsafe(n)


def role_for_pin(pin: str) -> str | None:
    pin = (pin or "").strip()
    if pin and hmac.compare_digest(pin, settings.ENGINEER_PIN):
        return "engineer"
    if pin and hmac.compare_digest(pin, settings.OFFICER_PIN):
        return "officer"
    return None


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        t = time.monotonic()
        q = self.hits[key]
        while q and t - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(t)
        return True
