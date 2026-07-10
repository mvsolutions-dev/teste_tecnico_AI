from __future__ import annotations

import argparse
from pathlib import Path

from scripts import smoke_delivery


def test_delivery_report_markdown_marks_failures() -> None:
    report = {
        "gate": "FAIL",
        "mode": "fast",
        "output_dir": "runtime/reports/delivery_smoke",
        "steps": [
            {
                "name": "pytest",
                "command": "python -m pytest",
                "returncode": 1,
                "elapsed_seconds": 1.2,
                "output_tail": "failure",
            }
        ],
        "summary": {"eval_gate": "FAIL"},
    }

    markdown = smoke_delivery._render_markdown(report)

    assert "# AutoSeguro Delivery Smoke" in markdown
    assert "pytest - FAIL" in markdown
    assert "failure" in markdown


def test_delivery_args_defaults_to_fast_mode(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    calls = []

    def fake_run_step(name, command, *, cwd):  # noqa: ANN001
        calls.append((name, command, cwd))
        if name == "eval_suite":
            out_dir = Path(command[command.index("--output-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "eval_suite_report.json").write_text(
                '{"gate":"PASS","total_conversations":250}',
                encoding="utf-8",
            )
        if name == "acceptance_suite":
            out_dir = Path(command[command.index("--output-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "acceptance_report.json").write_text(
                '{"gate":"PASS","total":9,"passed":9,"failed":0}',
                encoding="utf-8",
            )
        if name == "chaos_matrix":
            out_dir = Path(command[command.index("--output-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "chaos_matrix_report.json").write_text(
                '{"gate":"PASS","limit":120}',
                encoding="utf-8",
            )
        if name == "trace_replay":
            json_path = Path(command[command.index("--json-output") + 1])
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                '{"conversation_id":"conv-test","final_status":"quoted","final_quote_status":"success"}',
                encoding="utf-8",
            )
        if name == "demo_walkthrough":
            out_dir = Path(command[command.index("--output-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "demo_walkthrough.json").write_text(
                '{"gate":"PASS","total":4,"passed":4,"failed":0}',
                encoding="utf-8",
            )
        if name == "security_scan":
            out_dir = Path(command[command.index("--output-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "security_scan_report.json").write_text(
                '{"gate":"PASS","scanned_files":10,"failure_count":0,"warning_count":0}',
                encoding="utf-8",
            )
        return {
            "name": name,
            "command": " ".join(command),
            "cwd": str(cwd),
            "returncode": 0,
            "elapsed_seconds": 0.01,
            "output_tail": "ok",
        }

    monkeypatch.setattr(smoke_delivery, "_run_step", fake_run_step)
    args = argparse.Namespace(
        full=False,
        limit=250,
        unstable_limit=80,
        chaos_limit=120,
        trace_scan_limit=10,
        output_dir=str(tmp_path),
        include_llm_judge=False,
        llm_judge_limit=8,
        include_http_e2e=False,
        http_e2e_start_services=False,
    )

    code = smoke_delivery.run(args)

    assert code == 0
    assert [call[0] for call in calls] == [
        "pytest",
        "ruff",
        "dataset_profile",
        "eval_suite",
        "acceptance_suite",
        "chaos_matrix",
        "trace_replay",
        "demo_walkthrough",
        "security_scan",
        "control_tower",
    ]
    assert (tmp_path / "delivery_smoke_report.json").exists()
