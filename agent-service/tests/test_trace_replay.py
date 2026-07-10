from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_trace_replay import build_replay_report


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_trace_replay_generates_redacted_artifacts(tmp_path: Path) -> None:
    json_output = tmp_path / "trace.json"
    html_output = tmp_path / "trace.html"

    report = await build_replay_report(
        dataset_dir=REPO_ROOT / "dataset",
        output=html_output,
        json_output=json_output,
        scan_limit=4,
    )

    assert json_output.exists()
    assert html_output.exists()
    assert report["turns"]
    assert report["final_status"] in {"collecting", "quoted", "handoff"}
    html = html_output.read_text(encoding="utf-8")
    assert "AutoSeguro Trace Replay" in html
    assert "Lead" in html
    assert "Agente" in html
    assert "389.083.863-43" not in html
