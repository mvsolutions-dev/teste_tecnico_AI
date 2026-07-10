from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dataset_loader import load_conversation_rows  # noqa: E402
from app.pii import CPF_RE, EMAIL_RE, PHONE_RE  # noqa: E402


CEP_RE = re.compile(r"\b\d{5}-?\d{3}\b")
VEHICLE_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d|2050)\b")
OBJECTION_TERMS = {
    "preco": ["caro", "salgado", "preco", "preço"],
    "franquia": ["franquia"],
    "concorrente": ["concorrente", "porto seguro", "azul seguros", "bradesco", "sulamerica"],
    "pensar": ["preciso pensar", "vou ver"],
}


def _lead_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("sender_role") == "lead"]


def _conversation_lengths(rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, int] = defaultdict(int)
    for row in rows:
        grouped[str(row["conversation_id"])] += 1
    values = sorted(grouped.values())
    if not values:
        return {"min": 0, "p50": 0, "p90": 0, "max": 0}
    return {
        "min": values[0],
        "p50": values[len(values) // 2],
        "p90": values[int(len(values) * 0.9)],
        "max": values[-1],
    }


def build_profile(rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    lead = _lead_rows(rows)
    conversations = {str(row["conversation_id"]) for row in rows}
    outcomes = Counter(
        str(row["conversation_outcome"])
        for row in {row["conversation_id"]: row for row in rows}.values()
    )
    message_types = Counter(str(row["message_type"]) for row in rows)
    lead_texts = "\n".join(str(row.get("message_body") or "") for row in lead)
    objection_counts = {}
    folded = lead_texts.casefold()
    for label, terms in OBJECTION_TERMS.items():
        objection_counts[label] = sum(folded.count(term) for term in terms)
    media_conversations = {
        str(row["conversation_id"])
        for row in lead
        if str(row.get("message_type")) in {"image", "audio", "document"}
    }
    profile = {
        "dataset_source": source,
        "row_count": len(rows),
        "conversation_count": len(conversations),
        "lead_message_count": len(lead),
        "message_type_distribution": dict(message_types),
        "conversation_outcomes": dict(outcomes),
        "conversation_length": _conversation_lengths(rows),
        "media_conversation_rate": round(len(media_conversations) / max(1, len(conversations)), 4),
        "pii_presence_in_lead_messages": {
            "cpf": len(CPF_RE.findall(lead_texts)),
            "email": len(EMAIL_RE.findall(lead_texts)),
            "phone": len(PHONE_RE.findall(lead_texts)),
            "cep": len(CEP_RE.findall(lead_texts)),
            "vehicle_year": len(VEHICLE_YEAR_RE.findall(lead_texts)),
        },
        "objection_mentions": objection_counts,
        "engineering_implications": [
            "mensagens de midia exigem handoff ou canal multimodal; nao ha transcricao no dataset",
            "PII aparece em texto livre; logs e traces precisam mascarar CPF, telefone e e-mail",
            "plano nem sempre aparece na fala do lead; default precisa ser auditavel",
            "objecoes comerciais aparecem depois da cotacao; criterio de handoff deve ser explicito",
            "o parquet pode falhar em pyarrow local; DuckDB e fallback JSONL reduzem atrito de avaliacao",
        ],
    }
    return profile


def write_markdown(profile: dict[str, Any], path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AutoSeguro Dataset Profile",
        "",
        f"- Fonte: `{profile['dataset_source']}`",
        f"- Linhas: **{profile['row_count']}**",
        f"- Conversas: **{profile['conversation_count']}**",
        f"- Mensagens de lead: **{profile['lead_message_count']}**",
        f"- Conversas com midia: **{profile['media_conversation_rate']:.1%}**",
        "",
        "## Distribuicoes",
        "",
        f"- Outcomes: `{json.dumps(profile['conversation_outcomes'], ensure_ascii=False)}`",
        f"- Tipos de mensagem: `{json.dumps(profile['message_type_distribution'], ensure_ascii=False)}`",
        f"- Tamanho das conversas: `{json.dumps(profile['conversation_length'], ensure_ascii=False)}`",
        "",
        "## Presenca de PII e campos de cotacao",
        "",
    ]
    for key, value in profile["pii_presence_in_lead_messages"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Objeções comerciais", ""])
    for key, value in profile["objection_mentions"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Implicações para o agente", ""])
    for item in profile["engineering_implications"]:
        lines.append(f"- {item}")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile do dataset AutoSeguro")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--output", default="runtime/reports/dataset_profile.json")
    parser.add_argument("--markdown-output", default="runtime/reports/dataset_profile.md")
    args = parser.parse_args()

    loaded = load_conversation_rows(args.dataset_dir)
    profile = build_profile(loaded.rows, loaded.source)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(profile, args.markdown_output)
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
