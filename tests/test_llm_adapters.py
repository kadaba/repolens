import asyncio
import json
from unittest.mock import patch

import pytest

from app_classifier.llm.adapters.openai import OpenAIProvider
from app_classifier.llm.adapters.anthropic import AnthropicProvider


def test_openai_provider_request_shape():
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        return {"choices": [{"message": {"content": "answer text"}}]}

    with patch("app_classifier.llm.adapters.openai._post_json_async", fake_post):
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini")
        out = asyncio.run(provider.complete("hello", max_tokens=100, temperature=0.0))

    assert out == "answer text"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["max_tokens"] == 100
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["messages"] == [{"role": "user", "content": "hello"}]


def test_openai_provider_satisfies_protocol_and_callable():
    """Both LLMProviderProtocol shape and bare-callable contract must hold."""
    from app_classifier.llm.provider import LLMProviderProtocol
    provider = OpenAIProvider(api_key="sk-test")
    assert isinstance(provider, LLMProviderProtocol)
    assert callable(provider)  # __call__ = complete is aliased


def test_openai_provider_returns_none_on_failure():
    async def fake_post(url, body, headers=None, **kw):
        return None  # _http returned None on error
    with patch("app_classifier.llm.adapters.openai._post_json_async", fake_post):
        provider = OpenAIProvider(api_key="sk-test")
        assert asyncio.run(provider.complete("x")) is None


def test_openai_provider_custom_base_url():
    """base_url override turns it into an OpenAI-compat client."""
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["url"] = url
        return {"choices": [{"message": {"content": "local response"}}]}
    with patch("app_classifier.llm.adapters.openai._post_json_async", fake_post):
        provider = OpenAIProvider(
            api_key="local-key", base_url="http://localhost:8000/v1",
        )
        asyncio.run(provider.complete("x"))
    assert captured["url"] == "http://localhost:8000/v1/chat/completions"


def test_anthropic_provider_request_shape():
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        return {"content": [{"type": "text", "text": "anthropic response"}]}

    with patch("app_classifier.llm.adapters.anthropic._post_json_async", fake_post):
        provider = AnthropicProvider(
            api_key="sk-ant-test", model="claude-haiku-4-5-20251001"
        )
        out = asyncio.run(provider.complete("hi", max_tokens=200, temperature=0.0))

    assert out == "anthropic response"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["body"]["model"] == "claude-haiku-4-5-20251001"
    assert captured["body"]["max_tokens"] == 200
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_anthropic_provider_satisfies_both_contracts():
    from app_classifier.llm.provider import LLMProviderProtocol
    p = AnthropicProvider(api_key="x")
    assert isinstance(p, LLMProviderProtocol)
    assert callable(p)
