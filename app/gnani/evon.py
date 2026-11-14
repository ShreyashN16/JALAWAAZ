"""Evon v3.3 (gnani/gnani-evon-v3.3-30B-A3B) through YOUR OWN OpenAI-compatible server.

Evon is open-weight. The Gnani docs list no hosted endpoint, so serve it with vLLM or SGLang:
  vllm serve gnani/gnani-evon-v3.3-30B-A3B --served-model-name evon --max-model-len 8192 \
       --port 8001 --trust-remote-code
Extraction uses temperature 0, disables reasoning traces (chat_template_kwargs) and asks for a JSON
object (response_format). Servers that reject either optional field are retried without it, so any
OpenAI-compatible server version works.
"""
from __future__ import annotations

import re
import time

from .. import db
from ..config import settings
from .base import LLM
from .client import httpx, make_client

THINK = re.compile(r"<think>.*?</think>", re.S)
OPTIONAL = ("response_format", "chat_template_kwargs")


class EvonError(Exception):
    pass


class Evon(LLM):
    name = "evon"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.EVON_API_KEY}"} if settings.EVON_API_KEY else {}

    async def complete(self, system: str, user: str, max_tokens: int = 400) -> str:
        body = {"model": settings.EVON_SERVED_NAME,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0, "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": False}}
        if settings.EVON_JSON_MODE:
            body["response_format"] = {"type": "json_object"}
        url = settings.EVON_BASE_URL.rstrip("/") + "/v1/chat/completions"
        for attempt in range(1 + len(OPTIONAL)):
            t0 = time.perf_counter()
            try:
                async with make_client(settings.EVON_TIMEOUT_SEC) as c:
                    r = await c.post(url, json=body, headers=self._headers())
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                db.log_api_call("llm", "evon", 0, False, (time.perf_counter() - t0) * 1000, attempt, "NETWORK")
                raise EvonError(f"Evon server unreachable at {settings.EVON_BASE_URL}: {type(e).__name__}")
            ms = (time.perf_counter() - t0) * 1000
            db.log_api_call("llm", "evon", r.status_code, r.status_code == 200, ms, attempt,
                            None if r.status_code == 200 else str(r.status_code))
            if r.status_code in (400, 422) and any(k in body for k in OPTIONAL):
                text = r.text or ""
                named = [k for k in OPTIONAL if k in body and k in text]
                body.pop((named or [k for k in OPTIONAL if k in body])[0])
                continue
            if r.status_code != 200:
                raise EvonError(f"Evon HTTP {r.status_code}: {r.text[:200]}")
            try:
                content = r.json()["choices"][0]["message"].get("content") or ""
            except (ValueError, KeyError, IndexError, TypeError):
                raise EvonError("Evon returned an unexpected response shape")
            return THINK.sub("", content).strip()
        raise EvonError("Evon rejected the request with and without optional fields")

    async def ping(self) -> bool:
        try:
            async with make_client(3.0) as c:
                r = await c.get(settings.EVON_BASE_URL.rstrip("/") + "/v1/models", headers=self._headers())
            return r.status_code == 200
        except Exception:
            return False
