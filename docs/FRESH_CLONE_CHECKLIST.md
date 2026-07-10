# Fresh Clone Checklist

Use este roteiro para simular a banca em uma pasta limpa.

```bash
git clone <repo-publico> autoseguro-review
cd autoseguro-review/agent-service
python -m pip install -e ".[dev]"
python -m pytest -q --basetemp .pytest-tmp
python -m ruff check .
python scripts/smoke_delivery.py --limit 250
```

Validar:

- `delivery_smoke_report.json` com `gate=PASS`;
- `eval_suite_report.json` com `gate=PASS`;
- `acceptance_report.json` com `gate=PASS`;
- `chaos_matrix_report.json` com `gate=PASS`;
- `security_scan_report.json` com `gate=PASS`;
- `terminal_handoff_violations=0`;
- nenhum arquivo `.env`, banco SQLite, cache ou `runtime/` versionado.

Checks opcionais:

```bash
python scripts/smoke_delivery.py --full
python scripts/smoke_delivery.py --limit 250 --include-llm-judge
python scripts/http_e2e_smoke.py --start-services
```

Observações:

- O fluxo principal não precisa de chave de LLM.
- Se o LLM judge estiver sem variaveis de ambiente, ele deve aparecer como
  `skipped`, não como falha.
- O SQLite opcional deve ser testado com `AUTOSEGURO_STATE_STORE=sqlite`, mas o
  banco gerado em `runtime/state/` não deve ser commitado.
