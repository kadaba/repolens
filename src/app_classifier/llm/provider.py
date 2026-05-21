"""LLM provider protocol + load_provider() — public surface for v0.5.0.

The new Protocol is named `LLMProviderProtocol` to avoid colliding with the
existing public Callable alias `LLMProvider` in classifier.py (which remains
unchanged for backwards compatibility).
"""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


class LLMConfigError(Exception):
    """Raised when provider configuration is invalid or incomplete."""


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Shape every adapter satisfies.

    Each adapter ALSO aliases `__call__ = complete` so it doubles as a
    `Callable[..., Awaitable[Optional[str]]]` and works wherever the existing
    `LLMProvider` callable type is accepted (e.g., classify_agentic).
    """

    name: str

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 400,
        temperature: float = 0.0,
    ) -> Optional[str]: ...


# `load_provider` is defined in config.py to keep provider.py dependency-light.
# Re-export for callers:
def load_provider(name: Optional[str] = None) -> Optional["LLMProviderProtocol"]:
    """Thin wrapper that delegates to config.load_provider.

    Imported lazily to avoid pulling config.py at protocol-import time.
    """
    from app_classifier.llm.config import load_provider as _impl
    return _impl(name)
