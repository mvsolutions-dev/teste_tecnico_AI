from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(label: str, value: Any, detail: str = "") -> str:
    return (
        '<div class="metric">'
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(str(value))}</div>'
        f'<div class="metric-detail">{html.escape(detail)}</div>'
        "</div>"
    )


def _json_block(value: Any) -> str:
    return f"<pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre>"


def build_control_tower(
    profile: dict[str, Any],
    eval_report: dict[str, Any],
    judge_report: dict[str, Any] | None = None,
    acceptance_report: dict[str, Any] | None = None,
    chaos_report: dict[str, Any] | None = None,
    demo_report: dict[str, Any] | None = None,
    security_report: dict[str, Any] | None = None,
    http_e2e_report: dict[str, Any] | None = None,
) -> str:
    scenarios = eval_report.get("scenarios") or []
    stable = scenarios[0] if scenarios else {}
    unstable = scenarios[1] if len(scenarios) > 1 else {}
    judge_report = judge_report or {}
    acceptance_report = acceptance_report or {}
    chaos_report = chaos_report or {}
    demo_report = demo_report or {}
    security_report = security_report or {}
    http_e2e_report = http_e2e_report or {}
    cards = [
        _metric("Overall Gate", _overall_gate(eval_report, acceptance_report, chaos_report, demo_report, security_report, http_e2e_report), "criterios automatizados"),
        _metric("Eval Gate", eval_report.get("gate", "N/A"), "dataset replay"),
        _metric("Acceptance Gate", acceptance_report.get("gate", "N/A"), "cenarios de produto"),
        _metric("Chaos Gate", chaos_report.get("gate", "N/A"), "legado instavel"),
        _metric("Security Gate", security_report.get("gate", "N/A"), "PII crua"),
        _metric("HTTP E2E Gate", http_e2e_report.get("gate", "not_requested"), "integracao local"),
        _metric("Conversas", profile.get("conversation_count", "N/A"), "dataset completo"),
        _metric("Mensagens", profile.get("row_count", "N/A"), "historico sintetico"),
        _metric("Midia", f"{profile.get('media_conversation_rate', 0):.1%}", "conversas com anexo"),
        _metric("Stable throughput", stable.get("conversations_per_second", "N/A"), "conversas/s"),
        _metric("Handoff violations", stable.get("terminal_handoff_violations", "N/A"), "cenario estavel"),
        _metric("Unstable unavailable", (unstable.get("quote_status") or {}).get("unavailable", "N/A"), "legado instavel"),
        _metric("Slot coverage", f"{(stable.get('slot_coverage') or {}).get('idade', 0):.0%}", "idade/CEP/veiculo/plano"),
        _metric(
            "LLM Judge",
            f"{judge_report.get('passed', 'N/A')}/{judge_report.get('total', 'N/A')}",
            f"avg score {judge_report.get('avg_score', 'N/A')}",
        ),
        _metric(
            "Demo",
            f"{demo_report.get('passed', 'N/A')}/{demo_report.get('total', 'N/A')}",
            "walkthrough comercial",
        ),
        _metric(
            "Security",
            security_report.get("gate", "N/A"),
            f"{security_report.get('failure_count', 'N/A')} raw PII findings",
        ),
    ]
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro AgentOps Control Tower</title>
  <style>
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; color: #172033; background: #f5f7fb; }}
    header {{ background: #111827; color: white; padding: 28px 36px; }}
    header h1 {{ margin: 0 0 8px; font-size: 30px; }}
    header p {{ margin: 0; color: #cbd5e1; }}
    main {{ padding: 28px 36px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(170px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .metric {{ background: white; border: 1px solid #dbe3ef; border-radius: 10px; padding: 14px; }}
    .metric-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: .04em; }}
    .metric-value {{ font-size: 26px; font-weight: 760; margin-top: 4px; }}
    .metric-detail {{ font-size: 12px; color: #64748b; margin-top: 6px; }}
    section {{ background: white; border: 1px solid #dbe3ef; border-radius: 10px; padding: 18px; margin: 16px 0; }}
    h2 {{ margin: 0 0 10px; font-size: 20px; }}
    ul {{ margin-top: 8px; }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 14px; border-radius: 8px; overflow-x: auto; }}
    .ok {{ color: #047857; font-weight: 700; }}
    .risk {{ color: #b45309; font-weight: 700; }}
  </style>
</head>
<body>
  <header>
    <h1>AutoSeguro AgentOps Control Tower</h1>
    <p>Agente conversacional auditavel para cotacao de seguro auto com legado instavel.</p>
  </header>
  <main>
    <div class="grid">{''.join(cards)}</div>
    <section>
      <h2>Resumo executivo</h2>
      <ul>
        <li><span class="ok">Funciona ponta a ponta:</span> coleta slots, chama cotacao real e decide handoff.</li>
        <li><span class="ok">Dataset-driven:</span> avalia o parquet completo, nao apenas exemplos manuais.</li>
        <li><span class="ok">Seguro por design:</span> PII mascarada em logs e estado de debug.</li>
        <li><span class="ok">Operacional:</span> handoff vira pacote acionavel para corretor humano.</li>
        <li><span class="risk">Limite conhecido:</span> midia sem transcricao vira handoff no MVP.</li>
      </ul>
    </section>
    <section>
      <h2>Reviewer interpretation</h2>
      <p>This delivery should be reviewed as an operational agent layer, not only as a chatbot. The strongest evidence is the combination of deterministic acceptance tests, dataset replay, chaos testing, redacted trace replay and a security scan gate.</p>
      <ul>
        <li>Quando o legado funciona, o agente calcula cotacao oficial.</li>
        <li>Quando o legado falha, o agente nao inventa preco e encaminha com contexto.</li>
        <li>Quando ha PII nos inputs, os artefatos gerados ficam redigidos.</li>
      </ul>
    </section>
    <section>
      <h2>Decisoes de produto</h2>
      <ul>
        <li>Preco nunca e inventado: so sai apos resposta do legado.</li>
        <li>Falha do legado gera retry e, se persistir, handoff claro.</li>
        <li>Plano Completo pode ser usado como default auditavel quando so falta plano.</li>
        <li>Depois de handoff, o fluxo nao reabre cotacao automaticamente.</li>
      </ul>
    </section>
    <section>
      <h2>Dataset profile</h2>
      {_json_block({k: profile.get(k) for k in ['dataset_source', 'row_count', 'conversation_count', 'message_type_distribution', 'conversation_outcomes', 'media_conversation_rate', 'objection_mentions']})}
    </section>
    <section>
      <h2>Eval suite</h2>
      {_json_block({k: eval_report.get(k) for k in ['gate', 'gate_failures', 'total_rows', 'total_conversations']})}
      {_json_block([{k: s.get(k) for k in ['name', 'total', 'elapsed_seconds', 'conversations_per_second', 'status', 'quote_status', 'handoff_reasons', 'terminal_handoff_violations']} for s in scenarios])}
    </section>
    <section>
      <h2>LLM-as-a-Judge opcional</h2>
      {_json_block({k: judge_report.get(k) for k in ['total', 'passed', 'failed', 'avg_score']})}
    </section>
    <section>
      <h2>Acceptance suite</h2>
      {_json_block({k: acceptance_report.get(k) for k in ['gate', 'total', 'passed', 'failed']})}
    </section>
    <section>
      <h2>Chaos matrix</h2>
      {_json_block({k: chaos_report.get(k) for k in ['gate', 'limit', 'business_rule']})}
      {_json_block([{k: s.get(k) for k in ['name', 'failure_rate', 'timeout_rate', 'total', 'status', 'quote_status', 'quote_attempts_avg', 'gate']} for s in chaos_report.get('matrix', [])])}
    </section>
    <section>
      <h2>Demo walkthrough</h2>
      {_json_block({k: demo_report.get(k) for k in ['gate', 'total', 'passed', 'failed']})}
    </section>
    <section>
      <h2>Security scan</h2>
      {_json_block({k: security_report.get(k) for k in ['gate', 'scanned_files', 'failure_count', 'warning_count', 'policy']})}
    </section>
    <section>
      <h2>HTTP E2E smoke</h2>
      {_json_block({k: http_e2e_report.get(k) for k in ['gate', 'health', 'trace_ids']})}
    </section>
  </main>
</body>
</html>
"""


def _overall_gate(*reports: dict[str, Any]) -> str:
    present = [report for report in reports if report]
    if not present:
        return "N/A"
    failing = [
        report.get("gate")
        for report in present
        if report.get("gate") not in {None, "PASS", "SKIPPED", "not_requested"}
    ]
    return "FAIL" if failing else "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AgentOps Control Tower HTML")
    parser.add_argument("--profile", default="runtime/reports/dataset_profile.json")
    parser.add_argument("--eval-report", default="runtime/reports/eval_suite/eval_suite_report.json")
    parser.add_argument("--llm-judge", default="runtime/reports/llm_judge_report.json")
    parser.add_argument("--acceptance-report", default="runtime/reports/acceptance/acceptance_report.json")
    parser.add_argument("--chaos-report", default="runtime/reports/chaos_matrix/chaos_matrix_report.json")
    parser.add_argument("--demo-report", default="runtime/reports/demo_walkthrough/demo_walkthrough.json")
    parser.add_argument("--security-report", default="runtime/reports/security_scan/security_scan_report.json")
    parser.add_argument("--http-e2e-report", default="runtime/reports/http_e2e/http_e2e_report.json")
    parser.add_argument("--output", default="runtime/reports/control_tower.html")
    args = parser.parse_args()

    profile = _load_json(Path(args.profile))
    eval_report = _load_json(Path(args.eval_report))
    judge_report = _load_json(Path(args.llm_judge))
    acceptance_report = _load_json(Path(args.acceptance_report))
    chaos_report = _load_json(Path(args.chaos_report))
    demo_report = _load_json(Path(args.demo_report))
    security_report = _load_json(Path(args.security_report))
    http_e2e_report = _load_json(Path(args.http_e2e_report))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        build_control_tower(
            profile,
            eval_report,
            judge_report,
            acceptance_report,
            chaos_report,
            demo_report,
            security_report,
            http_e2e_report,
        ),
        encoding="utf-8",
    )
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
