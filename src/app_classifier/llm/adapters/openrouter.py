"""OpenRouter adapter — OpenAI-compatible shape with attribution headers."""
from __future__ import annotations

import asyncio
from typing import Optional

from app_classifier.llm._http import post_json

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


async def _post_json_async(url, body, headers=None, **kw):
    return await asyncio.to_thread(post_json, url, body, headers, **kw)


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-haiku-4-5-20251001",
        app_name: str = "app-classifier",
        app_url: str = "https://github.com/codefixer/app-classifier",
    ):
        if not api_key:
            raise ValueError("api_key required")
        self.api_key = api_key
        self.model = model
        self.app_name = app_name
        self.app_url = app_url
        self.base_url = DEFAULT_BASE_URL

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.0,
    ) -> Optional[str]:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.app_url,
            "X-Title": self.app_name,
        }
        resp = await _post_json_async(
            f"{self.base_url}/chat/completions", body, headers
        )
        if not resp:
            return None
        try:
            return resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

    __call__ = complete
