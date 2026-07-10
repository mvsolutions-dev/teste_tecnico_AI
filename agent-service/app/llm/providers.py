from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from .base import LLMProviderError, LLMProviderNotConfigured, LLMProviderTimeout


def _loads_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("provider returned non-object JSON")
    return parsed


class DisabledLLMProvider:
    name = "disabled"

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        raise LLMProviderNotConfigured("LLM provider is disabled")

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float | None = None,
    ) -> str:
        raise LLMProviderNotConfigured("LLM provider is disabled")


class FakeLLMProvider:
    """Deterministic test double that behaves like the agentic contract."""

    name = "fake"

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        await asyncio.sleep(0)
        if schema_name == "provider_smoke":
            return {
                "extracted_slots": {"idade": 35, "cep": "01310-100"},
                "intent": "quote_request",
                "commercial_signals": {},
                "suggested_next_action": "continue",
                "reply_draft": "Adapter validado sem dados sensíveis.",
            }
        payload = _extract_prompt_payload(user_prompt)
        message = str(payload.get("lead_message_redacted") or payload.get("message") or user_prompt)
        folded = message.casefold()
        slots: dict[str, Any] = {}
        if match := re.search(r"\b(\d{2,3})\s*anos?\b", message, flags=re.IGNORECASE):
            slots["idade"] = int(match.group(1))
        if match := re.search(r"\b\d{5}-?\d{3}\b", message):
            slots["cep"] = match.group(0)
        if match := re.search(r"\b(19[5-9]\d|20[0-4]\d|2050)\b", message):
            year = int(match.group(1))
            slots["veiculo_ano"] = year
            if "corolla" in folded:
                slots.update(
                    {
                        "veiculo_texto": f"Toyota Corolla {year}",
                        "veiculo_marca": "Toyota",
                        "veiculo_modelo": "Corolla",
                    }
                )
            elif "onix" in folded:
                slots.update(
                    {
                        "veiculo_texto": f"Chevrolet Onix {year}",
                        "veiculo_marca": "Chevrolet",
                        "veiculo_modelo": "Onix",
                    }
                )
        if "premium" in folded:
            slots["plano_id"] = "premium"
        elif "completo" in folded or "vidros" in folded:
            slots["plano_id"] = "completo"
        elif "essencial" in folded or "basico" in folded or "básico" in folded:
            slots["plano_id"] = "essencial"

        intent = "quote_request"
        action = "continue"
        signals = {
            "price_objection": any(term in folded for term in ("caro", "desconto", "preco", "preço")),
            "competitor_mentioned": "concorrente" in folded or "outra seguradora" in folded,
            "urgency": any(term in folded for term in ("hoje", "urgente", "agora")),
            "trust_concern": any(term in folded for term in ("confiavel", "confiável", "golpe")),
        }
        if any(term in folded for term in ("humano", "corretor", "atendente", "especialista")):
            intent = "human_request"
            action = "handoff"
            reply = "Posso chamar um especialista humano e manter tudo que já coletamos no contexto."
        elif signals["price_objection"] or signals["competitor_mentioned"]:
            intent = "objection"
            action = "explain_quote"
            reply = "Entendi a preocupação. Posso revisar cobertura e franquia com você sem inventar desconto."
        elif not slots.get("veiculo_ano"):
            intent = "incomplete"
            action = "ask_missing_slot"
            reply = "Consigo seguir. Para calcular com segurança, me diga o modelo e ano do veículo."
        else:
            reply = "Perfeito, já tenho os principais dados para seguir com uma cotação segura."

        return {
            "extracted_slots": slots,
            "intent": intent,
            "commercial_signals": signals,
            "suggested_next_action": action,
            "reply_draft": reply,
        }

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float | None = None,
    ) -> str:
        await asyncio.sleep(0)
        return "Resposta revisada em tom consultivo, sem dados sensíveis."


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str, model: str, base_url: str | None = None) -> None:
        if not api_key or not model:
            raise LLMProviderNotConfigured("OPENAI_API_KEY and OPENAI_MODEL are required")
        self.model = model
        self.base_url = base_url
        self._api_key = api_key

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        text = await self._chat(system_prompt, user_prompt, response_format={"type": "json_object"}, timeout_seconds=timeout_seconds)
        return _loads_json_object(text)

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float | None = None,
    ) -> str:
        return await self._chat(system_prompt, user_prompt, response_format=None, timeout_seconds=timeout_seconds)

    async def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_format: dict[str, str] | None,
        timeout_seconds: float | None,
    ) -> str:
        try:
            from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

            client = AsyncOpenAI(api_key=self._api_key, base_url=self.base_url or None)
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
            }
            if response_format:
                kwargs["response_format"] = response_format
            if timeout_seconds:
                kwargs["timeout"] = timeout_seconds
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or "{}"
        except (APITimeoutError, TimeoutError) as exc:
            raise LLMProviderTimeout(type(exc).__name__) from exc
        except (APIConnectionError, RateLimitError) as exc:
            raise LLMProviderError(type(exc).__name__) from exc


class AzureOpenAIProvider:
    name = "azure_openai"

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str | None = None,
    ) -> None:
        if not api_key or not endpoint or not deployment:
            raise LLMProviderNotConfigured(
                "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT are required"
            )
        self.model = deployment
        self.endpoint = endpoint.rstrip("/")
        self.api_version = api_version or "2024-02-15-preview"
        self._api_key = api_key

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        text = await self._chat(system_prompt, user_prompt, response_format={"type": "json_object"}, timeout_seconds=timeout_seconds)
        return _loads_json_object(text)

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float | None = None,
    ) -> str:
        return await self._chat(system_prompt, user_prompt, response_format=None, timeout_seconds=timeout_seconds)

    async def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_format: dict[str, str] | None,
        timeout_seconds: float | None,
    ) -> str:
        try:
            from openai import APIConnectionError, APITimeoutError, AsyncAzureOpenAI, AsyncOpenAI, RateLimitError

            if self.endpoint.endswith("/openai/v1"):
                client: Any = AsyncOpenAI(api_key=self._api_key, base_url=self.endpoint)
            else:
                client = AsyncAzureOpenAI(
                    api_key=self._api_key,
                    azure_endpoint=self.endpoint,
                    api_version=self.api_version,
                )
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
            }
            if response_format:
                kwargs["response_format"] = response_format
            if timeout_seconds:
                kwargs["timeout"] = timeout_seconds
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content or "{}"
        except (APITimeoutError, TimeoutError) as exc:
            raise LLMProviderTimeout(type(exc).__name__) from exc
        except (APIConnectionError, RateLimitError) as exc:
            raise LLMProviderError(type(exc).__name__) from exc


class OpenAICompatibleProvider(OpenAIProvider):
    name = "openai_compatible"


def _extract_prompt_payload(user_prompt: str) -> dict[str, Any]:
    try:
        parsed = json.loads(user_prompt)
    except json.JSONDecodeError:
        return {"message": user_prompt}
    return parsed if isinstance(parsed, dict) else {"message": user_prompt}


async def timed_complete_json(provider: Any, **kwargs: Any) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    result = await provider.complete_json(**kwargs)
    return result, int((time.perf_counter() - started) * 1000)
