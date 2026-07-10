from __future__ import annotations

import json
from typing import Any

from app.models import LeadData
from app.pii import redact_text


AGENTIC_SYSTEM_PROMPT = """\
Você é um consultor premium de seguro auto da AutoSeguro.

Objetivo:
Conduzir o lead até uma cotação segura, clara e auditável.

Estilo:
- humano, consultivo e direto;
- sem juridiquês;
- confiante, mas sem prometer aprovação;
- uma pergunta por vez quando faltam dados;
- não repetir dado já coletado;
- explicar próximos passos com clareza.

Regras críticas:
- nunca inventar preço, franquia, cobertura, desconto ou regra;
- preço oficial só pode aparecer se o sistema informar uma cotação oficial;
- nunca ecoar CPF, telefone, e-mail ou placa;
- se houver falha do legado, risco comercial ou mídia sem texto, encaminhar para humano;
- se houver estimativa, deixar claro que não é oficial e precisa de validação humana.

Retorne apenas JSON válido no schema solicitado.
"""


SMOKE_SYSTEM_PROMPT = """\
Você é um validador técnico de adapter LLM. Retorne JSON válido, curto e sem PII.
"""


def build_agentic_user_prompt(
    *,
    message: str,
    current: LeadData,
    deterministic_updates: dict[str, Any],
) -> str:
    payload = {
        "lead_message_redacted": redact_text(message),
        "current_lead_redacted": current.model_dump(mode="json", exclude_none=True),
        "deterministic_updates_redacted": {
            key: redact_text(str(value)) if "masked" in key or key in {"cpf", "email", "telefone"} else value
            for key, value in deterministic_updates.items()
        },
        "task": {
            "extract_slots": [
                "nome",
                "idade",
                "cep",
                "veiculo_texto",
                "veiculo_marca",
                "veiculo_modelo",
                "veiculo_ano",
                "plano_id",
                "data_inicio",
            ],
            "classify_intent": [
                "quote_request",
                "human_request",
                "objection",
                "accept",
                "reject",
                "incomplete",
                "media",
                "other",
            ],
            "commercial_signals": [
                "price_objection",
                "competitor_mentioned",
                "urgency",
                "trust_concern",
            ],
        },
        "required_json_shape": {
            "extracted_slots": {
                "nome": None,
                "idade": None,
                "cep": None,
                "veiculo_texto": None,
                "veiculo_marca": None,
                "veiculo_modelo": None,
                "veiculo_ano": None,
                "plano_id": None,
                "data_inicio": None,
            },
            "intent": "quote_request | human_request | objection | accept | reject | incomplete | media | other",
            "commercial_signals": {
                "price_objection": False,
                "competitor_mentioned": False,
                "urgency": False,
                "trust_concern": False,
            },
            "suggested_next_action": "ask_missing_slot | quote | handoff | explain_quote | continue",
            "reply_draft": "",
        },
        "guardrails": [
            "Não invente valores de cotação ou descontos.",
            "Não inclua CPF, telefone, e-mail ou placa no reply_draft.",
            "Se faltarem dados, faça uma pergunta objetiva.",
            "Se o lead pedir humano/corretor, marque intent human_request e suggested_next_action handoff.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)
