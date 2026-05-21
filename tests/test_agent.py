"""Tests for the agentic classification mode."""
import asyncio
from pathlib import Path

import pytest

from app_classifier import (
    AgentClassificationResult,
    AgentStep,
    classify_agentic,
)
from app_classifier.agent import _detect_monorepo


FIXTURES = Path(__file__).parent / "fixtures"


# ── Monorepo detection (deterministic, no LLM) ──

def test_detect_monorepo_flat_repo_returns_false():
    is_mono, subapps = _detect_monorepo(FIXTURES / "blog_flask")
    assert is_mono is False
    assert subapps == []


def test_detect_monorepo_workspaces_returns_true():
    is_mono, subapps = _detect_monorepo(FIXTURES / "monorepo_two_apps")
    assert is_mono is True
    # frontend + api should both surface
    assert any("frontend" in s for s in subapps)
    assert any("api" in s for s in subapps)


# ── Agent loop with stub providers (no real LLM calls) ──

def _make_stub_provider(responses):
    """Build a stub LLM provider that yields canned responses in order."""
    state = {"i": 0}

    async def provider(prompt, max_tokens=400, temperature=0.0):
        i = state["i"]
        state["i"] += 1
        if i >= len(responses):
            return None
        return responses[i]
    return provider


def test_agent_uses_baseline_when_confidence_high():
    """e-commerce fixture has 95% confidence. Agent shouldn't call LLM at all."""
    stub = _make_stub_provider([])  # zero canned responses
    result = asyncio.run(classify_agentic(
        str(FIXTURES / "ecommerce_django"), llm_provider=stub,
    ))
    assert isinstance(result, AgentClassificationResult)
    assert result.description.app_category == "e-commerce"
    assert result.llm_calls == 0
    assert result.iterations_used == 0
    # One step recorded: the conclude-baseline shortcut
    assert any(s.action == "conclude_baseline" for s in result.steps)


def test_agent_loops_when_confidence_low():
    """Force a low-confidence path; agent should investigate then conclude."""
    # Use blog_flask but lower the threshold so the agent ALWAYS investigates.
    stub_conclude = _make_stub_provider([
        # First call — LLM picks a tool
        '{"action": "list_files", "arguments": {"pattern": "*.py"}, "reasoning": "see python files"}',
        # Second call — LLM concludes
        '{"action": "conclude", "arguments": {"category": "blog / content platform", "confidence": 0.85, "features": ["publishing"], "description": "A Flask-based blog engine where authors publish markdown posts and readers leave comments. Tagged content + RSS feed."}, "reasoning": "model names confirm blog domain"}',
    ])
    result = asyncio.run(classify_agentic(
        str(FIXTURES / "blog_flask"),
        llm_provider=stub_conclude,
        confidence_threshold=0.99,  # force the agent loop
        max_iterations=4,
    ))
    assert result.llm_calls == 2
    assert result.iterations_used == 2
    assert result.description.app_category == "blog / content platform"
    assert result.final_confidence == 0.85
    assert "Flask-based blog" in result.description.functional_description
    # Audit trail captured both steps
    action_names = [s.action for s in result.steps]
    assert "list_files" in action_names
    assert "conclude" in action_names


def test_agent_monorepo_synthesizes_top_level():
    """Monorepo fixture: agent classifies each sub-app, then LLM synthesizes."""
    stub = _make_stub_provider([
        # The synth call. LLM returns a top-level description.
        "This monorepo contains an Express-based frontend service and a FastAPI-based backend API that persists to PostgreSQL.",
    ])
    result = asyncio.run(classify_agentic(
        str(FIXTURES / "monorepo_two_apps"), llm_provider=stub,
    ))
    assert result.is_monorepo is True
    assert len(result.subapps) >= 2
    assert result.changed_verdict is True
    assert result.description.app_category == "monorepo"
    assert "Express" in result.description.functional_description
    assert result.llm_calls == 1  # only the synth call
    # No agent loop on monorepo path
    assert result.iterations_used == 0


def test_agent_handles_broken_llm_gracefully():
    """If LLM returns invalid JSON, agent should stop cleanly + keep baseline."""
    stub = _make_stub_provider([
        "I'm not following the JSON schema. Here's some prose instead.",
    ])
    result = asyncio.run(classify_agentic(
        str(FIXTURES / "blog_flask"),
        llm_provider=stub,
        confidence_threshold=0.99,  # force loop
    ))
    # Baseline preserved
    assert result.description.app_category == "blog / content platform"
    # Error step recorded
    assert any(s.action == "error" for s in result.steps)


def test_agent_handles_path_traversal_in_tool_args():
    """If the LLM tries to read /etc/passwd or `../../foo`, tools must refuse."""
    stub = _make_stub_provider([
        '{"action": "read_file", "arguments": {"relpath": "../../../../etc/passwd"}, "reasoning": "trying path traversal"}',
        '{"action": "conclude", "arguments": {"category": "unknown", "confidence": 0.1, "features": [], "description": "Could not determine. The structural evidence was thin."}, "reasoning": "no useful evidence"}',
    ])
    result = asyncio.run(classify_agentic(
        str(FIXTURES / "blog_flask"),
        llm_provider=stub,
        confidence_threshold=0.99,
    ))
    # The first observation should be an error about path traversal
    first_tool_step = next(
        s for s in result.steps if s.action == "read_file"
    )
    assert "blocked" in first_tool_step.observation_summary.lower() or "error" in first_tool_step.observation_summary.lower()


def test_agent_to_dict_is_json_serializable():
    """Audit trail + result must round-trip through JSON."""
    import json
    stub = _make_stub_provider([])
    result = asyncio.run(classify_agentic(
        str(FIXTURES / "ecommerce_django"), llm_provider=stub,
    ))
    blob = json.dumps(result.to_dict())
    assert "e-commerce" in blob
    assert "steps" in blob


def test_agent_respects_max_iterations():
    """If LLM keeps calling tools without concluding, agent stops at max."""
    # Stub always returns a tool call — never conclude
    looper = _make_stub_provider([
        '{"action": "list_files", "arguments": {"pattern": "*.py"}, "reasoning": "again"}',
    ] * 10)  # 10 canned tool calls
    result = asyncio.run(classify_agentic(
        str(FIXTURES / "blog_flask"),
        llm_provider=looper,
        confidence_threshold=0.99,
        max_iterations=3,
    ))
    assert result.iterations_used == 3
    # Should hit the exhausted branch
    assert any(s.action == "exhausted" for s in result.steps)
    # Baseline preserved
    assert result.description.app_category == "blog / content platform"
