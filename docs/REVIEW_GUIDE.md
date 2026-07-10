# AutoSeguro AgentOps - Review Guide

Este guia existe para uma avaliação técnica rápida. A ideia é permitir que outro
engenheiro verifique funcionamento, resiliência e rastreabilidade sem precisar
ler o repositório inteiro primeiro.

## Revisao em 10 minutos

1. Instale as dependências do agente:

   ```bash
   cd agent-service
   python -m pip install -e ".[dev]"
   ```

2. Rode o smoke determinístico:

   ```bash
   python scripts/smoke_delivery.py --limit 250
   ```

   Atalhos equivalentes:

   ```bash
   make smoke
   # ou, no Windows
   powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 smoke
   ```

3. Abra os artefatos gerados:

   - `runtime/reports/delivery_smoke/control_tower.html`
   - `runtime/reports/delivery_smoke/trace_replay.html`
   - `runtime/reports/delivery_smoke/eval_suite/eval_suite_report.html`
   - `runtime/reports/delivery_smoke/acceptance/acceptance_report.html`
   - `runtime/reports/delivery_smoke/chaos_matrix/chaos_matrix_report.html`
   - `runtime/reports/delivery_smoke/demo_walkthrough/demo_walkthrough.html`
   - `runtime/reports/delivery_smoke/security_scan/security_scan_report.html`

4. Verifique o gate:

   - `delivery_smoke_report.json` deve ter `gate=PASS`;
   - `eval_suite_report.json` deve ter `gate=PASS`;
   - `terminal_handoff_violations` deve ser `0`.

## O que olhar no código

- `agent-service/app/agent.py`: estado conversacional, decisões de handoff e chamada de cotação.
- `agent-service/app/llm/`: provider adapters e contrato estruturado LLM-first.
- `agent-service/app/quote_client.py`: retry, timeout, circuit breaker, cache e estimativa.
- `agent-service/app/pii.py`: redação de CPF, telefone, email e placa.
- `agent-service/app/handoff_packet.py`: pacote operacional para o corretor humano.
- `agent-service/app/main.py`: endpoints publicos, `X-Trace-Id` e `/ops/metrics`.
- `agent-service/scripts/run_eval_suite.py`: avaliação em massa no dataset completo.
- `agent-service/scripts/run_acceptance_suite.py`: cenários de aceite do produto.
- `agent-service/scripts/run_chaos_matrix.py`: matriz de resiliência contra legado instável.
- `agent-service/scripts/build_trace_replay.py`: replay visual de uma conversa com estado por turno.
- `agent-service/scripts/demo_walkthrough.py`: demonstração narrativa para banca.
- `agent-service/scripts/security_scan.py`: gate local contra PII crua em logs/relatórios.

## Diferenciais intencionais

- O agente não inventa preço. Cotação oficial só sai após resposta do legado.
- Quando o legado falha, existe retry, cache stale-if-error e estimativa preliminar marcada para validação humana.
- Handoff é terminal: depois de encaminhar para humano, o bot não reabre cotação automaticamente.
- Logs e replays persistem conteúdo redigido, não PII bruta.
- O dataset não é apenas insumo textual: ele vira suíte de avaliação e relatório operacional.

## Modo com LLM

O fluxo principal roda sem chave de LLM. Se uma chave estiver configurada, o extrator
usa provider adapters para interpretar mensagens livres, extrair slots, identificar
intenção/objeções e sugerir uma resposta consultiva. As decisões criticas continuam
protegidas por código determinístico.

Variaveis aceitas:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `AUTOSEGURO_LLM_PROVIDER`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_DEPLOYMENT_MINI`
- `OPENAI_COMPATIBLE_API_KEY`
- `OPENAI_COMPATIBLE_BASE_URL`
- `OPENAI_COMPATIBLE_MODEL`

Não commitar `.env`.

Smoke de provider:

```bash
python scripts/llm_provider_smoke.py --list
python scripts/llm_provider_smoke.py --provider fake
python scripts/llm_provider_smoke.py --provider openai
python scripts/llm_provider_smoke.py --provider azure_openai
```

O juiz LLM e opcional:

```bash
python scripts/smoke_delivery.py --limit 250 --include-llm-judge
```

Sem variaveis preenchidas, o report marca `llm_judge_status=skipped` e mantem o
gate principal verde.

## Smoke HTTP opcional

Para validar integração real entre agent e quote API:

```bash
python scripts/http_e2e_smoke.py --start-services
```

O report sai em:

- `runtime/reports/http_e2e/http_e2e_report.json`
- `runtime/reports/http_e2e/http_e2e_report.html`

## Persistência local opcional

O default é memória. Para testar persistência local redigida:

```bash
AUTOSEGURO_STATE_STORE=sqlite AUTOSEGURO_SQLITE_PATH=runtime/state/autoseguro.db uvicorn app.main:app --port 8010
```

No PowerShell:

```powershell
$env:AUTOSEGURO_STATE_STORE="sqlite"
$env:AUTOSEGURO_SQLITE_PATH="runtime/state/autoseguro.db"
uvicorn app.main:app --port 8010
```
