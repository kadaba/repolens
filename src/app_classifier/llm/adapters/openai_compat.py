"""OpenAI-compatible adapter for any service that mimics /v1/chat/completions.

Covers: LM Studio, vLLM, llama.cpp server, Groq, Together, Fireworks,
DeepSeek, Mistral, Perplexity — anything implementing the OpenAI shape.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app_classifier.llm._http import post_json


async def _post_json_async(url, body, headers=None, **kw):
    return await asyncio.to_thread(post_json, url, body, headers, **kw)


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
    ):
        if not base_url:
            raise ValueError("base_url required")
        if not model:
            raise ValueError("model required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

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
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
