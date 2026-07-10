from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import AutoSeguroAgent  # noqa: E402
from app.dataset_loader import load_conversation_rows  # noqa: E402
from app.extraction import LeadExtractor  # noqa: E402
from app.recorder import FlightRecorder  # noqa: E402
from scripts.run_eval_suite import InProcessQuoteClient, NullRecorder  # noqa: E402


def _group_rows(rows: list[dict[str, Any]], limit: int) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["conversation_id"])].append(row)
    return list(grouped.items())[:limit]


async def _run_cell(
    *,
    name: str,
    rows: list[tuple[str, list[dict[str, Any]]]],
    failure_rate: float,
    timeout_rate: float,
    seed: int,
    persist_trace: bool,
    output_dir: Path,
) -> dict[str, Any]:
    recorder = (
        FlightRecorder(output_dir / f"{name}_events.jsonl") if persist_trace else NullRecorder()
    )
    agent = AutoSeguroAgent(
        quote_client=InProcessQuoteClient(
            quote_service_dir=REPO_ROOT / "quote-service",
            failure_rate=failure_rate,
            timeout_rate=timeout_rate,
            seed=seed,
            max_attempts=2,
        ),
        extractor=LeadExtractor(use_llm=False),
        recorder=recorder,
    )
    started = time.perf_counter()
    finals = []
    for cid, messages in rows:
        final = None
        for row in sorted(messages, key=lambda item: int(item["message_index"])):
            if row["sender_role"] != "lead":
                continue
            final = await agent.handle(
                cid,
                str(row["message_body"]),
                sender_name=str(row.get("sender_name") or "") or None,
                message_type=str(row.get("message_type") or "text"),
            )
        if final:
            finals.append(final)
    elapsed = round(time.perf_counter() - started, 3)
    handoff_reasons = Counter(str(item.handoff_reason) for item in finals if item.handoff_reason)
    quote_status = Counter(str(item.quote_status) for item in finals)
    statuses = Counter(item.status.value for item in finals)
    unavailable_not_handoff = [
        item.conversation_id for item in finals if item.quote_status == "unavailable" and item.status.value != "handoff"
    ]
    total_attempts = sum(len(item.quote_attempts) for item in finals)
    return {
        "name": name,
        "failure_rate": failure_rate,
        "timeout_rate": timeout_rate,
        "total": len(finals),
        "elapsed_seconds": elapsed,
        "conversations_per_second": round(len(finals) / elapsed, 2) if elapsed else 0,
        "status": dict(statuses),
        "quote_status": dict(quote_status),
        "handoff_reasons": dict(handoff_reasons),
        "quote_attempts_total": total_attempts,
        "quote_attempts_avg": round(total_attempts / max(1, len(finals)), 2),
        "unavailable_not_handoff": unavailable_not_handoff,
        "gate": "PASS" if not unavailable_not_handoff else "FAIL",
    }


def _render_html(report: dict[str, Any]) -> str:
    rows = []
    for cell in report["matrix"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(cell['name'])}</td>"
            f"<td>{cell['failure_rate']:.0%}</td>"
            f"<td>{cell['timeout_rate']:.0%}</td>"
            f"<td>{cell['total']}</td>"
            f"<td>{cell['conversations_per_second']}</td>"
            f"<td><code>{html.escape(json.dumps(cell['status'], ensure_ascii=False))}</code></td>"
            f"<td><code>{html.escape(json.dumps(cell['quote_status'], ensure_ascii=False))}</code></td>"
            f"<td>{cell['quote_attempts_avg']}</td>"
            f"<td>{html.escape(cell['gate'])}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro Chaos Matrix</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d8dee9; padding: 8px; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    code {{ white-space: pre-wrap; }}
    .ok {{ color: #047857; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>AutoSeguro Chaos Matrix</h1>
  <p>Validacao do comportamento do agente com legado instavel. Gate global:
  <span class="ok">{html.escape(report['gate'])}</span>.</p>
  <table>
    <thead>
      <tr><th>Cenario</th><th>Falha</th><th>Timeout</th><th>Total</th><th>Conv/s</th><th>Status</th><th>Quote status</th><th>Avg attempts</th><th>Gate</th></tr>
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>JSON</h2>
  <pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
</body>
</html>
"""


async def run_matrix(
    *,
    dataset_dir: str | Path,
    output_dir: str | Path,
    limit: int,
    seed: int,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    loaded = load_conversation_rows(dataset_dir)
    rows = _group_rows(loaded.rows, limit)
    configs = [
        ("stable", 0.0, 0.0),
        ("mild_20pct_failure", 0.20, 0.0),
        ("mixed_50pct_failure_5pct_timeout", 0.50, 0.05),
        ("severe_80pct_failure_10pct_timeout", 0.80, 0.10),
    ]
    matrix = [
        await _run_cell(
            name=name,
            rows=rows,
            failure_rate=failure_rate,
            timeout_rate=timeout_rate,
            seed=seed,
            persist_trace=False,
            output_dir=output_path,
        )
        for name, failure_rate, timeout_rate in configs
    ]
    gate = "PASS" if all(item["gate"] == "PASS" for item in matrix) else "FAIL"
    report = {
        "gate": gate,
        "dataset_source": loaded.source,
        "limit": limit,
        "matrix": matrix,
        "business_rule": "quote_status=unavailable deve terminar em handoff, nunca em preco inventado.",
    }
    (output_path / "chaos_matrix_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_path / "chaos_matrix_report.html").write_text(_render_html(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run instability matrix for the quote legacy")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--output-dir", default="runtime/reports/chaos_matrix")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    report = asyncio.run(
        run_matrix(
            dataset_dir=args.dataset_dir,
            output_dir=args.output_dir,
            limit=args.limit,
            seed=args.seed,
        )
    )
    print(json.dumps({k: report[k] for k in ["gate", "limit"]}, ensure_ascii=False, indent=2))
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
