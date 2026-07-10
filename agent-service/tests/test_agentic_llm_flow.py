import pytest

from app.agent import AutoSeguroAgent, InMemoryConversationStore
from app.extraction import LeadExtractor
from app.llm.providers import FakeLLMProvider
from app.models import QuoteResult
from app.recorder import FlightRecorder


class FakeQuoteClient:
    async def quote(self, payload):  # noqa: ANN001
        return QuoteResult(
            status="success",
            quote={
                "plano_nome": "Completo",
                "premio_mensal": 209.9,
                "franquia": 3000,
                "coberturas": ["colisao", "roubo"],
            },
            attempts=[],
        )


@pytest.mark.asyncio
async def test_fake_llm_provider_improves_missing_slot_reply(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(llm_provider=FakeLLMProvider()),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle("conv-llm", "Tenho 35 anos e CEP 01310-100.")

    assert response.status == "collecting"
    assert "modelo e ano" in response.reply
    assert response.state["lead"]["idade"] == 35
    assert response.state["lead"]["cep"] == "01310-100"


@pytest.mark.asyncio
async def test_fake_llm_provider_detects_human_request(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(llm_provider=FakeLLMProvider()),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle("conv-human-llm", "Quero falar com um especialista.")

    assert response.status == "handoff"
    assert response.handoff_packet
    assert "humano" in response.handoff_reason
