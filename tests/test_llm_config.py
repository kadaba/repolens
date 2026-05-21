import inspect
from typing import get_type_hints

import pytest

from app_classifier.llm.provider import LLMProviderProtocol, LLMConfigError


def test_protocol_has_required_attrs():
    """LLMProviderProtocol must declare name attr + complete() method."""
    assert hasattr(LLMProviderProtocol, "complete")
    annotations = getattr(LLMProviderProtocol, "__annotations__", {})
    assert "name" in annotations


def test_protocol_complete_signature():
    sig = inspect.signature(LLMProviderProtocol.complete)
    params = sig.parameters
    assert "prompt" in params
    assert "max_tokens" in params
    assert "temperature" in params
    assert params["max_tokens"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["temperature"].kind == inspect.Parameter.KEYWORD_ONLY


def test_llm_config_error_is_exception():
    err = LLMConfigError("missing key")
    assert isinstance(err, Exception)
