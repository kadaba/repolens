"""OpenAI Chat Completions adapter.

Setting base_url=None uses api.openai.com. Setting it to anything else
makes the adapter speak the same shape to LM Studio / vLLM / llama.cpp
server / Groq / Together / Fireworks / DeepSeek / Mistral.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app_classifier.llm._http import post_json

DEFAULT_BASE_URL = "https://api.openai.com/v1"


async def _post_json_async(url, body, headers=None, **kw):
    return await asyncio.to_thread(post_json, url, body, headers, **kw)


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
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
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = await _post_json_async(
            f"{self.base_url}/chat/completions",
            body,
            headers,
        )
        if not resp:
            return None
        try:
            return resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

    __call__ = complete
