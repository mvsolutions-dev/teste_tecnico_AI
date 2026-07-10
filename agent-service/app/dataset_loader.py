from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DatasetLoadResult:
    rows: list[dict[str, Any]]
    source: str
    warning: str | None = None


def load_conversation_rows(dataset_dir: str | Path) -> DatasetLoadResult:
    """Carrega o dataset completo com fallback controlado.

    O parquet do desafio pode falhar em algumas combinacoes de pyarrow no
    Windows. DuckDB le o arquivo local corretamente e vira o caminho preferido
    para avaliacao.
    """
    root = Path(dataset_dir)
    parquet = root / "conversations.parquet"
    sample = root / "sample.jsonl"

    if parquet.exists():
        duckdb_result = _load_parquet_duckdb(parquet)
        if duckdb_result is not None:
            return duckdb_result
        pandas_result = _load_parquet_pandas(parquet)
        if pandas_result is not None:
            return pandas_result

    if not sample.exists():
        raise FileNotFoundError(f"Nenhum dataset encontrado em {root}")
    rows = [json.loads(line) for line in sample.read_text(encoding="utf-8").splitlines() if line.strip()]
    return DatasetLoadResult(
        rows=rows,
        source=str(sample),
        warning="parquet indisponivel; usando sample.jsonl",
    )


def _load_parquet_duckdb(path: Path) -> DatasetLoadResult | None:
    try:
        import duckdb

        con = duckdb.connect()
        rows = con.execute(
            "select * from read_parquet(?) order by conversation_id, message_index",
            [str(path)],
        ).fetch_df().to_dict(orient="records")
        return DatasetLoadResult(rows=rows, source=f"{path} via duckdb")
    except Exception:
        return None


def _load_parquet_pandas(path: Path) -> DatasetLoadResult | None:
    try:
        import pandas as pd

        rows = (
            pd.read_parquet(path)
            .sort_values(["conversation_id", "message_index"])
            .to_dict(orient="records")
        )
        return DatasetLoadResult(rows=rows, source=f"{path} via pandas")
    except Exception:
        return None
