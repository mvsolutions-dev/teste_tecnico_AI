from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def _wait_health(url: str, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(f"{url.rstrip('/')}/health", timeout=1.5)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.3)
    return False


def _start_services(agent_url: str, quote_url: str) -> list[subprocess.Popen[str]]:
    agent_port = agent_url.rsplit(":", 1)[-1].strip("/")
    quote_port = quote_url.rsplit(":", 1)[-1].strip("/")
    quote_env = {
        **os.environ,
        "QUOTE_FAILURE_RATE": "0",
        "QUOTE_SLOW_RATE": "0",
        "QUOTE_SEED": "11",
    }
    agent_env = {
        **os.environ,
        "QUOTE_API_URL": quote_url,
        "QUOTE_TIMEOUT_SECONDS": "2",
        "QUOTE_MAX_ATTEMPTS": "2",
        "AUTOSEGURO_STATE_STORE": "memory",
    }
    return [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", quote_port],
            cwd=REPO_ROOT / "quote-service",
            env=quote_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
        ),
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", agent_port],
            cwd=ROOT,
            env=agent_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
        ),
    ]


def _post_chat(agent_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(f"{agent_url.rstrip('/')}/chat", json=payload, timeout=5)
    return {
        "http_status": response.status_code,
        "trace_id": response.headers.get("X-Trace-Id"),
        "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else {},
    }


def _cases() -> list[dict[str, Any]]:
    return [
        {
            "name": "official_quote_happy_path",
            "payload": {
                "conversation_id": "http-e2e-happy",
                "sender_name": "Ana Silva",
                "message": (
                    "Tenho 35 anos, CEP 01310-100, meu carro e um Corolla 2022 "
                    "e quero plano completo."
                ),
            },
            "expected_status": "quoted",
            "expected_quote_status": "success",
            "must_have_trace": True,
            "official_price_allowed": True,
        },
        {
            "name": "incomplete_lead_next_question",
            "payload": {
                "conversation_id": "http-e2e-incomplete",
                "sender_name": "Bruno Rocha",
                "message": "Tenho 35 anos e quero cotar meu seguro.",
            },
            "expected_status": "collecting",
            "expected_quote_status": None,
            "must_have_trace": True,
            "official_price_allowed": False,
        },
        {
            "name": "explicit_human_handoff",
            "payload": {
                "conversation_id": "http-e2e-human",
                "sender_name": "Carla Nunes",
                "message": "Quero falar com um corretor humano.",
            },
            "expected_status": "handoff",
            "expected_quote_status": None,
            "must_have_trace": True,
            "official_price_allowed": False,
        },
        {
            "name": "media_handoff",
            "payload": {
                "conversation_id": "http-e2e-media",
                "sender_name": "Daniel Costa",
                "message": "Segue documento do carro.",
                "message_type": "document",
            },
            "expected_status": "handoff",
            "expected_quote_status": None,
            "must_have_trace": True,
            "official_price_allowed": False,
        },
    ]


def _validate_case(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    body = result.get("body") or {}
    if result["http_status"] != 200:
        failures.append(f"http_status={result['http_status']}")
        return failures
    if case.get("must_have_trace") and not result.get("trace_id"):
        failures.append("missing X-Trace-Id")
    if body.get("trace_id") and result.get("trace_id") != body.get("trace_id"):
        failures.append("trace id header/body mismatch")
    if body.get("status") != case["expected_status"]:
        failures.append(f"expected status {case['expected_status']}, got {body.get('status')}")
    if body.get("quote_status") != case["expected_quote_status"]:
        failures.append(
            f"expected quote_status {case['expected_quote_status']}, got {body.get('quote_status')}"
        )
    reply = str(body.get("reply") or "")
    if not case["official_price_allowed"] and "premio_mensal" in reply.casefold():
        failures.append("official price marker appeared when quote was not successful")
    if body.get("quote") and body.get("quote_status") != "success":
        failures.append("quote payload returned without quote_status=success")
    return failures


def _render_html(report: dict[str, Any]) -> str:
    rows = []
    for case in report["cases"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(case['name'])}</td>"
            f"<td>{'PASS' if case['passed'] else 'FAIL'}</td>"
            f"<td>{html.escape(str(case['status']))}</td>"
            f"<td>{html.escape(str(case['quote_status']))}</td>"
            f"<td>{html.escape(str(case['trace_id']))}</td>"
            f"<td>{html.escape('; '.join(case['failures']))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro HTTP E2E Smoke</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border: 1px solid #d8dee9; padding: 8px; text-align: left; }}
    th {{ background: #f1f5f9; }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 14px; border-radius: 8px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>AutoSeguro HTTP E2E Smoke</h1>
  <p>Gate: <strong>{html.escape(report['gate'])}</strong></p>
  <table>
    <thead><tr><th>Case</th><th>Gate</th><th>Status</th><th>Quote</th><th>Trace</th><th>Failures</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>Report JSON</h2>
  <pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
</body>
</html>
"""


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[str]] = []
    try:
        if args.start_services:
            processes = _start_services(args.agent_url, args.quote_url)
        quote_ok = _wait_health(args.quote_url, args.wait_seconds)
        agent_ok = _wait_health(args.agent_url, args.wait_seconds)
        cases: list[dict[str, Any]] = []
        if quote_ok and agent_ok:
            for case in _cases():
                result = _post_chat(args.agent_url, case["payload"])
                failures = _validate_case(case, result)
                body = result.get("body") or {}
                cases.append(
                    {
                        "name": case["name"],
                        "passed": not failures,
                        "failures": failures,
                        "http_status": result["http_status"],
                        "trace_id": result.get("trace_id"),
                        "status": body.get("status"),
                        "quote_status": body.get("quote_status"),
                        "reply_redacted": body.get("reply"),
                    }
                )
        services_missing_without_start = not args.start_services and not (quote_ok and agent_ok)
        gate = "PASS" if quote_ok and agent_ok and all(c["passed"] for c in cases) else "FAIL"
        if services_missing_without_start:
            gate = "SKIPPED"
        report = {
            "gate": gate,
            "agent_url": args.agent_url,
            "quote_url": args.quote_url,
            "health": {"agent": agent_ok, "quote": quote_ok},
            "cases": cases,
            "trace_ids": [case.get("trace_id") for case in cases if case.get("trace_id")],
            "failures": [case for case in cases if not case["passed"]],
        }
        if not quote_ok or not agent_ok:
            report["message"] = (
                "Servicos indisponiveis. Rode com --start-services ou suba quote-service e "
                "agent-service antes do smoke."
            )
        (output_dir / "http_e2e_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "http_e2e_report.html").write_text(_render_html(report), encoding="utf-8")
        print(json.dumps({k: report[k] for k in ["gate", "health", "trace_ids"]}, ensure_ascii=False, indent=2))
        return 0 if report["gate"] in {"PASS", "SKIPPED"} else 1
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTP E2E smoke for quote-service + agent-service")
    parser.add_argument("--agent-url", default="http://127.0.0.1:8010")
    parser.add_argument("--quote-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", default="runtime/reports/http_e2e")
    parser.add_argument("--start-services", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=12)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
