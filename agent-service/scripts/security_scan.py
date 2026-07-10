from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

CPF_FORMATTED_RE = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
CPF_UNFORMATTED_RE = re.compile(r"(?<![A-Za-z0-9-])\d{11}(?![A-Za-z0-9-])")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<![\da-fA-F])(?:\(\d{2}\)\s?|\d{2}[\s-]?)(?:9\d{4}|\d{4})[-\s]\d{4}(?![\da-fA-F])"
)
PLATE_RE = re.compile(r"\b[A-Z]{3}[-\s]?\d[A-Z0-9]\d{2}\b")
CEP_RE = re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)")

FAIL_PATTERNS = {
    "raw_cpf_formatted": CPF_FORMATTED_RE,
    "raw_cpf_unformatted": CPF_UNFORMATTED_RE,
    "raw_email": EMAIL_RE,
    "raw_phone": PHONE_RE,
    "raw_plate": PLATE_RE,
}
WARN_PATTERNS = {
    "cep_visible": CEP_RE,
}


def _iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for item in path.rglob("*"):
            if item.is_file() and item.suffix.lower() in {".json", ".jsonl", ".md", ".html", ".txt"}:
                files.append(item)
    return files


def _redact_match(kind: str, value: str) -> str:
    if kind.startswith("raw_cpf"):
        return "***.***.***-**"
    if kind == "raw_email":
        domain = value.split("@", 1)[-1]
        return f"***@{domain}"
    if kind == "raw_phone":
        return "***" + value[-4:]
    if kind == "raw_plate":
        return "***-****"
    if kind == "cep_visible":
        return value[:2] + "***-***"
    return "***"


def _scan_text(path: Path, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    failures = []
    warnings = []
    for kind, pattern in FAIL_PATTERNS.items():
        for match in pattern.finditer(text):
            failures.append(
                {
                    "file": str(path),
                    "kind": kind,
                    "redacted_match": _redact_match(kind, match.group(0)),
                    "offset": match.start(),
                }
            )
    for kind, pattern in WARN_PATTERNS.items():
        count = len(pattern.findall(text))
        if count:
            warnings.append({"file": str(path), "kind": kind, "count": count})
    return failures, warnings


def scan_paths(paths: list[str | Path]) -> dict[str, Any]:
    files = _iter_files([Path(path) for path in paths])
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        file_failures, file_warnings = _scan_text(path, text)
        failures.extend(file_failures)
        warnings.extend(file_warnings)
    return {
        "gate": "PASS" if not failures else "FAIL",
        "scanned_files": len(files),
        "failure_count": len(failures),
        "warning_count": sum(item.get("count", 1) for item in warnings),
        "failures": failures[:200],
        "warnings": warnings[:200],
        "policy": {
            "fail": sorted(FAIL_PATTERNS),
            "warn": sorted(WARN_PATTERNS),
            "note": "CEP visivel e tratado como warning porque pode ser necessario para cotacao; CPF/email/telefone/placa crus falham o gate.",
        },
    }


def _render_html(report: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>AutoSeguro Security Scan</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
    .metric {{ border: 1px solid #d8dee9; border-radius: 10px; padding: 14px; background: #f8fafc; }}
    .metric span {{ display: block; color: #64748b; font-size: 12px; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    pre {{ background: #0f172a; color: #dbeafe; padding: 14px; border-radius: 8px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>AutoSeguro Security Scan</h1>
  <div class="grid">
    <div class="metric"><span>Gate</span><strong>{html.escape(report['gate'])}</strong></div>
    <div class="metric"><span>Files</span><strong>{report['scanned_files']}</strong></div>
    <div class="metric"><span>Failures</span><strong>{report['failure_count']}</strong></div>
    <div class="metric"><span>Warnings</span><strong>{report['warning_count']}</strong></div>
  </div>
  <h2>Report</h2>
  <pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
</body>
</html>
"""


def write_report(report: dict[str, Any], output_dir: str | Path) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "security_scan_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_path / "security_scan_report.html").write_text(_render_html(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan generated logs/reports for raw PII")
    parser.add_argument(
        "--paths",
        nargs="+",
        default=["runtime/logs", "runtime/reports"],
        help="Arquivos ou diretorios a escanear.",
    )
    parser.add_argument("--output-dir", default="runtime/reports/security_scan")
    args = parser.parse_args()
    report = scan_paths(args.paths)
    write_report(report, args.output_dir)
    print(
        json.dumps(
            {k: report[k] for k in ["gate", "scanned_files", "failure_count", "warning_count"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
