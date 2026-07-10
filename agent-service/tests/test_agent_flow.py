import pytest

from app.agent import AutoSeguroAgent, InMemoryConversationStore
from app.extraction import LeadExtractor
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
                "coberturas": ["colisao", "roubo", "furto", "terceiros", "vidros"],
                "carencia": {"coberturas": ["roubo", "furto"], "dias": 30},
            },
            attempts=[],
        )


class DownQuoteClient:
    async def quote(self, payload):  # noqa: ANN001
        return QuoteResult(status="unavailable", reason="down", attempts=[])


class EstimatedQuoteClient:
    async def quote(self, payload):  # noqa: ANN001
        return QuoteResult(
            status="estimated",
            reason="legacy down",
            quote={
                "plano_nome": "Completo",
                "premio_mensal_estimado": 209.9,
                "premio_mensal_faixa": {"min": 199.4, "max": 220.4},
                "estimated": True,
                "requires_human_validation": True,
            },
            attempts=[],
        )


class StatusQuoteClient:
    def __init__(self, result: QuoteResult) -> None:
        self.result = result

    async def quote(self, payload):  # noqa: ANN001
        return self.result


@pytest.mark.asyncio
async def test_agent_quotes_end_to_end(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle(
        "conv-test",
        "Sou Ana, tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
    )

    assert response.status == "quoted"
    assert response.quote_status == "success"
    assert "R$ 209.90/mes" in response.reply
    assert not response.missing_slots


@pytest.mark.asyncio
async def test_agent_uses_sender_name_metadata(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle(
        "conv-metadata",
        "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
        sender_name="Ana Silva",
    )

    assert response.status == "quoted"
    assert response.state["lead"]["nome"] == "Ana Silva"


@pytest.mark.asyncio
async def test_agent_handoffs_media_by_message_type(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle(
        "conv-media-type",
        "foto do carro",
        sender_name="Ana Silva",
        message_type="image",
    )

    assert response.status == "handoff"
    assert "midia" in response.handoff_reason


@pytest.mark.asyncio
async def test_agent_handoffs_when_legacy_is_down(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=DownQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle(
        "conv-down",
        "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
    )

    assert response.status == "handoff"
    assert response.quote_status == "unavailable"
    assert "legado" in response.handoff_reason
    assert response.handoff_packet
    assert response.handoff_packet["next_best_action"].startswith("Validar")
    assert response.handoff_packet["lead"]["cpf_masked"] is None


@pytest.mark.asyncio
async def test_agent_handoffs_estimated_quote_for_human_validation(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=EstimatedQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle(
        "conv-estimated",
        "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
    )

    assert response.status == "handoff"
    assert response.quote_status == "estimated"
    assert "estimativa preliminar" in response.handoff_reason
    assert response.handoff_packet
    assert response.handoff_packet["quote"]["estimated"] is True
    assert response.handoff_packet["quote"]["requires_human_validation"] is True


@pytest.mark.asyncio
async def test_handoff_is_terminal_and_does_not_reopen_quote_flow(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=DownQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    first = await agent.handle(
        "conv-terminal",
        "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
    )
    second = await agent.handle("conv-terminal", "Tenho mais dados se precisar.")

    assert first.status == "handoff"
    assert second.status == "handoff"
    assert second.handoff_reason == first.handoff_reason
    assert "ja esta encaminhado" in second.reply
    assert second.handoff_packet
    assert second.state["messages"][-2]["redacted_content"] == "Tenho mais dados se precisar."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quote_result",
    [
        QuoteResult(status="unavailable", reason="legacy down", attempts=[]),
        QuoteResult(status="refused", reason="idade fora da regra", attempts=[]),
        QuoteResult(status="invalid", reason="payload invalido", attempts=[]),
        QuoteResult(
            status="estimated",
            reason="legacy down",
            quote={
                "plano_nome": "Completo",
                "premio_mensal_estimado": 209.9,
                "premio_mensal_faixa": {"min": 199.4, "max": 220.4},
                "estimated": True,
                "requires_human_validation": True,
            },
            attempts=[],
        ),
    ],
)
async def test_non_success_quote_status_never_returns_official_price(tmp_path, quote_result) -> None:  # noqa: ANN001
    agent = AutoSeguroAgent(
        quote_client=StatusQuoteClient(quote_result),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle(
        f"conv-{quote_result.status}",
        "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
    )

    assert response.status == "handoff"
    assert response.quote_status == quote_result.status
    assert "R$" not in response.reply
    assert "premio_mensal" not in response.reply.casefold()
    if quote_result.status == "estimated":
        assert response.handoff_packet["quote"]["estimated"] is True
        assert response.handoff_packet["quote"]["requires_human_validation"] is True


@pytest.mark.asyncio
async def test_acceptance_after_quote_goes_to_human_issuance(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    first = await agent.handle(
        "conv-accept",
        "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
    )
    second = await agent.handle("conv-accept", "Fechado, pode emitir")

    assert first.status == "quoted"
    assert second.status == "handoff"
    assert "emissao" in second.handoff_reason
    assert second.handoff_packet["next_best_action"]


@pytest.mark.asyncio
async def test_rejection_after_quote_goes_to_retention_handoff(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    await agent.handle(
        "conv-reject",
        "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero plano completo.",
    )
    response = await agent.handle("conv-reject", "nao precisa, vou ficar com a outra")

    assert response.status == "handoff"
    assert "recusou" in response.handoff_reason


@pytest.mark.asyncio
async def test_agent_defaults_plan_when_only_plan_is_missing(tmp_path) -> None:
    agent = AutoSeguroAgent(
        quote_client=FakeQuoteClient(),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(tmp_path / "events.jsonl"),
        store=InMemoryConversationStore(),
    )

    response = await agent.handle("conv-default-plan", "Tenho 35 anos, CEP 01310-100, Corolla 2022.")

    assert response.status == "quoted"
    assert response.state["lead"]["plano_id"] == "completo"
    assert any(
        "Plano Completo usado como recomendacao padrao" in item
        for item in response.state["lead"]["observacoes"]
    )
