from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMProviderError(RuntimeError):
    """Base exception for optional LLM providers."""


class LLMProviderNotConfigured(LLMProviderError):
    """Raised when a real provider is selected without complete env vars."""


class LLMProviderTimeout(LLMProviderError):
    """Raised when a provider call times out."""


class LLMProvider(Protocol):
    name: str

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-compatible dict following the requested schema."""

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float | None = None,
    ) -> str:
        """Return free-form text."""


@dataclass(frozen=True)
class ProviderConfigStatus:
    provider: str
    configured: bool
    model: str | None = None
    reason: str | None = None
