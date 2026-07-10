import argparse

import pytest

from scripts import llm_provider_smoke


@pytest.mark.asyncio
async def test_provider_smoke_fake_passes(tmp_path) -> None:
    args = argparse.Namespace(
        list=False,
        all=False,
        provider="fake",
        output_dir=str(tmp_path),
        timeout=5.0,
        real=False,
        fail_on_skip=False,
        redact_output=True,
    )

    exit_code = await llm_provider_smoke.run(args)

    report = tmp_path.joinpath("llm_provider_smoke_report.json").read_text(encoding="utf-8")
    assert exit_code == 0
    assert '"gate": "PASS"' in report
    assert "OPENAI_API_KEY" not in report


@pytest.mark.asyncio
async def test_provider_smoke_missing_real_provider_is_skipped(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    args = argparse.Namespace(
        list=False,
        all=False,
        provider="openai",
        output_dir=str(tmp_path),
        timeout=5.0,
        real=False,
        fail_on_skip=False,
        redact_output=True,
    )

    exit_code = await llm_provider_smoke.run(args)

    report = tmp_path.joinpath("llm_provider_smoke_report.json").read_text(encoding="utf-8")
    assert exit_code == 0
    assert '"status": "SKIPPED"' in report
