from typing import Any

import pytest

from app.agent import AutoSeguroAgent, InMemoryConversationStore
from app.extraction import LeadExtractor
from app.models import QuoteResult
from app.recorder import FlightRecorder


class DangerousReplyProvider:
    name = "fake"

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return {
            "extracted_slots": {"idade": 35, "cep": "01310-100"},
            "intent": "incomplete",
            "commercial_signals": {},
            "suggested_next_action": "ask_missing_slot",
            "reply_draft": "Consigo fazer por R$ 99,90 se voce mandar o carro.",
        }

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: float | None = None,
    ) -> str:
        return "R$ 99,90"


class DownQuoteClient:
    async def quote(self, payload):  # noqa: ANN001
        return QuoteResult(status="unavailable", reason="down", attempts=[])


@pytest.mark.asyncio
async def test_llm_draft_with_invented_price_is_blocked(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=DownQuoteClient(),
        extractor=LeadExtractor(llm_provider=DangerousReplyProvider()),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle("conv-danger", "Tenho 35 anos e CEP 01310-100.")

    assert response.status == "collecting"
    assert "R$" not in response.reply
    assert "Qual é o modelo e ano" in response.reply
