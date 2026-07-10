from __future__ import annotations

from pathlib import Path

from scripts.security_scan import scan_paths, write_report


def test_security_scan_fails_on_raw_pii(tmp_path: Path) -> None:
    target = tmp_path / "bad.jsonl"
    target.write_text(
        '{"cpf":"389.083.863-43","email":"ana@example.com","telefone":"1199999-1111"}',
        encoding="utf-8",
    )

    report = scan_paths([target])

    assert report["gate"] == "FAIL"
    kinds = {item["kind"] for item in report["failures"]}
    assert "raw_cpf_formatted" in kinds
    assert "raw_email" in kinds
    assert "raw_phone" in kinds


def test_security_scan_passes_masked_pii_and_writes_report(tmp_path: Path) -> None:
    target = tmp_path / "good.jsonl"
    target.write_text(
        '{"cpf":"***.083.863-**","email":"an***@example.com","telefone":"***1111"}',
        encoding="utf-8",
    )

    report = scan_paths([target])
    write_report(report, tmp_path / "out")

    assert report["gate"] == "PASS"
    assert report["failure_count"] == 0
    assert (tmp_path / "out" / "security_scan_report.json").exists()
    assert (tmp_path / "out" / "security_scan_report.html").exists()


def test_security_scan_does_not_flag_uuid_digits_as_cpf(tmp_path: Path) -> None:
    target = tmp_path / "trace.json"
    target.write_text(
        '{"message_id":"0620e067-cb9a-49b0-9702-00388594237b","cpf_masked":"***.515.492-**"}',
        encoding="utf-8",
    )

    report = scan_paths([target])

    assert report["gate"] == "PASS"
    assert report["failure_count"] == 0
