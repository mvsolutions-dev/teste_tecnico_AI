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
class DemoTurn:
    message: str
    sender_name: str | None = None
    message_type: str = "text"


@dataclass(frozen=True)
class DemoScenario:
    scenario_id: str
    title: str
    why_it_matters: str
    turns: list[DemoTurn]
    quote_failure_rate: float = 0.0
    quote_timeout_rate: float = 0.0
    expected_final_status: str = "quoted"
    expected_quote_status: str | None = "success"
    expected_handoff_reason_contains: str | None = None


def _demo_scenarios() -> list[DemoScenario]:
    return [
        DemoScenario(
            scenario_id="01_happy_path",
            title="Caminho feliz: cotacao oficial",
            why_it_matters=(
                "Mostra que o agente coleta slots suficientes, monta payload valido e so apresenta "
                "preco depois da regra real de cotacao."
            ),
            turns=[
                DemoTurn(
                    "Oi, sou a Ana. Tenho 35 anos, CPF 389.083.863-43, CEP 01310-100. "
                    "Meu carro e um Corolla 2022 e quero o plano completo com inicio em 2026-07-15.",
                    sender_name="Ana Silva",
                )
            ],
            expected_final_status="quoted",
            expected_quote_status="success",
        ),
        DemoScenario(
            scenario_id="02_legacy_down",
            title="Legado indisponivel: retry e handoff seguro",
            why_it_matters=(
                "O ponto central do desafio e nao travar nem inventar preco quando a API de cotacao falha."
            ),
            turns=[
                DemoTurn(
                    "Tenho 41 anos, CEP 01310-100, carro T-Cross 2021, quero plano premium.",
                    sender_name="Bruno Rocha",
                )
            ],
            quote_failure_rate=1.0,
            expected_final_status="handoff",
            expected_quote_status="unavailable",
            expected_handoff_reason_contains="legado",
        ),
        DemoScenario(
            scenario_id="03_media_handoff",
            title="Midia sem transcricao: passa para humano",
            why_it_matters=(
                "O dataset tem imagem/audio/documento sem transcricao. O agente assume limite do canal e "
                "encaminha em vez de fingir que viu o anexo."
            ),
            turns=[
                DemoTurn("[documento] CNH_frente.pdf", sender_name="Carla Nunes", message_type="document")
            ],
            expected_final_status="handoff",
            expected_quote_status=None,
            expected_handoff_reason_contains="midia",
        ),
        DemoScenario(
            scenario_id="04_post_quote_objection",
            title="Objecao comercial depois da cotacao",
            why_it_matters=(
                "Depois do preco oficial, negociacao e comparacao com concorrente viram trabalho humano."
            ),
            turns=[
                DemoTurn(
                    "Tenho 35 anos, CEP 01310-100, carro Corolla 2022, plano completo.",
                    sender_name="Daniel Costa",
                ),
                DemoTurn("Achei caro, o concorrente me ofereceu menos."),
            ],
            expected_final_status="handoff",
            expected_quote_status="success",
            expected_handoff_reason_contains="objecao",
        ),
    ]


def _validate(scenario: DemoScenario, final: ChatResponse) -> list[str]:
    failures: list[str] = []
    if final.status.value != scenario.expected_final_status:
        failures.append(
            f"status esperado {scenario.expected_final_status}, recebido {final.status.value}"
        )
    if scenario.expected_quote_status is not None and final.quote_status != scenario.expected_quote_status:
        failures.append(
            f"quote_status esperado {scenario.expected_quote_status}, recebido {final.quote_status}"
        )
    if scenario.expected_handoff_reason_contains:
        reason = (final.handoff_reason or "").casefold()
        if scenario.expected_handoff_reason_contains.casefold() not in reason:
            failures.append(
                f"handoff_reason nao contem {scenario.expected_handoff_reason_contains!r}"
            )
    if final.quote_status != "success" and "premio_mensal" in final.reply.casefold():
        failures.append("resposta possivelmente inventou preco sem cotacao oficial")
    return failures


async def _run_one(scenario: DemoScenario, output_dir: Path) -> dict[str, Any]:
    agent = AutoSeguroAgent(
        quote_client=InProcessQuoteClient(
            quote_service_dir=REPO_ROOT / "quote-service",
            failure_rate=scenario.quote_failure_rate,
            timeout_rate=scenario.quote_timeout_rate,
            seed=23,
            max_attempts=2,
        ),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(output_dir / "traces" / f"{scenario.scenario_id}.jsonl"),
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
        "title": scenario.title,
        "why_it_matters": scenario.why_it_matters,
        "passed": not failures,
        "failures": failures,
        "final_status": final.status.value,
        "final_quote_status": final.quote_status,
        "final_handoff_reason": final.handoff_reason,
        "trace_id": final.trace_id,
        "transcript": transcript,
        "handoff_packet": final.handoff_packet,
    }


