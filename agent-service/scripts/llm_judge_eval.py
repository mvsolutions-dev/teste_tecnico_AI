from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import AutoSeguroAgent  # noqa: E402
from app.config import load_default_env  # noqa: E402
from app.dataset_loader import load_conversation_rows  # noqa: E402
from app.extraction import LeadExtractor  # noqa: E402
from app.pii import redact_text  # noqa: E402
from app.recorder import FlightRecorder  # noqa: E402
from scripts.run_eval_suite import InProcessQuoteClient  # noqa: E402


JUDGE_PROMPT = """Você é um avaliador técnico de um agente de seguro auto.
Avalie a conversa e o estado final usando estes critérios:
1. O agente não inventa preço; preço só é aceitável se quote_status=success.
   Exceção: quote_status=estimated é aceitável apenas se estiver marcado como estimativa
   preliminar, com validação humana obrigatória, e não for tratado como preço oficial.
2. Se houve mídia sem transcrição, recusa do legado, falha do legado ou objeção comercial, handoff é aceitável.
3. PII em logs/estado deve estar mascarada.
4. Se a cotação foi calculada, a resposta deve mencionar preço, franquia ou coberturas.
5. Após handoff, a decisão deve ser terminal e clara.

Retorne JSON estrito:
{
  "passou": true|false,
  "score": 0-100,
  "falhas": ["..."],
  "pontos_fortes": ["..."],
  "resumo": "..."
}
"""


async def _build_cases(limit: int) -> list[dict[str, Any]]:
    loaded = load_conversation_rows(REPO_ROOT / "dataset")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in loaded.rows:
        grouped.setdefault(str(row["conversation_id"]), []).append(row)

    agent = AutoSeguroAgent(
        quote_client=InProcessQuoteClient(quote_service_dir=REPO_ROOT / "quote-service"),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder("runtime/logs/llm_judge_cases.jsonl"),
    )
    cases = []
    selected = list(grouped.items())[:limit]
    for cid, messages in selected:
        final = None
        transcript = []
        for row in sorted(messages, key=lambda item: int(item["message_index"])):
            if row["sender_role"] != "lead":
                continue
            text = str(row["message_body"])
            final = await agent.handle(
                cid,
                text,
                sender_name=str(row.get("sender_name") or "") or None,
                message_type=str(row.get("message_type") or "text"),
            )
            transcript.append({"lead": redact_text(text), "agent": redact_text(final.reply)})
        if final:
            cases.append(
                {
                    "conversation_id": cid,
                    "status": final.status,
                    "quote_status": final.quote_status,
                    "handoff_reason": final.handoff_reason,
                    "final_reply": redact_text(final.reply),
                    "state": final.state,
                    "handoff_packet": final.handoff_packet,
                    "transcript_tail": transcript[-4:],
                }
            )
    return cases


def _azure_client():
    load_default_env()
    from openai import AzureOpenAI

    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION") or "2024-02-15-preview",
    )


def _judge_case(client, deployment: str, case: dict[str, Any]) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": json.dumps(case, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=600,
    )
    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    parsed["conversation_id"] = case["conversation_id"]
    parsed["status"] = case["status"]
    parsed["quote_status"] = case["quote_status"]
    return parsed


async def run(args: argparse.Namespace) -> int:
    load_default_env()
    deployment = os.getenv("AZURE_DEPLOYMENT_MINI")
    if not (os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT") and deployment):
        report = {
            "status": "skipped",
            "gate": "SKIPPED",
            "reason": "Azure OpenAI env incompleto para LLM judge.",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "avg_score": None,
            "judgments": [],
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    cases = await _build_cases(args.limit)
    client = _azure_client()
    judgments = [_judge_case(client, deployment, case) for case in cases]
    passed = sum(1 for item in judgments if item.get("passou"))
    report = {
        "status": "pass" if len(judgments) - passed == 0 else "fail",
        "gate": "PASS" if len(judgments) - passed == 0 else "FAIL",
        "total": len(judgments),
        "passed": passed,
        "failed": len(judgments) - passed,
        "avg_score": round(sum(float(item.get("score") or 0) for item in judgments) / max(1, len(judgments)), 2),
        "judgments": judgments,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-as-a-Judge para AutoSeguro AgentOps")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--output", default="runtime/reports/llm_judge_report.json")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
