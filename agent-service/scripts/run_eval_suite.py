from __future__ import annotations

import argparse
import asyncio
import html
import importlib.util
import json
import random
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
from app.models import QuoteAttempt, QuoteResult  # noqa: E402
from app.pii import CPF_RE, EMAIL_RE, PHONE_RE  # noqa: E402
from app.recorder import FlightRecorder  # noqa: E402


class NullRecorder(FlightRecorder):
    def __init__(self) -> None:
        super().__init__(Path("runtime/logs/null.jsonl"))

    def record(self, event_type: str, payload: dict[str, Any]) -> None:
        return None


class InProcessQuoteClient:
    """Executa a cotacao sem HTTP para avaliacao de alto volume.

    A logica de negocio continua vindo de `quote-service/app/quote_logic.py`.
    A instabilidade e simulada no adaptador para testar retries/handoff com seed
    reproduzivel.
    """

    def __init__(
        self,
        *,
        quote_service_dir: Path,
        failure_rate: float = 0.0,
        timeout_rate: float = 0.0,
        seed: int = 7,
        max_attempts: int = 2,
    ) -> None:
        self.failure_rate = failure_rate
        self.timeout_rate = timeout_rate
        self.max_attempts = max_attempts
        self.rng = random.Random(seed)
        self.quote_logic = self._load_quote_logic(quote_service_dir)

    @staticmethod
    def _load_quote_logic(quote_service_dir: Path):
        module_path = quote_service_dir / "app" / "quote_logic.py"
        spec = importlib.util.spec_from_file_location("autoseguro_quote_logic", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Nao consegui carregar quote_logic em {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    async def quote(self, payload: dict[str, Any]) -> QuoteResult:
        attempts: list[QuoteAttempt] = []
        for attempt in range(1, self.max_attempts + 1):
            started = time.perf_counter()
            roll = self.rng.random()
            latency_ms = int((time.perf_counter() - started) * 1000)
            if roll < self.timeout_rate:
                attempts.append(
                    QuoteAttempt(
                        attempt=attempt,
                        status="timeout",
                        latency_ms=latency_ms,
                        error="simulated timeout",
                    )
                )
            elif roll < self.timeout_rate + self.failure_rate:
                attempts.append(
                    QuoteAttempt(
                        attempt=attempt,
                        status="retryable_error",
                        latency_ms=latency_ms,
                        http_status=503,
                        error="simulated upstream_unavailable",
                    )
                )
            else:
                try:
                    return QuoteResult(
                        status="success",
                        quote=self.quote_logic.cotar(payload),
                        attempts=[
                            *attempts,
                            QuoteAttempt(
                                attempt=attempt,
                                status="success",
                                latency_ms=latency_ms,
                                http_status=200,
                            ),
                        ],
                    )
                except self.quote_logic.CotacaoRecusada as exc:
                    return QuoteResult(
                        status="refused",
                        reason=exc.motivo,
                        attempts=[
                            *attempts,
                            QuoteAttempt(
                                attempt=attempt,
                                status="refused",
                                latency_ms=latency_ms,
                                http_status=422,
                                error=exc.motivo,
                            ),
                        ],
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    return QuoteResult(
                        status="invalid",
                        reason=str(exc),
                        attempts=[
                            *attempts,
                            QuoteAttempt(
                                attempt=attempt,
                                status="invalid",
                                latency_ms=latency_ms,
                                http_status=400,
                                error=str(exc),
                            ),
                        ],
                    )
        return QuoteResult(
            status="unavailable",
            reason="Servico de cotacao indisponivel apos tentativas com retry.",
            attempts=attempts,
        )


def _slot_coverage(results: list[dict[str, Any]]) -> dict[str, float]:
    slots = ["nome", "idade", "cep", "veiculo_ano", "plano_id", "data_inicio"]
    coverage = {}
    for slot in slots:
        filled = sum(1 for item in results if item["lead"].get(slot) not in (None, "", [], {}))
        coverage[slot] = round(filled / max(1, len(results)), 4)
    return coverage


def _detect_unredacted_pii(log_path: Path) -> dict[str, int]:
    if not log_path.exists():
        return {"cpf": 0, "email": 0, "phone": 0}
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "cpf": len(CPF_RE.findall(text)),
        "email": len(EMAIL_RE.findall(text)),
        "phone": len(PHONE_RE.findall(text)),
    }


async def run_scenario(
    *,
    name: str,
    rows: list[dict[str, Any]],
    limit: int,
    failure_rate: float,
    timeout_rate: float,
    seed: int,
    output_dir: Path,
    persist_trace: bool,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["conversation_id"])].append(row)

    log_path = output_dir / f"{name}_events.jsonl"
    recorder = FlightRecorder(log_path) if persist_trace else NullRecorder()
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
    results: list[dict[str, Any]] = []
    conversations = list(grouped.items())[:limit]
    for cid, messages in conversations:
        ordered = sorted(messages, key=lambda item: int(item["message_index"]))
        final = None
        for row in ordered:
            if row["sender_role"] != "lead":
                continue
            final = await agent.handle(
                cid,
                str(row["message_body"]),
                sender_name=str(row.get("sender_name") or "") or None,
                message_type=str(row.get("message_type") or "text"),
            )
        if final:
            results.append(
                {
                    "conversation_id": cid,
                    "status": final.status,
                    "quote_status": final.quote_status,
                    "handoff_reason": final.handoff_reason,
                    "missing_slots": final.missing_slots,
                    "lead": final.state.get("lead", {}),
                    "quote_attempt_count": len(final.quote_attempts),
                }
            )

    elapsed = time.perf_counter() - started
    quote_attempts = [item["quote_attempt_count"] for item in results if item["quote_attempt_count"]]
    terminal_violations = [
        item
        for item in results
        if item["handoff_reason"] and item["status"] != "handoff"
    ]
    report = {
        "name": name,
        "total": len(results),
        "elapsed_seconds": round(elapsed, 3),
        "conversations_per_second": round(len(results) / elapsed, 2) if elapsed else 0,
        "status": dict(Counter(item["status"] for item in results)),
        "quote_status": dict(Counter(str(item["quote_status"]) for item in results)),
        "handoff_reasons": dict(
            Counter(str(item["handoff_reason"]) for item in results if item["handoff_reason"])
        ),
        "slot_coverage": _slot_coverage(results),
        "quote_attempts": {
            "min": min(quote_attempts) if quote_attempts else 0,
            "max": max(quote_attempts) if quote_attempts else 0,
            "avg": round(sum(quote_attempts) / len(quote_attempts), 2) if quote_attempts else 0,
        },
        "terminal_handoff_violations": len(terminal_violations),
        "unredacted_pii_in_trace": _detect_unredacted_pii(log_path) if persist_trace else {},
        "samples": results[:5],
    }
    return report


def _render_html(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    scenarios = report["scenarios"]
    rows = []
    for scenario in scenarios:
        rows.append(
            "<tr>"
            f"<td>{html.escape(scenario['name'])}</td>"
            f"<td>{scenario['total']}</td>"
            f"<td>{scenario['elapsed_seconds']}</td>"
            f"<td>{scenario['conversations_per_second']}</td>"
            f"<td><code>{html.escape(json.dumps(scenario['status'], ensure_ascii=False))}</code></td>"
            f"<td><code>{html.escape(json.dumps(scenario['quote_status'], ensure_ascii=False))}</code></td>"
            f"<td>{scenario['terminal_handoff_violations']}</td>"
            "</tr>"
        )
    html_text = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro Eval Suite</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #d8dee9; border-radius: 8px; padding: 12px; background: #f8fafc; }}
    .label {{ color: #596579; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #d8dee9; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; }}
    code {{ white-space: pre-wrap; }}
    .ok {{ color: #087f5b; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>AutoSeguro Eval Suite</h1>
  <p>Dataset: <code>{html.escape(report['dataset_source'])}</code></p>
  <div class="grid">
    <div class="card"><div class="label">Conversas</div><div class="value">{report['total_conversations']}</div></div>
    <div class="card"><div class="label">Mensagens</div><div class="value">{report['total_rows']}</div></div>
    <div class="card"><div class="label">Cenarios</div><div class="value">{len(scenarios)}</div></div>
    <div class="card"><div class="label">Gate</div><div class="value ok">{html.escape(report['gate'])}</div></div>
  </div>
  <h2>Cenarios</h2>
  <table>
    <thead>
      <tr>
        <th>Cenario</th><th>Total</th><th>Segundos</th><th>Conv/s</th>
        <th>Status</th><th>Quote Status</th><th>Violacoes handoff</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <h2>Resumo JSON</h2>
  <pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
</body>
</html>
"""
    output.write_text(html_text, encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    loaded = load_conversation_rows(args.dataset_dir)
    rows = loaded.rows
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = [
        await run_scenario(
            name="stable_full",
            rows=rows,
            limit=args.limit,
            failure_rate=0.0,
            timeout_rate=0.0,
            seed=args.seed,
            output_dir=output_dir,
            persist_trace=args.persist_trace,
        ),
        await run_scenario(
            name="unstable_sample",
            rows=rows,
            limit=min(args.unstable_limit, args.limit),
            failure_rate=args.failure_rate,
            timeout_rate=args.timeout_rate,
            seed=args.seed,
            output_dir=output_dir,
            persist_trace=args.persist_trace,
        ),
    ]
    gate_failures = []
    for scenario in scenarios:
        if scenario["terminal_handoff_violations"]:
            gate_failures.append(f"{scenario['name']}: terminal_handoff_violations")
        pii_counts = scenario.get("unredacted_pii_in_trace") or {}
        if any(pii_counts.values()):
            gate_failures.append(f"{scenario['name']}: unredacted_pii_in_trace={pii_counts}")
    report = {
        "dataset_source": loaded.source,
        "total_rows": len(rows),
        "total_conversations": len({str(row["conversation_id"]) for row in rows}),
        "gate": "PASS" if not gate_failures else "FAIL",
        "gate_failures": gate_failures,
        "scenarios": scenarios,
    }
    json_path = output_dir / "eval_suite_report.json"
    html_path = output_dir / "eval_suite_report.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _render_html(report, html_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not gate_failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval suite in-process AutoSeguro")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--limit", type=int, default=2500)
    parser.add_argument("--unstable-limit", type=int, default=250)
    parser.add_argument("--failure-rate", type=float, default=0.45)
    parser.add_argument("--timeout-rate", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", default="runtime/reports/eval_suite")
    parser.add_argument("--persist-trace", action="store_true")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