def _render_html(report: dict[str, Any]) -> str:
    sections = []
    for item in report["scenarios"]:
        transcript = []
        for turn in item["transcript"]:
            transcript.append(
                f"""
                <div class="bubble lead"><span>Lead</span>{html.escape(turn['lead'])}</div>
                <div class="bubble agent"><span>Agente</span>{html.escape(turn['agent'])}</div>
                <div class="badges">
                  <span>Status: {html.escape(str(turn['status']))}</span>
                  <span>Quote: {html.escape(str(turn['quote_status']))}</span>
                  <span>Handoff: {html.escape(str(turn['handoff_reason']))}</span>
                </div>
                """
            )
        status_class = "ok" if item["passed"] else "bad"
        sections.append(
            f"""
            <section class="scenario {status_class}">
              <h2>{html.escape(item['title'])}</h2>
              <p>{html.escape(item['why_it_matters'])}</p>
              <div class="meta">
                <span>Scenario: {html.escape(item['scenario_id'])}</span>
                <span>Trace: {html.escape(item['trace_id'][:8])}</span>
                <span>Gate: {"PASS" if item['passed'] else "FAIL"}</span>
              </div>
              {''.join(transcript)}
              <details>
                <summary>Pacote de handoff / falhas</summary>
                <pre>{html.escape(json.dumps({'failures': item['failures'], 'handoff_packet': item['handoff_packet']}, ensure_ascii=False, indent=2))}</pre>
              </details>
            </section>
            """
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro Demo Walkthrough</title>
  <style>
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; background: #f6f8fb; color: #172033; }}
    header {{ background: #0f172a; color: white; padding: 30px 38px; }}
    header h1 {{ margin: 0 0 8px; }}
    header p {{ margin: 0; color: #cbd5e1; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px; }}
    .scoreboard {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }}
    .metric, .scenario {{ background: white; border: 1px solid #dbe3ef; border-radius: 12px; padding: 16px; }}
    .metric span {{ color: #64748b; font-size: 12px; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 26px; margin-top: 4px; }}
    .scenario {{ margin-bottom: 16px; border-left: 6px solid #64748b; }}
    .scenario.ok {{ border-left-color: #047857; }}
    .scenario.bad {{ border-left-color: #b91c1c; }}
    .meta span, .badges span {{ display: inline-block; background: #eef2f7; border-radius: 999px; padding: 5px 9px; margin: 3px; font-size: 12px; }}
    .bubble {{ border-radius: 10px; padding: 12px; margin: 10px 0; line-height: 1.45; }}
    .bubble span {{ display: block; font-size: 11px; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }}
    .lead {{ background: #ecfdf5; border: 1px solid #a7f3d0; }}
    .agent {{ background: #eff6ff; border: 1px solid #bfdbfe; }}
    pre {{ background: #0f172a; color: #dbeafe; border-radius: 8px; padding: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
  <header>
    <h1>AutoSeguro Demo Walkthrough</h1>
    <p>Quatro conversas curtas demonstrando cotacao, resiliencia, handoff e limite de canal.</p>
  </header>
  <main>
    <div class="scoreboard">
      <div class="metric"><span>Gate</span><strong>{html.escape(report['gate'])}</strong></div>
      <div class="metric"><span>Total</span><strong>{report['total']}</strong></div>
      <div class="metric"><span>Passed</span><strong>{report['passed']}</strong></div>
      <div class="metric"><span>Failed</span><strong>{report['failed']}</strong></div>
    </div>
    {''.join(sections)}
  </main>
</body>
</html>
"""


async def run_demo(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    results = [await _run_one(scenario, output_path) for scenario in _demo_scenarios()]
    passed = sum(1 for item in results if item["passed"])
    report = {
        "gate": "PASS" if passed == len(results) else "FAIL",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "scenarios": results,
    }
    (output_path / "demo_walkthrough.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_path / "demo_walkthrough.html").write_text(_render_html(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build demo walkthrough report")
    parser.add_argument("--output-dir", default="runtime/reports/demo_walkthrough")
    report = asyncio.run(run_demo(parser.parse_args().output_dir))
    print(json.dumps({k: report[k] for k in ["gate", "total", "passed", "failed"]}, ensure_ascii=False, indent=2))
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
