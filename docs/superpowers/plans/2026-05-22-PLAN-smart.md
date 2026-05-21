# PLAN-smart — classify_smart() Implementation

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `classify_smart()` (sync) and `classify_smart_async()` (returns full agent audit trail) that run the deterministic `classify()` first, and only escalate to `classify_agentic()` when confidence is below the threshold and a provider is available.

**Architecture:** One module: `src/app_classifier/smart.py`. Thin wrapper — no new analysis logic. Honors three-way provider precedence: explicit arg > auto-loaded > None. When no provider is available, returns the low-confidence baseline rather than raising.

**Tech Stack:** Python 3.10+, stdlib only, pytest with stub providers (no network).

**Wave:** 2. **Depends on PLAN-llm completing** (uses `load_provider` from `app_classifier.llm`).

**Spec reference:** `docs/superpowers/specs/2026-05-22-v0.5.0-design.md` § Component 2 (`classify_smart()`).

---

## File Structure

| Path | Purpose |
|---|---|
| `src/app_classifier/smart.py` | NEW — `classify_smart` + `classify_smart_async` |
| `src/app_classifier/__init__.py` | MODIFY — re-export both functions |
| `tests/test_smart.py` | NEW — escalation paths + provider precedence |

---

## Chunk 1: classify_smart() with all branches covered

### Task 1: High-confidence baseline path (no LLM, no network)

**Files:**
- Create: `src/app_classifier/smart.py`
- Create: `tests/test_smart.py`

- [ ] **Step 1: Write failing test for baseline short-circuit**

```python
# tests/test_smart.py
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
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_smart.py::test_classify_smart_high_confidence_does_not_call_llm -v
```

Expected: `ModuleNotFoundError: No module named 'app_classifier.smart'`.

- [ ] **Step 3: Implement `smart.py` (minimal — just the high-confidence path)**

```python
# src/app_classifier/smart.py
"""classify_smart() — deterministic-first, LLM-escalated when confidence is low.

Layered on top of the existing classify() and classify_agentic() APIs. Adds
no new analysis logic — its job is to pick the right path based on confidence
and provider availability.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional, Union

from app_classifier.classifier import classify, AppDescription
from app_classifier.agent import classify_agentic, AgentClassificationResult

# Top-level import — makes `patch("app_classifier.smart.load_provider")` work
# as a stable test target. PLAN-llm is a hard prerequisite (Wave 2 dep).
from app_classifier.llm import load_provider
from app_classifier.llm.provider import LLMConfigError


ProviderLike = Optional[Any]  # LLMProviderProtocol | LLMProvider Callable | None


def _resolve_provider(
    explicit: ProviderLike, auto_load: bool
) -> ProviderLike:
    if explicit is not None:
        return explicit
    if not auto_load:
        return None
    try:
        return load_provider()
    except LLMConfigError:
        # Misconfigured provider (e.g., missing ${VAR}) — degrade to baseline
        # rather than raising. Honors the spec's "no surprises in default path."
        return None


def classify_smart(
    repo: str,
    *,
    llm_provider: ProviderLike = None,
    confidence_threshold: float = 0.75,
    auto_load_provider: bool = True,
) -> AppDescription:
    """Rule-based first; LLM-escalated for low-confidence cases.

    Args:
        repo: Path to the repository root.
        llm_provider: Explicit provider (Protocol or Callable). Wins over auto-loaded.
        confidence_threshold: Below this, escalate to classify_agentic.
        auto_load_provider: If True (default), call load_provider() to discover
            a configured provider from env/config when no explicit one is passed.

    Returns:
        AppDescription. When no provider is available and confidence is low,
        returns the low-confidence baseline rather than raising.
    """
    baseline = classify(repo)
    if baseline.app_category_confidence >= confidence_threshold:
        return baseline

    provider = _resolve_provider(llm_provider, auto_load_provider)
    if provider is None:
        return baseline

    result = asyncio.run(classify_agentic(
        repo,
        llm_provider=provider,
        confidence_threshold=confidence_threshold,
    ))
    return result.description


async def classify_smart_async(
    repo: str,
    *,
    llm_provider: ProviderLike = None,
    confidence_threshold: float = 0.75,
    auto_load_provider: bool = True,
) -> AgentClassificationResult:
    """Async variant returning the full audit trail (steps, llm_calls, iterations).

    When the baseline is high-confidence, returns an AgentClassificationResult
    with iterations_used=0 and a synthetic conclude_baseline step (matching
    classify_agentic's no-LLM-path shape).
    """
    provider = _resolve_provider(llm_provider, auto_load_provider)
    if provider is None:
        # Force the baseline path inside classify_agentic by passing an
        # impossible threshold? No — easier: synthesize the result directly.
        baseline = classify(repo)
        return AgentClassificationResult(
            description=baseline,
            steps=[],
            llm_calls=0,
            iterations_used=0,
            final_confidence=baseline.app_category_confidence,
            changed_verdict=False,
            change_reason="No LLM provider configured",
        )

    return await classify_agentic(
        repo,
        llm_provider=provider,
        confidence_threshold=confidence_threshold,
    )
```

