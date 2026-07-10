from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
import time
from pathlib import Path
from typing import Any

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_ROOT.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import load_default_env  # noqa: E402
from app.llm.base import LLMProviderNotConfigured  # noqa: E402
from app.llm.factory import build_llm_provider, provider_config_status  # noqa: E402
from app.llm.prompts import AGENTIC_SYSTEM_PROMPT, build_agentic_user_prompt  # noqa: E402
from app.llm.schemas import parse_agentic_output  # noqa: E402
from app.models import LeadData  # noqa: E402
from app.pii import redact_text  # noqa: E402


PROVIDERS = ["fake", "openai", "azure_openai", "openai_compatible"]


def _status_map() -> dict[str, dict[str, Any]]:
    return {item.provider: item.__dict__ for item in provider_config_status()}


def _safe_sample(payload: dict[str, Any]) -> dict[str, Any]:
    text = redact_text(json.dumps(payload, ensure_ascii=False))
    return json.loads(text)


async def _run_provider(provider_name: str, timeout_seconds: float) -> dict[str, Any]:
    status_by_provider = _status_map()
    config_status = status_by_provider.get(provider_name, {})
    if provider_name != "fake" and not config_status.get("configured"):
        return {
            "provider": provider_name,
            "model": config_status.get("model"),
            "status": "SKIPPED",
            "reason": config_status.get("reason") or "provider env vars missing",
            "latency_ms": None,
            "schema_valid": False,
            "sample_response": None,
        }
    started = time.perf_counter()
    try:
        provider = build_llm_provider(provider_name)
        raw = await provider.complete_json(
            system_prompt=AGENTIC_SYSTEM_PROMPT,
            user_prompt=build_agentic_user_prompt(
                message="Tenho 35 anos, CEP 01310-100, Corolla 2022 e quero completo.",
                current=LeadData(),
                deterministic_updates={},
            ),
            schema_name="provider_smoke",
            timeout_seconds=timeout_seconds,
        )
        parsed = parse_agentic_output(raw)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider_name,
            "model": getattr(provider, "model", config_status.get("model")),
            "status": "PASS",
            "reason": None,
            "latency_ms": latency_ms,
            "schema_valid": True,
            "sample_response": _safe_sample(parsed.model_dump(mode="json")),
        }
    except LLMProviderNotConfigured as exc:
        return {
            "provider": provider_name,
            "model": config_status.get("model"),
            "status": "SKIPPED",
            "reason": type(exc).__name__,
            "latency_ms": None,
            "schema_valid": False,
            "sample_response": None,
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "provider": provider_name,
            "model": config_status.get("model"),
            "status": "FAIL",
            "reason": type(exc).__name__,
            "latency_ms": latency_ms,
            "schema_valid": False,
            "sample_response": None,
        }


def _render_html(report: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro LLM Provider Smoke</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 14px; border-radius: 8px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>AutoSeguro LLM Provider Smoke</h1>
  <p>Gate: <strong>{html.escape(report["gate"])}</strong></p>
  <pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
</body>
</html>
"""


def _write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "llm_provider_smoke_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "llm_provider_smoke_report.html").write_text(
        _render_html(report),
        encoding="utf-8",
    )


async def run(args: argparse.Namespace) -> int:
    load_default_env()
    if args.list:
        report = {
            "gate": "PASS",
            "providers": [item.__dict__ for item in provider_config_status()],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    providers = PROVIDERS if args.all else [args.provider]
    results = [await _run_provider(provider, args.timeout) for provider in providers]
    fail_count = sum(1 for result in results if result["status"] == "FAIL")
    skip_count = sum(1 for result in results if result["status"] == "SKIPPED")
    gate = "FAIL" if fail_count or (args.fail_on_skip and skip_count) else "PASS"
    report = {
        "gate": gate,
        "providers": results,
        "summary": {"pass": len(results) - fail_count - skip_count, "fail": fail_count, "skipped": skip_count},
        "secrets_policy": "No env values, headers or API keys are printed or persisted.",
    }
    _write_report(report, REPO_ROOT / args.output_dir)
    print(json.dumps({k: report[k] for k in ["gate", "summary", "providers"]}, ensure_ascii=False, indent=2))
    return 0 if gate == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional smoke for LLM providers")
    parser.add_argument("--list", action="store_true", help="List provider config without values.")
    parser.add_argument("--all", action="store_true", help="Test all providers with available envs.")
    parser.add_argument(
        "--provider",
        default="fake",
        choices=PROVIDERS,
        help="Provider to smoke when --all is not used.",
    )
    parser.add_argument("--output-dir", default="runtime/reports/llm_provider_smoke")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--real", action="store_true", help="Documentation flag; real providers still require env vars.")
    parser.add_argument("--fail-on-skip", action="store_true")
    parser.add_argument("--redact-output", action="store_true", default=True)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
