# AutoSeguro AgentOps - Baseline local

Data da rodada: 2026-07-09.

Objetivo: registrar o estado conhecido antes da rodada final de polish técnico e
documental.

## Gates executados

Diretorio:

```bash
cd agent-service
```

Resultados:

```bash
python -m pytest -q --basetemp .pytest-tmp
# 36 passed, 1 warning

python -m ruff check .
# All checks passed

python scripts/smoke_delivery.py --limit 250
# gate=PASS
```

## Smoke summary observado

- `eval_gate=PASS`
- `acceptance_gate=PASS`
- `chaos_gate=PASS`
- `demo_gate=PASS`
- `security_gate=PASS`
- `eval_conversations=2500`
- `trace_final_status=handoff`
- `trace_final_quote_status=success`

## Riscos detectados no baseline

- O README original ainda apresentava primeiro o enunciado do desafio, e só depois a
  solução. Isso aumenta o tempo de entendimento do avaliador.
- O campo `veiculo_texto` podia ficar poluído com trechos livres do lead em algumas
  mensagens.
- A eval principal era in-process; faltava um smoke HTTP opcional para provar a
  integração real entre `agent-service` e `quote-service`.
- A persistência era apenas em memória. Adequado ao take-home, mas sem demonstrar uma
  ponte local simples para produção.

## Decisão

Aplicar melhorias incrementais sem trocar a arquitetura:

- documentação reviewer-first;
- smoke HTTP opcional;
- SQLite opcional com payload redigido;
- normalização de veículo;
- flags opcionais de LLM judge no delivery smoke;
- control tower com narrativa executiva.
