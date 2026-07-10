from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent import AutoSeguroAgent  # noqa: E402
from app.dataset_loader import load_conversation_rows  # noqa: E402
from app.extraction import LeadExtractor  # noqa: E402
from app.quote_client import QuoteClient  # noqa: E402
from app.recorder import FlightRecorder  # noqa: E402


def _slot_coverage(results: list[dict[str, Any]]) -> dict[str, float]:
    if not results:
        return {}
    slots = ["nome", "idade", "cep", "veiculo_ano", "plano_id", "data_inicio"]
    coverage: dict[str, float] = {}
    for slot in slots:
        filled = sum(1 for item in results if item["lead"].get(slot) not in (None, "", [], {}))
        coverage[slot] = round(filled / len(results), 4)
    return coverage


def _write_markdown_report(report: dict[str, Any], path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AutoSeguro Replay Arena",
        "",
        f"- Dataset: `{report['dataset_source']}`",
        f"- Total de conversas avaliadas: **{report['total']}**",
        f"- Status: `{json.dumps(report['status'], ensure_ascii=False)}`",
        f"- Quote status: `{json.dumps(report['quote_status'], ensure_ascii=False)}`",
        f"- Handoff reasons: `{json.dumps(report['handoff_reasons'], ensure_ascii=False)}`",
        "",
        "## Cobertura de slots",
        "",
    ]
    for slot, value in report["slot_coverage"].items():
        lines.append(f"- `{slot}`: {value:.1%}")
    lines.extend(["", "## Amostras", ""])
    for item in report["samples"]:
        lines.extend(
            [
                f"### {item['conversation_id']}",
                "",
                f"- status: `{item['status']}`",
                f"- quote_status: `{item['quote_status']}`",
                f"- handoff_reason: `{item['handoff_reason']}`",
                f"- missing_slots: `{item['missing_slots']}`",
                "",
            ]
        )
    output.write_text("\n".join(lines), encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    loaded = load_conversation_rows(Path(args.dataset_dir))
    rows = loaded.rows
    if loaded.warning:
        print(f"[arena] {loaded.warning}")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["conversation_id"])].append(row)

    agent = AutoSeguroAgent(
        quote_client=QuoteClient(args.quote_api_url, timeout_seconds=args.timeout, max_attempts=args.max_attempts),
        extractor=LeadExtractor(use_llm=False),
        recorder=FlightRecorder(args.log_path),
    )

    results: list[dict[str, Any]] = []
    for cid, messages in list(grouped.items())[: args.limit]:
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

    counter = Counter(item["status"] for item in results)
    quote_counter = Counter(str(item["quote_status"]) for item in results)
    handoff_reasons = Counter(
        str(item["handoff_reason"]) for item in results if item["handoff_reason"]
    )
    quote_attempts = [item["quote_attempt_count"] for item in results if item["quote_attempt_count"]]
    report = {
        "dataset_source": loaded.source,
        "total": len(results),
        "status": dict(counter),
        "quote_status": dict(quote_counter),
        "handoff_reasons": dict(handoff_reasons),
        "slot_coverage": _slot_coverage(results),
        "quote_attempts": {
            "min": min(quote_attempts) if quote_attempts else 0,
            "max": max(quote_attempts) if quote_attempts else 0,
            "avg": round(sum(quote_attempts) / len(quote_attempts), 2) if quote_attempts else 0,
        },
        "handoffs": [item for item in results if item["status"] == "handoff"][:10],
        "samples": results[: min(5, len(results))],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_output:
        _write_markdown_report(report, args.markdown_output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay Arena AutoSeguro AgentOps")
    parser.add_argument("--dataset-dir", default="dataset")
    parser.add_argument("--quote-api-url", default="http://localhost:8000")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--log-path", default="runtime/logs/arena_conversations.jsonl")
    parser.add_argument("--output", default="runtime/reports/arena_report.json")
    parser.add_argument("--markdown-output", default="")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
