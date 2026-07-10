from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_chaos_matrix import run_matrix


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_chaos_matrix_keeps_unavailable_quotes_in_handoff(tmp_path: Path) -> None:
    report = await run_matrix(
        dataset_dir=REPO_ROOT / "dataset",
        output_dir=tmp_path,
        limit=40,
        seed=17,
    )

    assert report["gate"] == "PASS"
    assert report["matrix"]
    assert (tmp_path / "chaos_matrix_report.json").exists()
    assert (tmp_path / "chaos_matrix_report.html").exists()
    for cell in report["matrix"]:
        assert cell["gate"] == "PASS"
        assert cell["unavailable_not_handoff"] == []