- [ ] **Step 4: Run test, expect pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_smart.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/app_classifier/smart.py tests/test_smart.py
git commit -m "smart: classify_smart high-confidence short-circuit"
```

---

### Task 2: Low-confidence escalation + no-provider fallthrough

**Files:**
- Modify: `tests/test_smart.py`

- [ ] **Step 1: Append failing tests**

```python
# tests/test_smart.py — append

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
```

- [ ] **Step 2: Run tests, expect pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_smart.py -v
```

Expected: 5 passed (1 from Task 1 + 4 new). The implementation in Task 1 already covers these branches — no `smart.py` change required.

- [ ] **Step 3: Commit**

```bash
git add tests/test_smart.py
git commit -m "smart: escalation + no-provider + explicit-override coverage"
```

---

### Task 3: classify_smart_async() with audit trail

**Files:**
- Modify: `tests/test_smart.py`

- [ ] **Step 1: Append failing tests**

```python
# tests/test_smart.py — append

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
```

- [ ] **Step 2: Run tests, expect pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_smart.py -v
```

Expected: 8 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_smart.py
git commit -m "smart: classify_smart_async audit-trail coverage"
```

---

### Task 4: Public re-exports

**Files:**
- Modify: `src/app_classifier/__init__.py`

- [ ] **Step 1: Append public-import smoke test**

```python
# tests/test_smart.py — append at end
def test_public_imports():
    from app_classifier import classify_smart, classify_smart_async
    assert callable(classify_smart)
    assert callable(classify_smart_async)
```

- [ ] **Step 2: Add re-exports**

Modify `src/app_classifier/__init__.py` — add the import and append to `__all__`:

```python
from app_classifier.smart import classify_smart, classify_smart_async
```

```python
    # Smart classification (v0.5.0)
    "classify_smart", "classify_smart_async",
```

- [ ] **Step 3: Run full suite**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -v
```

Expected: 42 existing + 16 from PLAN-llm + ~22 from PLAN-codemap + 9 from PLAN-smart ≈ 89 passed.

- [ ] **Step 4: Commit**

```bash
git add src/app_classifier/__init__.py tests/test_smart.py
git commit -m "smart: re-export classify_smart from app_classifier"
```

---

## Final verification

- [ ] **Step 1: Smoke test on a real fixture**

```bash
PYTHONPATH=src .venv/bin/python -c "
from app_classifier import classify_smart
r = classify_smart('tests/fixtures/ecommerce_django')
print('category:', r.app_category, 'conf:', r.app_category_confidence)
"
```

Expected: `category: e-commerce conf: 0.95`. No network call (rule-based shortcut).
