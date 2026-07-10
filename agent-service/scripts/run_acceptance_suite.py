from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import AutoSeguroAgent, InMemoryConversationStore  # noqa: E402
from app.extraction import LeadExtractor  # noqa: E402
from app.models import ChatResponse  # noqa: E402
from app.pii import redact_text  # noqa: E402
from app.recorder import FlightRecorder  # noqa: E402
from scripts.run_eval_suite import InProcessQuoteClient  # noqa: E402


@dataclass(frozen=True)
class ScenarioTurn:
    message: str
    sender_name: str | None = None
    message_type: str = "text"


@dataclass(frozen=True)
class AcceptanceScenario:
    scenario_id: str
    description: str
    turns: list[ScenarioTurn]
    quote_failure_rate: float = 0.0
    quote_timeout_rate: float = 0.0
    expected_status: str | None = None
    expected_quote_status: str | None = None
    expected_handoff_reason_contains: str | None = None
    expected_reply_contains: str | None = None


def _scenarios() -> list[AcceptanceScenario]:
    return [
        AcceptanceScenario(
            scenario_id="happy_path_quote",
            description="Lead informa dados minimos e recebe cotacao oficial.",
            turns=[
                ScenarioTurn(
                    "Tenho 35 anos, CPF 389.083.863-43, CEP 01310-100, "
                    "Corolla 2022, quero plano completo com inicio em 2026-07-15.",
                    sender_name="Ana Silva",
                )
            ],
            expected_status="quoted",
            expected_quote_status="success",
            expected_reply_contains="R$",
        ),
        AcceptanceScenario(
            scenario_id="media_goes_to_handoff",
            description="Midia sem transcricao nao deve ser interpretada pelo bot.",
            turns=[ScenarioTurn("[imagem] foto_cnh.jpg", sender_name="Ana Silva", message_type="image")],
            expected_status="handoff",
            expected_handoff_reason_contains="midia",
        ),
        AcceptanceScenario(
            scenario_id="human_request_goes_to_handoff",
            description="Pedido explicito por humano encerra o fluxo automatico.",
            turns=[ScenarioTurn("Pode chamar um corretor humano?", sender_name="Carlos Lima")],
            expected_status="handoff",
            expected_handoff_reason_contains="humano",
        ),
        AcceptanceScenario(
            scenario_id="legacy_down_goes_to_handoff",
            description="Falha persistente do legado vira handoff claro.",
            turns=[
                ScenarioTurn(
                    "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, quero completo.",
                    sender_name="Bruna Costa",
                )
            ],
            quote_failure_rate=1.0,
            expected_status="handoff",
            expected_quote_status="unavailable",
            expected_handoff_reason_contains="legado",
        ),
        AcceptanceScenario(
            scenario_id="age_refused_goes_to_handoff",
            description="Regra de aceite por idade e respeitada.",
            turns=[
                ScenarioTurn(
                    "Tenho 80 anos, CEP 01310-100, carro Corolla 2022, plano completo.",
                    sender_name="Joao Pereira",
                )
            ],
            expected_status="handoff",
            expected_quote_status="refused",
            expected_handoff_reason_contains="idade",
        ),
        AcceptanceScenario(
            scenario_id="old_vehicle_refused_goes_to_handoff",
            description="Veiculo fora da regra de aceite nao gera preco inventado.",
            turns=[
                ScenarioTurn(
                    "Tenho 35 anos, CEP 01310-100, meu carro e um Corsa 2000, quero completo.",
                    sender_name="Marina Alves",
                )
            ],
            expected_status="handoff",
            expected_quote_status="refused",
            expected_handoff_reason_contains="veiculo",
        ),
        AcceptanceScenario(
            scenario_id="post_quote_acceptance_goes_to_issuance",
            description="Aceite depois da cotacao vai para emissao humana.",
            turns=[
                ScenarioTurn(
                    "Tenho 35 anos, CEP 01310-100, Corolla 2022, plano completo.",
                    sender_name="Pedro Santos",
                ),
                ScenarioTurn("Fechado, pode emitir."),
            ],
            expected_status="handoff",
            expected_quote_status="success",
            expected_handoff_reason_contains="emissao",
        ),
        AcceptanceScenario(
            scenario_id="post_quote_objection_goes_to_handoff",
            description="Objecao comercial depois da cotacao nao fica no bot.",
            turns=[
                ScenarioTurn(
                    "Tenho 35 anos, CEP 01310-100, Corolla 2022, plano completo.",
                    sender_name="Bianca Rocha",
                ),
                ScenarioTurn("Achei caro, o concorrente me ofereceu menos."),
            ],
            expected_status="handoff",
            expected_quote_status="success",
            expected_handoff_reason_contains="objecao",
        ),
        AcceptanceScenario(
            scenario_id="incomplete_lead_gets_next_question",
            description="Lead incompleto recebe proxima pergunta objetiva.",
            turns=[ScenarioTurn("Quero cotar meu seguro.", sender_name="Lucas Martins")],
            expected_status="collecting",
            expected_reply_contains="idade",
        ),
    ]


