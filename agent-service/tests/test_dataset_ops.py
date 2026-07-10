from __future__ import annotations

from pathlib import Path

from app.dataset_loader import load_conversation_rows


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dataset_loader_reads_full_parquet_with_duckdb() -> None:
    loaded = load_conversation_rows(REPO_ROOT / "dataset")

    assert "duckdb" in loaded.source
    assert len(loaded.rows) == 26470
    assert len({row["conversation_id"] for row in loaded.rows}) == 2500


def test_dataset_rows_are_ordered_by_conversation_and_message_index() -> None:
    loaded = load_conversation_rows(REPO_ROOT / "dataset")
    first = loaded.rows[:5]

    assert {row["conversation_id"] for row in first} == {"conv_00000"}
    assert [int(row["message_index"]) for row in first] == [0, 1, 2, 3, 4]
