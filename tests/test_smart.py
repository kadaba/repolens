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


def test_classify_smart_low_confidence_calls_provider():
    """confidence_threshold=0.99 forces escalation against blog_flask."""
    stub = _make_stub_provider([
        '{"action": "conclude", "arguments": {"category": "blog / content platform", '
        '"confidence": 0.92, "features": ["publishing"], '
        '"description": "A Flask-based blog with posts and comments."}, '
        '"reasoning": "model names confirm blog domain"}',
    ])
    result = classify_smart(
        str(FIXTURES / "blog_flask"),
        llm_provider=stub,
        confidence_threshold=0.99,
        auto_load_provider=False,
    )
    assert stub.calls["count"] == 1
    assert result.app_category == "blog / content platform"


def test_classify_smart_no_provider_returns_baseline():
    """When no provider is configured and confidence is low, fall through to baseline."""
    # load_provider is imported at top of smart.py — patch the name in that module.
    with patch("app_classifier.smart.load_provider", return_value=None):
        result = classify_smart(
            str(FIXTURES / "blog_flask"),
            confidence_threshold=0.99,
            auto_load_provider=True,
        )
    assert result.app_category == "blog / content platform"
    assert result.app_category_confidence < 0.99


def test_classify_smart_misconfigured_provider_degrades_to_baseline():
    """If load_provider raises LLMConfigError, classify_smart falls back to baseline."""
    from app_classifier.llm.provider import LLMConfigError
    def boom():
        raise LLMConfigError("missing ${ANTHROPIC_API_KEY}")
    with patch("app_classifier.smart.load_provider", side_effect=boom):
        result = classify_smart(
            str(FIXTURES / "blog_flask"),
            confidence_threshold=0.99,
            auto_load_provider=True,
        )
    assert result.app_category == "blog / content platform"


def test_classify_smart_explicit_provider_wins_over_autoload():
    """Explicit llm_provider must override auto-loaded one — load_provider is never even called."""
    stub = _make_stub_provider([
        '{"action": "conclude", "arguments": {"category": "OVERRIDE-WINS", '
        '"confidence": 0.91, "features": [], '
        '"description": "Provider explicitly passed in won."}, "reasoning": "explicit"}',
    ])
    # Patch load_provider in smart.py — if explicit provider works, load_provider
    # MUST NOT be called. side_effect=AssertionError will trip if it is.
    with patch(
        "app_classifier.smart.load_provider",
        side_effect=AssertionError("load_provider should not be called when explicit provider given"),
    ) as mock_load:
        result = classify_smart(
            str(FIXTURES / "blog_flask"),
            llm_provider=stub,
            confidence_threshold=0.99,
        )
    assert result.app_category == "OVERRIDE-WINS"
    assert stub.calls["count"] == 1
    mock_load.assert_not_called()


def test_classify_smart_auto_load_disabled_returns_baseline():
    """auto_load_provider=False + no explicit provider = always baseline."""
    result = classify_smart(
        str(FIXTURES / "blog_flask"),
        confidence_threshold=0.99,
        auto_load_provider=False,
    )
    # No provider tried, baseline returned with low confidence
    assert result.app_category == "blog / content platform"


def test_classify_smart_async_returns_audit_trail_on_escalation():
    """When confidence is low and provider available, return full AgentClassificationResult."""
    stub = _make_stub_provider([
        '{"action": "conclude", "arguments": {"category": "blog / content platform", '
        '"confidence": 0.88, "features": ["publishing"], '
        '"description": "Flask blog."}, "reasoning": "x"}',
    ])
    result = asyncio.run(classify_smart_async(
        str(FIXTURES / "blog_flask"),
        llm_provider=stub,
        confidence_threshold=0.99,
        auto_load_provider=False,
    ))
    assert hasattr(result, "steps")
    assert hasattr(result, "llm_calls")
    assert result.llm_calls == 1
    assert result.description.app_category == "blog / content platform"


def test_classify_smart_async_no_provider_synthesizes_zero_iterations():
    """No provider configured → return baseline-wrapped AgentClassificationResult."""
    result = asyncio.run(classify_smart_async(
        str(FIXTURES / "blog_flask"),
        confidence_threshold=0.99,
        auto_load_provider=False,
    ))
    assert result.iterations_used == 0
    assert result.llm_calls == 0
    assert result.description.app_category == "blog / content platform"
    assert "No LLM provider" in result.change_reason


def test_classify_smart_async_high_confidence_uses_classify_agentic_baseline():
    """ecommerce_django (conf=0.95) goes through classify_agentic which short-circuits."""
    stub = _make_stub_provider([])
    result = asyncio.run(classify_smart_async(
        str(FIXTURES / "ecommerce_django"),
        llm_provider=stub,
        auto_load_provider=False,
    ))
    assert result.llm_calls == 0
    assert result.iterations_used == 0
    # The classify_agentic baseline shortcut records a conclude_baseline step
    assert any(s.action == "conclude_baseline" for s in result.steps)


def test_public_imports():
    from app_classifier import classify_smart, classify_smart_async
    assert callable(classify_smart)
    assert callable(classify_smart_async)
