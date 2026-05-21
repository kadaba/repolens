import asyncio
import json
from unittest.mock import patch

import pytest

from app_classifier.llm.adapters.openai import OpenAIProvider
from app_classifier.llm.adapters.anthropic import AnthropicProvider
from app_classifier.llm.adapters.openai_compat import OpenAICompatProvider
from app_classifier.llm.adapters.openrouter import OpenRouterProvider
from app_classifier.llm.adapters.ollama import OllamaProvider


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


def test_openai_compat_provider_no_api_key_allowed():
    """Local servers (LM Studio, llama.cpp) often have no auth."""
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["headers"] = headers or {}
        return {"choices": [{"message": {"content": "ok"}}]}
    with patch("app_classifier.llm.adapters.openai_compat._post_json_async", fake_post):
        p = OpenAICompatProvider(
            base_url="http://localhost:1234/v1", api_key=None, model="llama-3"
        )
        out = asyncio.run(p.complete("x"))
    assert out == "ok"
    assert "Authorization" not in captured["headers"]


def test_openai_compat_provider_with_api_key():
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["headers"] = headers or {}
        captured["url"] = url
        return {"choices": [{"message": {"content": "ok"}}]}
    with patch("app_classifier.llm.adapters.openai_compat._post_json_async", fake_post):
        p = OpenAICompatProvider(
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk_x", model="llama-3.3-70b"
        )
        asyncio.run(p.complete("x"))
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer gsk_x"


def test_openai_compat_satisfies_both_contracts():
    from app_classifier.llm.provider import LLMProviderProtocol
    p = OpenAICompatProvider(base_url="http://x", model="m")
    assert isinstance(p, LLMProviderProtocol)
    assert callable(p)
    assert p.name == "openai_compat"


def test_openrouter_provider_adds_required_headers():
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["headers"] = headers
        captured["url"] = url
        captured["body"] = body
        return {"choices": [{"message": {"content": "router response"}}]}
    with patch("app_classifier.llm.adapters.openrouter._post_json_async", fake_post):
        p = OpenRouterProvider(
            api_key="sk-or-test",
            model="anthropic/claude-haiku-4-5-20251001",
            app_name="my-app",
            app_url="https://example.com",
        )
        out = asyncio.run(p.complete("hi"))
    assert out == "router response"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-or-test"
    assert captured["headers"]["HTTP-Referer"] == "https://example.com"
    assert captured["headers"]["X-Title"] == "my-app"
    assert captured["body"]["model"] == "anthropic/claude-haiku-4-5-20251001"


def test_openrouter_satisfies_both_contracts():
    from app_classifier.llm.provider import LLMProviderProtocol
    p = OpenRouterProvider(api_key="sk-or-x")
    assert isinstance(p, LLMProviderProtocol)
    assert callable(p)
    assert p.name == "openrouter"


def test_ollama_provider_request_shape():
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["url"] = url
        captured["body"] = body
        return {"response": "ollama response", "done": True}
    with patch("app_classifier.llm.adapters.ollama._post_json_async", fake_post):
        p = OllamaProvider(host="http://localhost:11434", model="llama3.2")
        out = asyncio.run(p.complete("hi", max_tokens=150, temperature=0.0))
    assert out == "ollama response"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["body"]["model"] == "llama3.2"
    assert captured["body"]["prompt"] == "hi"
    assert captured["body"]["stream"] is False
    assert captured["body"]["options"]["num_predict"] == 150
    assert captured["body"]["options"]["temperature"] == 0.0


def test_ollama_provider_no_auth_header():
    captured = {}
    async def fake_post(url, body, headers=None, **kw):
        captured["headers"] = headers or {}
        return {"response": "x"}
    with patch("app_classifier.llm.adapters.ollama._post_json_async", fake_post):
        asyncio.run(OllamaProvider().complete("x"))
    assert "Authorization" not in captured["headers"]


def test_ollama_satisfies_both_contracts():
    from app_classifier.llm.provider import LLMProviderProtocol
    p = OllamaProvider()
    assert isinstance(p, LLMProviderProtocol)
    assert callable(p)
    assert p.name == "ollama"
