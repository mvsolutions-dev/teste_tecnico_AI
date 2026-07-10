from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_acceptance_suite import run_suite


@pytest.mark.asyncio
async def test_acceptance_suite_passes_core_product_scenarios(tmp_path: Path) -> None:
    report = await run_suite(tmp_path)

    assert report["gate"] == "PASS"
    assert report["failed"] == 0
    assert report["total"] >= 8
    assert (tmp_path / "acceptance_report.json").exists()
    assert (tmp_path / "acceptance_report.html").exists()


@pytest.mark.asyncio
async def test_acceptance_suite_covers_legacy_failure_and_media(tmp_path: Path) -> None:
    report = await run_suite(tmp_path)
    by_id = {item["scenario_id"]: item for item in report["scenarios"]}

    assert by_id["legacy_down_goes_to_handoff"]["final_status"] == "handoff"
    assert by_id["legacy_down_goes_to_handoff"]["final_quote_status"] == "unavailable"
    assert by_id["media_goes_to_handoff"]["final_status"] == "handoff"
    assert "midia" in by_id["media_goes_to_handoff"]["final_handoff_reason"]
