import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app_classifier.smart import classify_smart, classify_smart_async


FIXTURES = Path(__file__).parent / "fixtures"


def _make_stub_provider(responses):
    """Stub that records call count + returns canned responses (matches agent.py style)."""
    state = {"i": 0, "count": 0}
    async def provider(prompt, max_tokens=400, temperature=0.0):
        state["count"] += 1
        i = state["i"]
        state["i"] += 1
        return responses[i] if i < len(responses) else None
    provider.calls = state
    return provider


def test_classify_smart_high_confidence_does_not_call_llm():
    """ecommerce_django has 0.95 confidence > 0.75 default → no LLM call."""
    stub = _make_stub_provider([])  # No canned responses; would fail if called
    result = classify_smart(
        str(FIXTURES / "ecommerce_django"),
        llm_provider=stub,
        auto_load_provider=False,
    )
    assert result.app_category == "e-commerce"
    assert result.app_category_confidence >= 0.75
    assert stub.calls["count"] == 0
