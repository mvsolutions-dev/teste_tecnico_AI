from __future__ import annotations

from pathlib import Path

import pytest

from scripts.demo_walkthrough import run_demo


@pytest.mark.asyncio
async def test_demo_walkthrough_generates_four_passed_scenarios(tmp_path: Path) -> None:
    report = await run_demo(tmp_path)

    assert report["gate"] == "PASS"
    assert report["total"] == 4
    assert report["failed"] == 0
    assert (tmp_path / "demo_walkthrough.json").exists()
    assert (tmp_path / "demo_walkthrough.html").exists()


@pytest.mark.asyncio
async def test_demo_walkthrough_contains_legacy_failure_and_objection(tmp_path: Path) -> None:
    report = await run_demo(tmp_path)
    by_id = {item["scenario_id"]: item for item in report["scenarios"]}

    assert by_id["02_legacy_down"]["final_quote_status"] == "unavailable"
    assert by_id["02_legacy_down"]["final_status"] == "handoff"
    assert by_id["04_post_quote_objection"]["final_handoff_reason"]
    assert "objecao" in by_id["04_post_quote_objection"]["final_handoff_reason"]
