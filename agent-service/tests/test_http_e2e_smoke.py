from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import http_e2e_smoke


def test_http_e2e_report_schema_with_mocked_services(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(http_e2e_smoke, "_wait_health", lambda url, timeout_seconds: True)

    def fake_post(agent_url, payload):  # noqa: ANN001
        status = "quoted"
        quote_status = "success"
        quote = {"premio_mensal": 209.9}
        if payload["conversation_id"].endswith("incomplete"):
            status = "collecting"
            quote_status = None
            quote = None
        if payload["conversation_id"].endswith("human") or payload["conversation_id"].endswith("media"):
            status = "handoff"
            quote_status = None
            quote = None
        return {
            "http_status": 200,
            "trace_id": f"trace-{payload['conversation_id']}",
            "body": {
                "trace_id": f"trace-{payload['conversation_id']}",
                "status": status,
                "quote_status": quote_status,
                "quote": quote,
                "reply": "ok",
            },
        }

    monkeypatch.setattr(http_e2e_smoke, "_post_chat", fake_post)
    args = argparse.Namespace(
        agent_url="http://127.0.0.1:8010",
        quote_url="http://127.0.0.1:8000",
        output_dir=str(tmp_path),
        start_services=False,
        wait_seconds=0.1,
    )

    code = http_e2e_smoke.run(args)
    report = json.loads((tmp_path / "http_e2e_report.json").read_text(encoding="utf-8"))

    assert code == 0
    assert report["gate"] == "PASS"
    assert len(report["cases"]) == 4
    assert report["trace_ids"]
    assert (tmp_path / "http_e2e_report.html").exists()


def test_http_e2e_skips_clearly_when_services_are_down_without_start_flag(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setattr(http_e2e_smoke, "_wait_health", lambda url, timeout_seconds: False)
    args = argparse.Namespace(
        agent_url="http://127.0.0.1:8010",
        quote_url="http://127.0.0.1:8000",
        output_dir=str(tmp_path),
        start_services=False,
        wait_seconds=0.1,
    )

    code = http_e2e_smoke.run(args)
    report = json.loads((tmp_path / "http_e2e_report.json").read_text(encoding="utf-8"))

    assert code == 0
    assert report["gate"] == "SKIPPED"
    assert "suba quote-service" in report["message"]