def _validate(scenario: AcceptanceScenario, final: ChatResponse) -> list[str]:
    failures: list[str] = []
    if scenario.expected_status and final.status.value != scenario.expected_status:
        failures.append(f"status esperado {scenario.expected_status}, recebido {final.status.value}")
    if scenario.expected_quote_status and final.quote_status != scenario.expected_quote_status:
        failures.append(
            f"quote_status esperado {scenario.expected_quote_status}, recebido {final.quote_status}"
        )
    if scenario.expected_handoff_reason_contains:
        reason = (final.handoff_reason or "").casefold()
        if scenario.expected_handoff_reason_contains.casefold() not in reason:
            failures.append(
                "handoff_reason nao contem "
                f"{scenario.expected_handoff_reason_contains!r}: {final.handoff_reason!r}"
            )
    if scenario.expected_reply_contains:
        if scenario.expected_reply_contains.casefold() not in final.reply.casefold():
            failures.append(f"reply nao contem {scenario.expected_reply_contains!r}")
    if final.quote_status != "success" and "premio_mensal" in final.reply.casefold():
        failures.append("possivel preco inventado em fluxo sem cotacao oficial")
    return failures


async def _run_one(scenario: AcceptanceScenario, output_dir: Path) -> dict[str, Any]:
    agent = AutoSeguroAgent(
        quote_client=InProcessQuoteClient(
            quote_service_dir=REPO_ROOT / "quote-service",
            failure_rate=scenario.quote_failure_rate,
            timeout_rate=scenario.quote_timeout_rate,
            seed=11,
            max_attempts=2,
        ),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(output_dir / f"{scenario.scenario_id}.jsonl"),
        store=InMemoryConversationStore(),
    )
    transcript = []
    final: ChatResponse | None = None
    for turn in scenario.turns:
        final = await agent.handle(
            scenario.scenario_id,
            turn.message,
            sender_name=turn.sender_name,
            message_type=turn.message_type,
        )
        transcript.append(
            {
                "lead": redact_text(turn.message),
                "agent": redact_text(final.reply),
                "status": final.status.value,
                "quote_status": final.quote_status,
                "handoff_reason": final.handoff_reason,
                "missing_slots": final.missing_slots,
            }
        )
    if final is None:
        raise RuntimeError(f"Cenario sem turnos: {scenario.scenario_id}")
    failures = _validate(scenario, final)
    return {
        "scenario_id": scenario.scenario_id,
        "description": scenario.description,
        "passed": not failures,
        "failures": failures,
        "final_status": final.status.value,
        "final_quote_status": final.quote_status,
        "final_handoff_reason": final.handoff_reason,
        "quote_attempts": [item.model_dump() for item in final.quote_attempts],
        "transcript": transcript,
        "handoff_packet": final.handoff_packet,
    }


def _render_html(report: dict[str, Any]) -> str:
    cards = []
    for item in report["scenarios"]:
        cls = "ok" if item["passed"] else "bad"
        cards.append(
            f"""
            <section class="scenario {cls}">
              <h2>{html.escape(item['scenario_id'])}</h2>
              <p>{html.escape(item['description'])}</p>
              <div class="meta">
                <span>Status: {html.escape(str(item['final_status']))}</span>
                <span>Quote: {html.escape(str(item['final_quote_status']))}</span>
                <span>Handoff: {html.escape(str(item['final_handoff_reason']))}</span>
              </div>
              <pre>{html.escape(json.dumps({'failures': item['failures'], 'transcript': item['transcript']}, ensure_ascii=False, indent=2))}</pre>
            </section>
            """
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro Acceptance Suite</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f6f8fb; color: #172033; margin: 0; }}
    header {{ background: #111827; color: white; padding: 28px 36px; }}
    main {{ padding: 24px 36px; }}
    .summary {{ display: flex; gap: 12px; margin-bottom: 18px; }}
    .metric {{ background: white; border: 1px solid #d8dee9; border-radius: 10px; padding: 14px; min-width: 150px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    .scenario {{ background: white; border: 1px solid #d8dee9; border-left: 6px solid #64748b; border-radius: 10px; padding: 16px; margin: 14px 0; }}
    .scenario.ok {{ border-left-color: #047857; }}
    .scenario.bad {{ border-left-color: #b91c1c; }}
    .meta span {{ display: inline-block; background: #eef2f7; border-radius: 999px; padding: 5px 9px; margin: 3px; font-size: 12px; }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 12px; border-radius: 8px; overflow-x: auto; }}
  </style>
</head>
<body>
  <header>
    <h1>AutoSeguro Acceptance Suite</h1>
    <p>Cenarios de produto alinhados aos criterios explicitos do desafio.</p>
  </header>
  <main>
    <div class="summary">
      <div class="metric">Gate<strong>{html.escape(report['gate'])}</strong></div>
      <div class="metric">Total<strong>{report['total']}</strong></div>
      <div class="metric">Passed<strong>{report['passed']}</strong></div>
      <div class="metric">Failed<strong>{report['failed']}</strong></div>
    </div>
    {''.join(cards)}
  </main>
</body>
</html>
"""


async def run_suite(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    results = [await _run_one(scenario, output_path / "traces") for scenario in _scenarios()]
    passed = sum(1 for item in results if item["passed"])
    report = {
        "gate": "PASS" if passed == len(results) else "FAIL",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "scenarios": results,
    }
    (output_path / "acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_path / "acceptance_report.html").write_text(_render_html(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic acceptance scenarios")
    parser.add_argument("--output-dir", default="runtime/reports/acceptance")
    report = asyncio.run(run_suite(parser.parse_args().output_dir))
    print(json.dumps({k: report[k] for k in ["gate", "total", "passed", "failed"]}, ensure_ascii=False, indent=2))
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
