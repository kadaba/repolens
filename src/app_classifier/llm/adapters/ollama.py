"""Ollama adapter — local LLM serving via /api/generate (non-streaming)."""
from __future__ import annotations

import asyncio
from typing import Optional

from app_classifier.llm._http import post_json

DEFAULT_HOST = "http://localhost:11434"


async def _post_json_async(url, body, headers=None, **kw):
    return await asyncio.to_thread(post_json, url, body, headers, **kw)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        model: str = "llama3.2",
    ):
        self.host = host.rstrip("/")
        self.model = model

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.0,
    ) -> Optional[str]:
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        resp = await _post_json_async(f"{self.host}/api/generate", body, headers={})
        if not resp:
            return None
        return resp.get("response")

    __call__ = complete
