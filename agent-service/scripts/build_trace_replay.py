from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import AutoSeguroAgent  # noqa: E402
from app.dataset_loader import load_conversation_rows  # noqa: E402
from app.extraction import LeadExtractor  # noqa: E402
from app.pii import redact_text  # noqa: E402
from app.recorder import FlightRecorder  # noqa: E402
from scripts.run_eval_suite import InProcessQuoteClient  # noqa: E402


def _group_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["conversation_id"])].append(row)
    return grouped


async def _run_conversation(
    *,
    conversation_id: str,
    rows: list[dict[str, Any]],
    recorder_path: Path,
    failure_rate: float,
    timeout_rate: float,
) -> dict[str, Any]:
    agent = AutoSeguroAgent(
        quote_client=InProcessQuoteClient(
            quote_service_dir=REPO_ROOT / "quote-service",
            failure_rate=failure_rate,
            timeout_rate=timeout_rate,
            max_attempts=2,
        ),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(recorder_path),
    )
    turns: list[dict[str, Any]] = []
    final = None
    for row in sorted(rows, key=lambda item: int(item["message_index"])):
        if row["sender_role"] != "lead":
            continue
        lead_text = str(row["message_body"])
        final = await agent.handle(
            conversation_id,
            lead_text,
            sender_name=str(row.get("sender_name") or "") or None,
            message_type=str(row.get("message_type") or "text"),
        )
        turns.append(
            {
                "message_index": int(row["message_index"]),
                "message_type": str(row.get("message_type") or "text"),
                "lead": redact_text(lead_text),
                "agent": redact_text(final.reply),
                "status": final.status.value,
                "missing_slots": final.missing_slots,
                "quote_status": final.quote_status,
                "handoff_reason": final.handoff_reason,
                "quote_attempt_count": len(final.quote_attempts),
                "lead_state": final.state.get("lead", {}),
            }
        )
    if final is None:
        raise RuntimeError(f"Conversa {conversation_id} nao possui mensagens do lead.")
    return {
        "conversation_id": conversation_id,
        "trace_id": final.trace_id,
        "final_status": final.status.value,
        "final_quote_status": final.quote_status,
        "final_handoff_reason": final.handoff_reason,
        "turns": turns,
        "final_state": final.state,
        "handoff_packet": final.handoff_packet,
        "recorder_path": str(recorder_path),
    }


def _score_demo_candidate(report: dict[str, Any]) -> int:
    score = 0
    if report["final_status"] == "quoted":
        score += 20
    if report["final_status"] == "handoff":
        score += 10
    if report.get("handoff_packet"):
        score += 10
    if report["final_quote_status"] == "success":
        score += 20
    score += min(10, len(report["turns"]))
    return score


async def build_replay_report(
    *,
    dataset_dir: str | Path,
    output: str | Path,
    json_output: str | Path,
    conversation_id: str | None = None,
    scan_limit: int = 80,
    failure_rate: float = 0.0,
    timeout_rate: float = 0.0,
) -> dict[str, Any]:
    loaded = load_conversation_rows(dataset_dir)
    grouped = _group_rows(loaded.rows)
    candidates = (
        [(conversation_id, grouped[conversation_id])]
        if conversation_id
        else list(grouped.items())[:scan_limit]
    )
    if not candidates:
        raise RuntimeError("Nenhuma conversa encontrada para trace replay.")

    replay_dir = Path(json_output).parent
    replay_dir.mkdir(parents=True, exist_ok=True)
    best: dict[str, Any] | None = None
    for cid, rows in candidates:
        report = await _run_conversation(
            conversation_id=cid,
            rows=rows,
            recorder_path=replay_dir / f"trace_replay_{cid}.jsonl",
            failure_rate=failure_rate,
            timeout_rate=timeout_rate,
        )
        if best is None or _score_demo_candidate(report) > _score_demo_candidate(best):
            best = report
        if conversation_id or report["final_status"] == "quoted":
            break
    assert best is not None
    best["dataset_source"] = loaded.source
    best["pii_policy"] = "Mensagens e outputs de replay sao redigidos antes de persistir."

    Path(json_output).write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(render_trace_html(best), encoding="utf-8")
    return best


def _render_state_badge(label: str, value: Any) -> str:
    return (
        '<span class="badge">'
        f"<strong>{html.escape(label)}:</strong> {html.escape(str(value))}"
        "</span>"
    )


