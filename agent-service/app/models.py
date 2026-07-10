from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


PlanId = Literal["essencial", "completo", "premium"]


class AgentStatus(str, Enum):
    COLLECTING = "collecting"
    QUOTING = "quoting"
    QUOTED = "quoted"
    HANDOFF = "handoff"


class Message(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["lead", "agent", "system"]
    content: str
    redacted_content: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LeadData(BaseModel):
    nome: str | None = None
    idade: int | None = None
    cpf_masked: str | None = None
    email_masked: str | None = None
    telefone_masked: str | None = None
    cep: str | None = None
    veiculo_texto: str | None = None
    veiculo_marca: str | None = None
    veiculo_modelo: str | None = None
    veiculo_ano: int | None = None
    plano_id: PlanId | None = None
    data_inicio: str | None = None
    observacoes: list[str] = Field(default_factory=list)

    def quote_payload(self) -> dict[str, Any]:
        if self.idade is None or self.veiculo_ano is None or not self.plano_id:
            raise ValueError("Lead sem dados minimos para cotacao.")
        payload: dict[str, Any] = {
            "plano_id": self.plano_id,
            "idade": self.idade,
            "veiculo_ano": self.veiculo_ano,
            "cep": self.cep,
        }
        if self.data_inicio:
            payload["data_inicio"] = self.data_inicio
        return payload


class QuoteAttempt(BaseModel):
    attempt: int
    status: Literal[
        "success",
        "retryable_error",
        "timeout",
        "refused",
        "invalid",
        "failed",
        "cache_hit",
        "estimate",
    ]
    latency_ms: int
    http_status: int | None = None
    error: str | None = None


class QuoteResult(BaseModel):
    status: Literal["success", "refused", "invalid", "unavailable", "estimated"]
    quote: dict[str, Any] | None = None
    reason: str | None = None
    attempts: list[QuoteAttempt] = Field(default_factory=list)


class ConversationState(BaseModel):
    conversation_id: str
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    status: AgentStatus = AgentStatus.COLLECTING
    lead: LeadData = Field(default_factory=LeadData)
    messages: list[Message] = Field(default_factory=list)
    quote_result: QuoteResult | None = None
    handoff_reason: str | None = None
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def missing_required_slots(self) -> list[str]:
        missing: list[str] = []
        if self.lead.idade is None:
            missing.append("idade")
        if self.lead.veiculo_ano is None:
            missing.append("ano do veiculo")
        if not self.lead.cep:
            missing.append("CEP")
        if not self.lead.plano_id:
            missing.append("plano")
        return missing


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    channel: str = "whatsapp"
    sender_name: str | None = None
    message_type: Literal["text", "image", "audio", "document"] = "text"


class ChatResponse(BaseModel):
    conversation_id: str
    trace_id: str
    status: AgentStatus
    reply: str
    missing_slots: list[str]
    handoff_reason: str | None = None
    quote_status: str | None = None
    quote: dict[str, Any] | None = None
    quote_attempts: list[QuoteAttempt] = Field(default_factory=list)
    handoff_packet: dict[str, Any] | None = None
    state: dict[str, Any]
