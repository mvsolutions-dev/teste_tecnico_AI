param(
    [ValidateSet("install", "test", "lint", "smoke", "smoke-full", "smoke-http", "acceptance", "chaos", "security")]
    [string]$Task = "smoke"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

switch ($Task) {
    "install" { python -m pip install -e ".[dev]" }
    "test" { python -m pytest -q --basetemp .pytest-tmp }
    "lint" { python -m ruff check . }
    "smoke" { python scripts/smoke_delivery.py --limit 250 }
    "smoke-full" { python scripts/smoke_delivery.py --full }
    "smoke-http" { python scripts/http_e2e_smoke.py --start-services }
    "acceptance" { python scripts/run_acceptance_suite.py --output-dir runtime/reports/acceptance }
    "chaos" { python scripts/run_chaos_matrix.py --dataset-dir ../dataset --limit 250 --output-dir runtime/reports/chaos_matrix }
    "security" { python scripts/security_scan.py --paths runtime/logs runtime/reports --output-dir runtime/reports/security_scan }
}
