from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


Intent = Literal[
    "quote_request",
    "human_request",
    "objection",
    "accept",
    "reject",
    "incomplete",
    "media",
    "other",
]

SuggestedNextAction = Literal[
    "ask_missing_slot",
    "quote",
    "handoff",
    "explain_quote",
    "continue",
]


class AgenticExtractedSlots(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nome: str | None = None
    idade: int | None = None
    cep: str | None = None
    veiculo_texto: str | None = None
    veiculo_marca: str | None = None
    veiculo_modelo: str | None = None
    veiculo_ano: int | None = None
    plano_id: Literal["essencial", "completo", "premium"] | None = None
    data_inicio: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_plan_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("plano_id") and data.get("plano"):
            data = dict(data)
            data["plano_id"] = data["plano"]
        return data

    @field_validator("nome", "cep", "veiculo_texto", "veiculo_marca", "veiculo_modelo", "data_inicio")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CommercialSignals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price_objection: bool = False
    competitor_mentioned: bool = False
    urgency: bool = False
    trust_concern: bool = False


class AgenticLLMOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    extracted_slots: AgenticExtractedSlots = Field(default_factory=AgenticExtractedSlots)
    intent: Intent = "other"
    commercial_signals: CommercialSignals = Field(default_factory=CommercialSignals)
    suggested_next_action: SuggestedNextAction = "continue"
    reply_draft: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "slots" in normalized and "extracted_slots" not in normalized:
            normalized["extracted_slots"] = normalized["slots"]
        if "suggested_action" in normalized and "suggested_next_action" not in normalized:
            normalized["suggested_next_action"] = normalized["suggested_action"]
        return normalized

    @field_validator("reply_draft")
    @classmethod
    def compact_reply(cls, value: str) -> str:
        return " ".join((value or "").split())[:600]


def parse_agentic_output(payload: dict[str, Any]) -> AgenticLLMOutput:
    try:
        return AgenticLLMOutput.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("invalid_agentic_llm_output") from exc


def llm_output_to_updates(output: AgenticLLMOutput, deterministic: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "nome",
        "idade",
        "cep",
        "veiculo_texto",
        "veiculo_marca",
        "veiculo_modelo",
        "veiculo_ano",
        "plano_id",
        "data_inicio",
    }
    raw_slots = output.extracted_slots.model_dump(exclude_none=True)
    updates: dict[str, Any] = {}
    for key in allowed:
        value = raw_slots.get(key)
        if value in (None, "", [], {}):
            continue
        if key in deterministic:
            continue
        updates[key] = value
    return updates
