"""Anthropic Messages API adapter."""
from __future__ import annotations

import asyncio
from typing import Optional

from app_classifier.llm._http import post_json

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"


async def _post_json_async(url, body, headers=None, **kw):
    return await asyncio.to_thread(post_json, url, body, headers, **kw)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        base_url: Optional[str] = None,
    ):
        if not api_key:
            raise ValueError("api_key required")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.0,
    ) -> Optional[str]:
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
        }
        resp = await _post_json_async(f"{self.base_url}/messages", body, headers)
        if not resp:
            return None
        try:
            blocks = resp.get("content") or []
            for block in blocks:
                if block.get("type") == "text":
                    return block.get("text")
            return None
        except (KeyError, IndexError, TypeError):
            return None

    __call__ = complete
