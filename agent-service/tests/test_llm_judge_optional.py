from __future__ import annotations

import argparse
import json

import pytest

from scripts import llm_judge_eval


@pytest.mark.asyncio
async def test_llm_judge_skips_without_env(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    for key in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_DEPLOYMENT_MINI"):
        monkeypatch.delenv(key, raising=False)
    output = tmp_path / "judge.json"

    code = await llm_judge_eval.run(argparse.Namespace(limit=2, output=str(output)))
    report = json.loads(output.read_text(encoding="utf-8"))

    assert code == 0
    assert report["status"] == "skipped"
    assert report["gate"] == "SKIPPED"
