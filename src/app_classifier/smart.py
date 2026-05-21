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
