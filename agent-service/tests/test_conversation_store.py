from __future__ import annotations

import sqlite3

from app.models import AgentStatus, ConversationState, LeadData, Message, QuoteResult
from app.pii import redact_text
from app.store import SQLiteConversationStore


def test_sqlite_store_roundtrip_redacted_state(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    store = SQLiteConversationStore(db_path)
    state = ConversationState(
        conversation_id="conv-store",
        status=AgentStatus.HANDOFF,
        lead=LeadData(
            nome="Ana Silva",
            idade=35,
            cpf_masked="***.083.863-**",
            email_masked="an***@email.com",
            telefone_masked="***9999",
            cep="01310-100",
            veiculo_texto="Toyota Corolla 2022",
            veiculo_marca="Toyota",
            veiculo_modelo="Corolla",
            veiculo_ano=2022,
            plano_id="completo",
        ),
        quote_result=QuoteResult(status="unavailable", reason="down", attempts=[]),
        handoff_reason="sistema legado de cotacao indisponivel apos retries",
    )
    raw_message = "CPF 389.083.863-43, telefone 11 99999-9999, email ana@email.com"
    state.messages.append(
        Message(role="lead", content=raw_message, redacted_content=redact_text(raw_message))
    )

    store.save(state)
    loaded = store.get("conv-store")

    assert store.exists("conv-store")
    assert store.count() == 1
    assert loaded.status == AgentStatus.HANDOFF
    assert loaded.lead.veiculo_texto == "Toyota Corolla 2022"
    assert loaded.messages[0].content == loaded.messages[0].redacted_content
    assert loaded.messages[0].content != raw_message

    with sqlite3.connect(db_path) as conn:
        payload = conn.execute("SELECT payload FROM conversations").fetchone()[0]
    assert "389.083.863-43" not in payload
    assert "99999-9999" not in payload
    assert "ana@email.com" not in payload


def test_sqlite_store_list_recent(tmp_path) -> None:
    store = SQLiteConversationStore(tmp_path / "state.db")
    store.save(ConversationState(conversation_id="conv-a"))
    store.save(ConversationState(conversation_id="conv-b"))

    recent = store.list_recent(limit=2)

    assert {item.conversation_id for item in recent} == {"conv-a", "conv-b"}
