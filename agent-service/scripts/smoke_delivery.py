from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_ROOT.parent


def _run_step(name: str, command: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    elapsed = round(time.perf_counter() - started, 3)
    return {
        "name": name,
        "command": " ".join(command),
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "output_tail": "\n".join(completed.stdout.splitlines()[-80:]),
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AutoSeguro Delivery Smoke",
        "",
        f"- Gate: `{report['gate']}`",
        f"- Mode: `{report['mode']}`",
        f"- Output dir: `{report['output_dir']}`",
        "",
        "## Steps",
        "",
    ]
    for step in report["steps"]:
        status = "PASS" if step["returncode"] == 0 else "FAIL"
        lines.extend(
            [
                f"### {step['name']} - {status}",
                "",
                f"- Command: `{step['command']}`",
                f"- Elapsed: `{step['elapsed_seconds']}s`",
                "",
                "```text",
                step["output_tail"],
                "```",
                "",
            ]
        )
    summary = report.get("summary") or {}
    if summary:
        lines.extend(["## Summary", "", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    output_dir = REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "full" if args.full else "fast"
    eval_limit = 2500 if args.full else args.limit
    unstable_limit = 250 if args.full else min(args.unstable_limit, eval_limit)

    steps = [
        _run_step(
            "pytest",
            [sys.executable, "-m", "pytest", "-q", "--basetemp", ".pytest-tmp"],
            cwd=AGENT_ROOT,
        ),
        _run_step("ruff", [sys.executable, "-m", "ruff", "check", "."], cwd=AGENT_ROOT),
        _run_step(
            "dataset_profile",
            [
                sys.executable,
                "agent-service/scripts/profile_dataset.py",
                "--dataset-dir",
                "dataset",
                "--output",
                str(output_dir / "dataset_profile.json"),
                "--markdown-output",
                str(output_dir / "dataset_profile.md"),
            ],
            cwd=REPO_ROOT,
        ),
        _run_step(
            "eval_suite",
            [
                sys.executable,
                "agent-service/scripts/run_eval_suite.py",
                "--limit",
                str(eval_limit),
                "--unstable-limit",
                str(unstable_limit),
                "--output-dir",
                str(output_dir / "eval_suite"),
            ],
            cwd=REPO_ROOT,
        ),
        _run_step(
            "acceptance_suite",
            [
                sys.executable,
                "agent-service/scripts/run_acceptance_suite.py",
                "--output-dir",
                str(output_dir / "acceptance"),
            ],
            cwd=REPO_ROOT,
        ),
        _run_step(
            "chaos_matrix",
            [
                sys.executable,
                "agent-service/scripts/run_chaos_matrix.py",
                "--dataset-dir",
                "dataset",
                "--limit",
                str(args.chaos_limit if args.full else min(args.chaos_limit, args.limit)),
                "--output-dir",
                str(output_dir / "chaos_matrix"),
            ],
            cwd=REPO_ROOT,
        ),
        _run_step(
            "trace_replay",
            [
                sys.executable,
                "agent-service/scripts/build_trace_replay.py",
                "--dataset-dir",
                "dataset",
                "--scan-limit",
                str(args.trace_scan_limit),
                "--output",
                str(output_dir / "trace_replay.html"),
                "--json-output",
                str(output_dir / "trace_replay.json"),
            ],
            cwd=REPO_ROOT,
        ),
        _run_step(
            "demo_walkthrough",
            [
                sys.executable,
                "agent-service/scripts/demo_walkthrough.py",
                "--output-dir",
                str(output_dir / "demo_walkthrough"),
            ],
            cwd=REPO_ROOT,
        ),
        _run_step(
            "security_scan",
            [
                sys.executable,
                "agent-service/scripts/security_scan.py",
                "--paths",
                str(output_dir),
                "--output-dir",
                str(output_dir / "security_scan"),
            ],
            cwd=REPO_ROOT,
        ),
    ]
    if getattr(args, "include_llm_judge", False):
        steps.append(
            _run_step(
                "llm_judge",
                [
                    sys.executable,
                    "agent-service/scripts/llm_judge_eval.py",
                    "--limit",
                    str(args.llm_judge_limit),
                    "--output",
                    str(output_dir / "llm_judge_report.json"),
                ],
                cwd=REPO_ROOT,
            )
        )
    if getattr(args, "include_http_e2e", False):
        command = [
            sys.executable,
            "agent-service/scripts/http_e2e_smoke.py",
            "--output-dir",
            str(output_dir / "http_e2e"),
        ]
        if args.http_e2e_start_services:
            command.append("--start-services")
        steps.append(_run_step("http_e2e", command, cwd=REPO_ROOT))
    steps.append(
        _run_step(
            "control_tower",
            [
                sys.executable,
                "agent-service/scripts/build_control_tower.py",
                "--profile",
                str(output_dir / "dataset_profile.json"),
                "--eval-report",
                str(output_dir / "eval_suite" / "eval_suite_report.json"),
                "--acceptance-report",
                str(output_dir / "acceptance" / "acceptance_report.json"),
                "--chaos-report",
                str(output_dir / "chaos_matrix" / "chaos_matrix_report.json"),
                "--demo-report",
                str(output_dir / "demo_walkthrough" / "demo_walkthrough.json"),
                "--security-report",
                str(output_dir / "security_scan" / "security_scan_report.json"),
                "--llm-judge",
                str(output_dir / "llm_judge_report.json"),
                "--http-e2e-report",
                str(output_dir / "http_e2e" / "http_e2e_report.json"),
                "--output",
                str(output_dir / "control_tower.html"),
            ],
            cwd=REPO_ROOT,
        )
    )
    failed = [step for step in steps if step["returncode"] != 0]
    eval_report = _load_json(output_dir / "eval_suite" / "eval_suite_report.json")
    trace_report = _load_json(output_dir / "trace_replay.json")
    acceptance_report = _load_json(output_dir / "acceptance" / "acceptance_report.json")
    chaos_report = _load_json(output_dir / "chaos_matrix" / "chaos_matrix_report.json")
    demo_report = _load_json(output_dir / "demo_walkthrough" / "demo_walkthrough.json")
    security_report = _load_json(output_dir / "security_scan" / "security_scan_report.json")
    judge_report = _load_json(output_dir / "llm_judge_report.json")
    http_e2e_report = _load_json(output_dir / "http_e2e" / "http_e2e_report.json")
    optional_gates_ok = True
    if getattr(args, "include_llm_judge", False):
        optional_gates_ok = optional_gates_ok and judge_report.get("gate") in {"PASS", "SKIPPED"}
    if getattr(args, "include_http_e2e", False):
        optional_gates_ok = optional_gates_ok and http_e2e_report.get("gate") == "PASS"
    report = {
        "gate": "PASS"
        if (
            not failed
            and eval_report.get("gate") == "PASS"
            and acceptance_report.get("gate") == "PASS"
            and chaos_report.get("gate") == "PASS"
            and demo_report.get("gate") == "PASS"
            and security_report.get("gate") == "PASS"
            and optional_gates_ok
        )
        else "FAIL",
        "mode": mode,
        "output_dir": str(output_dir),
        "steps": steps,
        "summary": {
            "eval_gate": eval_report.get("gate"),
            "acceptance_gate": acceptance_report.get("gate"),
            "chaos_gate": chaos_report.get("gate"),
            "demo_gate": demo_report.get("gate"),
            "security_gate": security_report.get("gate"),
            "llm_judge_status": judge_report.get("status", "not_requested")
            if getattr(args, "include_llm_judge", False)
            else "not_requested",
            "llm_judge_avg_score": judge_report.get("avg_score"),
            "http_e2e_gate": http_e2e_report.get("gate", "not_requested")
            if getattr(args, "include_http_e2e", False)
            else "not_requested",
            "eval_conversations": eval_report.get("total_conversations"),
            "trace_conversation_id": trace_report.get("conversation_id"),
            "trace_final_status": trace_report.get("final_status"),
            "trace_final_quote_status": trace_report.get("final_quote_status"),
            "artifacts": {
                "control_tower": str(output_dir / "control_tower.html"),
                "trace_replay": str(output_dir / "trace_replay.html"),
                "eval_report": str(output_dir / "eval_suite" / "eval_suite_report.html"),
                "acceptance_report": str(output_dir / "acceptance" / "acceptance_report.html"),
                "chaos_matrix": str(output_dir / "chaos_matrix" / "chaos_matrix_report.html"),
                "demo_walkthrough": str(output_dir / "demo_walkthrough" / "demo_walkthrough.html"),
                "security_scan": str(output_dir / "security_scan" / "security_scan_report.html"),
                "http_e2e": str(output_dir / "http_e2e" / "http_e2e_report.html")
                if getattr(args, "include_http_e2e", False)
                else None,
            },
        },
    }
    json_path = output_dir / "delivery_smoke_report.json"
    md_path = output_dir / "delivery_smoke_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["gate", "mode", "output_dir", "summary"]}, ensure_ascii=False, indent=2))
    return 0 if report["gate"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one-command delivery smoke")
    parser.add_argument("--full", action="store_true", help="Roda dataset completo.")
    parser.add_argument("--limit", type=int, default=250, help="Conversas no modo fast.")
    parser.add_argument("--unstable-limit", type=int, default=80)
    parser.add_argument("--chaos-limit", type=int, default=250)
    parser.add_argument("--trace-scan-limit", type=int, default=80)
    parser.add_argument("--output-dir", default="runtime/reports/delivery_smoke")
    parser.add_argument("--include-llm-judge", action="store_true")
    parser.add_argument("--llm-judge-limit", type=int, default=8)
    parser.add_argument("--include-http-e2e", action="store_true")
    parser.add_argument("--http-e2e-start-services", action="store_true")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
