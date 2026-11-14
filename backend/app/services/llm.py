"""Optional local LLM (Ollama). Used only for wording/structuring, never as a source of facts.

All callers must have a deterministic fallback; ``LLMClient.available`` is False when Ollama is not
running or LLM_PROVIDER=none.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        self.settings = get_settings()
        self._available: bool | None = None
        self._checked_at = 0.0
        self._lock = threading.Lock()  # small local models: serialize requests

    @property
    def model(self) -> str:
        return self.settings.ollama_model

    @property
    def available(self) -> bool:
        if self.settings.llm_provider == "none":
            return False
        now = time.time()
        if self._available is None or now - self._checked_at > 60:
            try:
                r = httpx.get(f"{self.settings.ollama_url}/api/tags", timeout=3)
                names = [m.get("name", "") for m in r.json().get("models", [])]
                self._available = r.status_code == 200 and any(n.split(":")[0] == self.model.split(":")[0] for n in names)
            except (httpx.HTTPError, ValueError):
                self._available = False
            self._checked_at = now
        return bool(self._available)

    def status(self) -> dict:
        return {
            "provider": self.settings.llm_provider,
            "model": self.model,
            "url": self.settings.ollama_url,
            "available": self.available,
        }

    def generate(self, prompt: str, system: str | None = None, max_tokens: int = 400, temperature: float = 0.3, json_mode: bool = False) -> str | None:
        if not self.available:
            return None
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"
        try:
            with self._lock:
                r = httpx.post(f"{self.settings.ollama_url}/api/generate", json=payload, timeout=self.settings.llm_timeout_seconds)
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("LLM call failed: %s", exc)
            return None

    def generate_json(self, prompt: str, system: str | None = None, max_tokens: int = 600) -> dict | list | None:
        raw = self.generate(prompt, system=system, max_tokens=max_tokens, json_mode=True, temperature=0.2)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            m = re.search(r"(\{.*\}|\[.*\])", raw, re.S)
            if m:
                try:
                    return json.loads(m.group(1))
                except ValueError:
                    return None
        return None


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
