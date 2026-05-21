# tests/test_readme_quickstart.py
"""Acceptance criterion #5: README Quick Start snippets must execute against
a real fixture. If these fail, the README is broken."""
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "ecommerce_django"


def test_quickstart_snippet_1_pure_rule_based():
    """README claims ecommerce_django classifies as 'e-commerce' at 0.95 confidence."""
    from app_classifier import classify
    result = classify(str(FIXTURE))
    assert result.app_category == "e-commerce"
    # Pin to 0.95 — the documented v0.4.1 fingerprint behavior.
    # Loosening this would mask regressions in fingerprint tightening.
    assert result.app_category_confidence >= 0.95
    assert result.functional_description
    assert isinstance(result.routes, list)


def test_quickstart_snippet_2_high_confidence_short_circuit():
    """README §2 promise: 'High-confidence repos (≥0.75) return immediately with no LLM call.'

    We use the high-confidence ecommerce_django fixture with a stub provider that
    would error if invoked. This verifies the threshold behavior the README claims.
    """
    from app_classifier import classify_smart
    bomb_calls = {"count": 0}
    async def bomb(prompt, max_tokens=400, temperature=0.0):
        bomb_calls["count"] += 1
        raise AssertionError("LLM should NOT be called for high-confidence fixture")
    result = classify_smart(
        str(FIXTURE), llm_provider=bomb, auto_load_provider=False,
    )
    assert result.app_category == "e-commerce"
    assert result.app_category_confidence >= 0.95
    assert bomb_calls["count"] == 0


def test_quickstart_snippet_2_low_confidence_uses_provider():
    """README §2 promise (second half): 'ambiguous ones get the agentic treatment.'

    Force escalation via confidence_threshold=0.99 and supply a stub provider that
    returns a valid conclude action — matches PLAN-smart's test pattern.
    """
    from app_classifier import classify_smart
    state = {"i": 0}
    async def stub(prompt, max_tokens=400, temperature=0.0):
        state["i"] += 1
        return (
            '{"action": "conclude", "arguments": {"category": "blog / content platform", '
            '"confidence": 0.9, "features": ["publishing"], '
            '"description": "Flask blog."}, "reasoning": "x"}'
        )
    blog_fixture = FIXTURE.parent / "blog_flask"
    result = classify_smart(
        str(blog_fixture),
        llm_provider=stub,
        confidence_threshold=0.99,
        auto_load_provider=False,
    )
    assert result.app_category == "blog / content platform"
    assert state["i"] >= 1


def test_quickstart_snippet_3_map_code():
    from app_classifier import map_code
    cm = map_code(str(FIXTURE))
    assert cm.entry_points  # at least one
    # impact_of on a random known file should not crash
    if cm.files:
        first_file = next(iter(cm.files))
        impact = cm.impact_of(first_file)
        assert isinstance(impact, list)
