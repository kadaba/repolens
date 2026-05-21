import inspect
from typing import get_type_hints
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app_classifier.llm.provider import LLMProviderProtocol, LLMConfigError
from app_classifier.llm.config import (
    load_provider, _interpolate_env_vars, _autodetect_provider,
)


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


def test_interpolate_env_vars_substitutes():
    with patch.dict(os.environ, {"FOO": "bar"}, clear=False):
        assert _interpolate_env_vars("${FOO}/x") == "bar/x"
        assert _interpolate_env_vars({"key": "${FOO}"}) == {"key": "bar"}
        assert _interpolate_env_vars(["${FOO}", "static"]) == ["bar", "static"]


def test_interpolate_env_vars_raises_on_missing():
    """Missing env var must raise LLMConfigError, not produce empty string."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(LLMConfigError):
            _interpolate_env_vars("${NONEXISTENT_KEY_xyz}")


def test_interpolate_error_never_echoes_env_value():
    """Error messages reveal only the placeholder name, not any expanded value."""
    with patch.dict(os.environ, {"PRESENT": "secret_val"}, clear=True):
        try:
            _interpolate_env_vars("${MISSING_VAR}")
        except LLMConfigError as e:
            assert "MISSING_VAR" in str(e)
            assert "secret_val" not in str(e)


def test_load_provider_explicit_name_from_env(tmp_path):
    """APP_CLASSIFIER_LLM_PROVIDER=openai + OPENAI_API_KEY → OpenAIProvider."""
    env = {
        "APP_CLASSIFIER_LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-test-from-env",
    }
    with patch.dict(os.environ, env, clear=True):
        # Steer config-file lookup at a temp path so it doesn't pick up real file
        with patch("app_classifier.llm.config._config_path", return_value=tmp_path / "nope.json"):
            p = load_provider()
    assert p is not None
    assert p.name == "openai"
    assert p.api_key == "sk-test-from-env"


def test_load_provider_from_json_file(tmp_path):
    cfg = {
        "default": "anthropic",
        "providers": {
            "anthropic": {
                "type": "anthropic",
                "api_key": "${ANTHROPIC_API_KEY}",
                "model": "claude-haiku-4-5-20251001",
            }
        }
    }
    cfg_path = tmp_path / "providers.json"
    cfg_path.write_text(json.dumps(cfg))
    env = {"ANTHROPIC_API_KEY": "sk-ant-from-file"}
    with patch.dict(os.environ, env, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=cfg_path):
            p = load_provider()
    assert p is not None
    assert p.name == "anthropic"
    assert p.api_key == "sk-ant-from-file"
    assert p.model == "claude-haiku-4-5-20251001"


def test_load_provider_env_overrides_file(tmp_path):
    """Env var APP_CLASSIFIER_LLM_PROVIDER picks the provider even if file has a different default."""
    cfg = {
        "default": "anthropic",
        "providers": {
            "anthropic": {"type": "anthropic", "api_key": "x", "model": "m"},
            "openai": {"type": "openai", "api_key": "sk-from-file", "model": "gpt-4o-mini"},
        }
    }
    cfg_path = tmp_path / "providers.json"
    cfg_path.write_text(json.dumps(cfg))
    env = {"APP_CLASSIFIER_LLM_PROVIDER": "openai"}
    with patch.dict(os.environ, env, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=cfg_path):
            p = load_provider()
    assert p.name == "openai"
    assert p.api_key == "sk-from-file"


def test_load_provider_explicit_arg_wins(tmp_path):
    cfg = {"default": "anthropic", "providers": {"anthropic": {"type": "anthropic", "api_key": "x", "model": "m"}, "openai": {"type": "openai", "api_key": "y", "model": "m"}}}
    cfg_path = tmp_path / "providers.json"
    cfg_path.write_text(json.dumps(cfg))
    with patch.dict(os.environ, {"APP_CLASSIFIER_LLM_PROVIDER": "anthropic"}, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=cfg_path):
            p = load_provider(name="openai")
    assert p.name == "openai"


def test_load_provider_returns_none_when_nothing_configured(tmp_path):
    with patch.dict(os.environ, {}, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=tmp_path / "nope.json"):
            assert load_provider() is None


def test_load_provider_autodetect_anthropic_wins_over_openai(tmp_path):
    """Autodetect precedence: ANTHROPIC_API_KEY wins when both are present."""
    env = {"ANTHROPIC_API_KEY": "sk-ant-1", "OPENAI_API_KEY": "sk-openai-1"}
    with patch.dict(os.environ, env, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=tmp_path / "nope.json"):
            p = load_provider()
    assert p is not None
    assert p.name == "anthropic"


def test_load_provider_autodetect_openai_when_anthropic_absent(tmp_path):
    """Autodetect falls through to OpenAI when only OPENAI_API_KEY is set."""
    env = {"OPENAI_API_KEY": "sk-fall-through"}
    with patch.dict(os.environ, env, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=tmp_path / "nope.json"):
            p = load_provider()
    assert p is not None
    assert p.name == "openai"


def test_load_provider_autodetect_ollama_last(tmp_path):
    """Autodetect uses Ollama when only OLLAMA_HOST is set."""
    env = {"OLLAMA_HOST": "http://localhost:11434"}
    with patch.dict(os.environ, env, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=tmp_path / "nope.json"):
            p = load_provider()
    assert p is not None
    assert p.name == "ollama"


def test_load_provider_raises_at_load_time_on_missing_env_var(tmp_path):
    """Spec § Component 1: missing ${VAR} raises LLMConfigError at load time, not call time."""
    cfg = {
        "default": "anthropic",
        "providers": {
            "anthropic": {
                "type": "anthropic",
                "api_key": "${ANTHROPIC_API_KEY_NOT_PRESENT}",
                "model": "claude-haiku-4-5-20251001",
            }
        }
    }
    cfg_path = tmp_path / "providers.json"
    cfg_path.write_text(json.dumps(cfg))
    with patch.dict(os.environ, {}, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=cfg_path):
            with pytest.raises(LLMConfigError) as exc_info:
                load_provider()
    # Error message names the placeholder, no expanded values.
    assert "ANTHROPIC_API_KEY_NOT_PRESENT" in str(exc_info.value)


def test_load_provider_unknown_type_raises(tmp_path):
    cfg = {"default": "x", "providers": {"x": {"type": "made_up", "api_key": "y", "model": "m"}}}
    cfg_path = tmp_path / "providers.json"
    cfg_path.write_text(json.dumps(cfg))
    with patch.dict(os.environ, {"APP_CLASSIFIER_LLM_PROVIDER": "x"}, clear=True):
        with patch("app_classifier.llm.config._config_path", return_value=cfg_path):
            with pytest.raises(LLMConfigError):
                load_provider()
