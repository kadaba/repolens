"""Provider config loader — env vars + ~/.app-classifier/providers.json."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from app_classifier.llm.provider import LLMConfigError, LLMProviderProtocol


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ENV_PROVIDER = "APP_CLASSIFIER_LLM_PROVIDER"
_ENV_CONFIG_PATH = "APP_CLASSIFIER_CONFIG"


def _config_path() -> Path:
    """~/.app-classifier/providers.json by default; APP_CLASSIFIER_CONFIG overrides."""
    override = os.environ.get(_ENV_CONFIG_PATH)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".app-classifier" / "providers.json"


def _interpolate_env_vars(value: Any) -> Any:
    """Recursively substitute ${VAR} in strings using os.environ.

    Raises LLMConfigError if a referenced var is missing. Error messages
    contain only the placeholder name, never the value of any other env var.
    """
    if isinstance(value, str):
        def _sub(match: "re.Match[str]") -> str:
            var_name = match.group(1)
            v = os.environ.get(var_name)
            if v is None:
                raise LLMConfigError(
                    f"Config references missing env var: ${{{var_name}}}"
                )
            return v
        return _ENV_VAR_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _interpolate_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env_vars(item) for item in value]
    return value


def _read_config_file() -> Optional[dict]:
    path = _config_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise LLMConfigError(f"Failed to read {path}: {e}")


def _build_provider(provider_type: str, config: dict) -> LLMProviderProtocol:
    """Instantiate the right adapter class from a config dict."""
    interpolated = _interpolate_env_vars(config)
    # Strip the 'type' key from kwargs (it's metadata, not a constructor arg)
    kwargs = {k: v for k, v in interpolated.items() if k != "type"}

    if provider_type == "openai":
        from app_classifier.llm.adapters.openai import OpenAIProvider
        return OpenAIProvider(**kwargs)
    if provider_type == "anthropic":
        from app_classifier.llm.adapters.anthropic import AnthropicProvider
        return AnthropicProvider(**kwargs)
    if provider_type == "openrouter":
        from app_classifier.llm.adapters.openrouter import OpenRouterProvider
        return OpenRouterProvider(**kwargs)
    if provider_type == "ollama":
        from app_classifier.llm.adapters.ollama import OllamaProvider
        return OllamaProvider(**kwargs)
    if provider_type == "openai_compat":
        from app_classifier.llm.adapters.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(**kwargs)
    raise LLMConfigError(f"Unknown provider type: {provider_type}")


def _autodetect_provider() -> Optional[LLMProviderProtocol]:
    """Best-effort: pick a provider from environment hints, no config file.

    Order: ANTHROPIC_API_KEY → OPENAI_API_KEY → OLLAMA_HOST (no reachability check).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        from app_classifier.llm.adapters.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
    if os.environ.get("OPENAI_API_KEY"):
        from app_classifier.llm.adapters.openai import OpenAIProvider
        return OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
    if os.environ.get("OLLAMA_HOST"):
        from app_classifier.llm.adapters.ollama import OllamaProvider
        return OllamaProvider(host=os.environ["OLLAMA_HOST"])
    return None


def load_provider(name: Optional[str] = None) -> Optional[LLMProviderProtocol]:
    """Resolve a provider in precedence order:

    1. Explicit `name` argument
    2. $APP_CLASSIFIER_LLM_PROVIDER env var
    3. ~/.app-classifier/providers.json `default`
    4. Autodetect from common API-key env vars
    5. None — caller must handle gracefully
    """
    cfg = _read_config_file()
    target_name = name or os.environ.get(_ENV_PROVIDER)
    if cfg and not target_name:
        target_name = cfg.get("default")

    if target_name and cfg and target_name in cfg.get("providers", {}):
        entry = cfg["providers"][target_name]
        ptype = entry.get("type")
        if not ptype:
            raise LLMConfigError(f"Provider '{target_name}' missing 'type' field")
        return _build_provider(ptype, entry)

    if target_name:
        # Named provider but no config entry — try env-var autodetect mapped to that name
        if target_name == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            from app_classifier.llm.adapters.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
        if target_name == "openai" and os.environ.get("OPENAI_API_KEY"):
            from app_classifier.llm.adapters.openai import OpenAIProvider
            return OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"])
        if target_name == "openrouter" and os.environ.get("OPENROUTER_API_KEY"):
            from app_classifier.llm.adapters.openrouter import OpenRouterProvider
            return OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"])
        if target_name == "ollama":
            from app_classifier.llm.adapters.ollama import OllamaProvider
            return OllamaProvider(host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
        raise LLMConfigError(f"Provider '{target_name}' not in config and no matching env var")

    return _autodetect_provider()
