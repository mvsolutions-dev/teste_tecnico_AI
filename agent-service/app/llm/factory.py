from __future__ import annotations

import os

from app.config import load_default_env

from .base import LLMProvider, LLMProviderNotConfigured, ProviderConfigStatus
from .providers import (
    AzureOpenAIProvider,
    DisabledLLMProvider,
    FakeLLMProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
)


ProviderName = str


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def build_llm_provider(provider_name: ProviderName | None = None) -> LLMProvider:
    load_default_env()
    selected = (provider_name or _env("AUTOSEGURO_LLM_PROVIDER", "disabled") or "disabled").lower()
    if selected == "disabled":
        return DisabledLLMProvider()
    if selected == "fake":
        return FakeLLMProvider()
    if selected == "auto":
        for candidate in ("openai_compatible", "azure_openai", "openai"):
            try:
                return build_llm_provider(candidate)
            except LLMProviderNotConfigured:
                continue
        return DisabledLLMProvider()
    if selected in {"azure_foundry", "openai_compatible"}:
        return OpenAICompatibleProvider(
            api_key=_env("OPENAI_COMPATIBLE_API_KEY") or _env("AZURE_FOUNDRY_API_KEY") or "",
            base_url=_env("OPENAI_COMPATIBLE_BASE_URL") or _env("AZURE_FOUNDRY_ENDPOINT"),
            model=_env("OPENAI_COMPATIBLE_MODEL") or _env("AZURE_FOUNDRY_DEPLOYMENT") or "",
        )
    if selected == "azure_openai":
        return AzureOpenAIProvider(
            api_key=_env("AZURE_OPENAI_API_KEY") or "",
            endpoint=_env("AZURE_OPENAI_ENDPOINT") or "",
            deployment=_env("AZURE_OPENAI_DEPLOYMENT") or _env("AZURE_DEPLOYMENT_MINI") or "",
            api_version=_env("AZURE_OPENAI_API_VERSION"),
        )
    if selected == "openai":
        return OpenAIProvider(
            api_key=_env("OPENAI_API_KEY") or "",
            model=_env("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            base_url=_env("OPENAI_BASE_URL") or _env("OPENAI_API_BASE_URL"),
        )
    raise LLMProviderNotConfigured(f"Unknown LLM provider: {selected}")


def provider_config_status() -> list[ProviderConfigStatus]:
    load_default_env()
    return [
        ProviderConfigStatus(provider="disabled", configured=True, model=None),
        ProviderConfigStatus(provider="fake", configured=True, model="fake"),
        ProviderConfigStatus(
            provider="openai",
            configured=bool(_env("OPENAI_API_KEY")),
            model=_env("OPENAI_MODEL", "gpt-4o-mini"),
            reason=None if _env("OPENAI_API_KEY") else "OPENAI_API_KEY missing",
        ),
        ProviderConfigStatus(
            provider="azure_openai",
            configured=bool(
                _env("AZURE_OPENAI_API_KEY")
                and _env("AZURE_OPENAI_ENDPOINT")
                and (_env("AZURE_OPENAI_DEPLOYMENT") or _env("AZURE_DEPLOYMENT_MINI"))
            ),
            model=_env("AZURE_OPENAI_DEPLOYMENT") or _env("AZURE_DEPLOYMENT_MINI"),
            reason=(
                None
                if _env("AZURE_OPENAI_API_KEY")
                and _env("AZURE_OPENAI_ENDPOINT")
                and (_env("AZURE_OPENAI_DEPLOYMENT") or _env("AZURE_DEPLOYMENT_MINI"))
                else "Azure OpenAI key, endpoint or deployment missing"
            ),
        ),
        ProviderConfigStatus(
            provider="openai_compatible",
            configured=bool(
                (_env("OPENAI_COMPATIBLE_API_KEY") or _env("AZURE_FOUNDRY_API_KEY"))
                and (_env("OPENAI_COMPATIBLE_BASE_URL") or _env("AZURE_FOUNDRY_ENDPOINT"))
                and (_env("OPENAI_COMPATIBLE_MODEL") or _env("AZURE_FOUNDRY_DEPLOYMENT"))
            ),
            model=_env("OPENAI_COMPATIBLE_MODEL") or _env("AZURE_FOUNDRY_DEPLOYMENT"),
            reason=(
                None
                if (_env("OPENAI_COMPATIBLE_API_KEY") or _env("AZURE_FOUNDRY_API_KEY"))
                and (_env("OPENAI_COMPATIBLE_BASE_URL") or _env("AZURE_FOUNDRY_ENDPOINT"))
                and (_env("OPENAI_COMPATIBLE_MODEL") or _env("AZURE_FOUNDRY_DEPLOYMENT"))
                else "OpenAI-compatible key, base URL or model missing"
            ),
        ),
    ]