def render_trace_html(report: dict[str, Any]) -> str:
    turn_cards = []
    for turn in report["turns"]:
        lead_state = {
            k: v for k, v in (turn.get("lead_state") or {}).items() if v not in (None, "", [], {})
        }
        badges = " ".join(
            [
                _render_state_badge("status", turn["status"]),
                _render_state_badge("quote", turn["quote_status"] or "-"),
                _render_state_badge("missing", ", ".join(turn["missing_slots"]) or "-"),
            ]
        )
        turn_cards.append(
            f"""
            <article class="turn">
              <div class="turn-header">Turno {turn['message_index']} · {html.escape(turn['message_type'])}</div>
              <div class="bubble lead"><span>Lead</span>{html.escape(turn['lead'])}</div>
              <div class="bubble agent"><span>Agente</span>{html.escape(turn['agent'])}</div>
              <div class="badges">{badges}</div>
              <details>
                <summary>Estado do lead apos o turno</summary>
                <pre>{html.escape(json.dumps(lead_state, ensure_ascii=False, indent=2))}</pre>
              </details>
            </article>
            """
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro Trace Replay</title>
  <style>
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; background: #f6f8fb; color: #172033; }}
    header {{ background: #0f172a; color: white; padding: 28px 36px; }}
    header h1 {{ margin: 0 0 8px; }}
    header p {{ margin: 0; color: #cbd5e1; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }}
    .metric, .turn {{ background: white; border: 1px solid #dbe3ef; border-radius: 12px; padding: 16px; }}
    .metric-label {{ color: #64748b; font-size: 12px; text-transform: uppercase; }}
    .metric-value {{ font-size: 22px; font-weight: 760; margin-top: 4px; }}
    .turn {{ margin-bottom: 14px; }}
    .turn-header {{ font-weight: 700; margin-bottom: 10px; color: #334155; }}
    .bubble {{ border-radius: 10px; padding: 12px; margin: 8px 0; line-height: 1.45; }}
    .bubble span {{ display: block; font-size: 11px; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }}
    .lead {{ background: #ecfdf5; border: 1px solid #a7f3d0; }}
    .agent {{ background: #eff6ff; border: 1px solid #bfdbfe; }}
    .badge {{ display: inline-block; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 999px; padding: 5px 9px; margin: 2px; font-size: 12px; }}
    pre {{ background: #0f172a; color: #dbeafe; border-radius: 8px; padding: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
  <header>
    <h1>AutoSeguro Trace Replay</h1>
    <p>Replay redigido de uma conversa real do dataset, com estado e decisao por turno.</p>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><div class="metric-label">Conversation</div><div class="metric-value">{html.escape(report['conversation_id'])}</div></div>
      <div class="metric"><div class="metric-label">Trace</div><div class="metric-value">{html.escape(report['trace_id'][:8])}</div></div>
      <div class="metric"><div class="metric-label">Final status</div><div class="metric-value">{html.escape(str(report['final_status']))}</div></div>
      <div class="metric"><div class="metric-label">Quote status</div><div class="metric-value">{html.escape(str(report['final_quote_status']))}</div></div>
    </section>
    {''.join(turn_cards)}
    <section class="turn">
      <div class="turn-header">Handoff packet / estado final</div>
      <pre>{html.escape(json.dumps({'handoff_packet': report.get('handoff_packet'), 'final_state': report.get('final_state')}, ensure_ascii=False, indent=2))}</pre>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build redacted trace replay HTML")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--conversation-id")
    parser.add_argument("--scan-limit", type=int, default=80)
    parser.add_argument("--failure-rate", type=float, default=0.0)
    parser.add_argument("--timeout-rate", type=float, default=0.0)
    parser.add_argument("--output", default="runtime/reports/trace_replay.html")
    parser.add_argument("--json-output", default="runtime/reports/trace_replay.json")
    args = parser.parse_args()
    report = asyncio.run(
        build_replay_report(
            dataset_dir=args.dataset_dir,
            output=args.output,
            json_output=args.json_output,
            conversation_id=args.conversation_id,
            scan_limit=args.scan_limit,
            failure_rate=args.failure_rate,
            timeout_rate=args.timeout_rate,
        )
    )
    print(json.dumps({k: report[k] for k in ["conversation_id", "final_status", "final_quote_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
