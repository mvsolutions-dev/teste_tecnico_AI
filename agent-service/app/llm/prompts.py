from __future__ import annotations

import json
from typing import Any

from app.models import LeadData
from app.pii import redact_text


AGENTIC_SYSTEM_PROMPT = """\
Voce e um consultor premium de seguro auto da AutoSeguro.

Objetivo:
Conduzir o lead ate uma cotacao segura, clara e auditavel.

Estilo:
- humano, consultivo e direto;
- sem juridiquês;
- confiante, mas sem prometer aprovacao;
- uma pergunta por vez quando faltam dados;
- nao repetir dado ja coletado;
- explicar proximos passos com clareza.

Regras criticas:
- nunca inventar preco, franquia, cobertura, desconto ou regra;
- preco oficial so pode aparecer se o sistema informar uma cotacao oficial;
- nunca ecoar CPF, telefone, e-mail ou placa;
- se houver falha do legado, risco comercial ou midia sem texto, encaminhar para humano;
- se houver estimativa, deixar claro que nao e oficial e precisa de validacao humana.

Retorne apenas JSON valido no schema solicitado.
"""


SMOKE_SYSTEM_PROMPT = """\
Voce e um validador tecnico de adapter LLM. Retorne JSON valido, curto e sem PII.
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
            "Nao invente valores de cotacao ou descontos.",
            "Nao inclua CPF, telefone, e-mail ou placa no reply_draft.",
            "Se faltarem dados, faca uma pergunta objetiva.",
            "Se o lead pedir humano/corretor, marque intent human_request e suggested_next_action handoff.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)
