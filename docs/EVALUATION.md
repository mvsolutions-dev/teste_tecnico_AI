# AutoSeguro AgentOps - Avaliacao

## Gates locais

```bash
cd agent-service
python -m pytest -q --basetemp .pytest-tmp
python -m ruff check .
```

Resultado local desta rodada:

- `58 passed, 1 warning`
- `ruff`: sem violacoes

Baseline registrado em `docs/BASELINE.md`:

- `python scripts/smoke_delivery.py --limit 250`: `gate=PASS`
- `eval_gate=PASS`
- `acceptance_gate=PASS`
- `chaos_gate=PASS`
- `demo_gate=PASS`
- `security_gate=PASS`

## Dataset profile

Comando:

```bash
python agent-service/scripts/profile_dataset.py \
  --dataset-dir dataset \
  --output runtime/reports/dataset_profile.json \
  --markdown-output runtime/reports/dataset_profile.md
```

Resultado observado:

- 26.470 mensagens;
- 2.500 conversas;
- 16.470 mensagens de lead;
- 56,8% das conversas contem algum tipo de midia;
- 2.500 CPFs e 2.500 CEPs aparecem em texto livre;
- outcomes: `em_negociacao=757`, `ganho=712`, `perdido=538`, `sem_resposta=493`.

Implicacao: o agente precisa redigir PII em logs, tratar midia sem transcricao e
ter criterio claro de objecao/handoff.

## Replay Arena - quote estavel

Comando:

```bash
python agent-service/scripts/replay_arena.py \
  --limit 200 \
  --quote-api-url http://127.0.0.1:8000 \
  --timeout 2 \
  --max-attempts 2 \
  --output runtime/reports/arena_200_stable.json \
  --markdown-output runtime/reports/arena_200_stable.md
```

Resultado observado com `QUOTE_FAILURE_RATE=0` e `QUOTE_SLOW_RATE=0`:

- 200 conversas avaliadas do parquet completo via DuckDB;
- `quoted=58`;
- `handoff=142`;
- `quote_status`: `success=151`, `refused=49`;
- cobertura de slots obrigatorios: 100% para idade, CEP, ano do veiculo e plano;
- principais handoffs:
  - midia sem texto;
  - objecao comercial apos cotacao;
  - cotacao recusada por idade ou veiculo antigo.

## Replay Arena - legado instavel

Comando:

```bash
python agent-service/scripts/replay_arena.py \
  --limit 50 \
  --quote-api-url http://127.0.0.1:8000 \
  --timeout 2 \
  --max-attempts 2 \
  --output runtime/reports/arena_50_unstable_after_terminal_fix.json \
  --markdown-output runtime/reports/arena_50_unstable_after_terminal_fix.md
```

Resultado observado com `QUOTE_FAILURE_RATE=0.45`, `QUOTE_SLOW_RATE=0`,
`QUOTE_SEED=7`:

- 50 conversas avaliadas;
- `quoted=9`;
- `handoff=41`;
- `quote_status`: `success=32`, `unavailable=10`, `refused=8`;
- tentativas de quote: media `1.42`, max `2`;
- handoff por indisponibilidade do legado: 10 conversas.

Bug encontrado e corrigido nessa rodada: depois de handoff por falha do legado,
mensagens futuras nao podem reabrir o fluxo e virar `quoted`. Handoff agora e
terminal e coberto por teste.

## Eval Suite in-process

Comando:

```bash
python agent-service/scripts/run_eval_suite.py \
  --limit 2500 \
  --unstable-limit 250 \
  --output-dir runtime/reports/eval_suite
```

Por que existe: a Replay Arena via HTTP e util para smoke real, mas e lenta para
rodar 2.500 conversas frequentemente. A Eval Suite usa o mesmo agente e importa
a regra real de `quote-service/app/quote_logic.py`, simulando falha/timeout no
adaptador. Assim conseguimos avaliar todo o dataset em segundos.

Resultado local:

- gate: `PASS`;
- dataset: parquet completo via DuckDB;
- `2.500` conversas avaliadas no cenario estavel;
- tempo do cenario estavel: `2,288s`;
- throughput: `1.092,83 conversas/s`;
- status estavel: `quoted=638`, `handoff=1862`;
- quote status estavel: `success=1749`, `refused=751`;
- `0` violacoes de handoff terminal;
- cobertura de slots: `100%` para nome, idade, CEP, ano do veiculo e plano;
- cenario instavel: `250` conversas, `unavailable=71`, `0` violacoes de gate.

Saidas:

- `runtime/reports/eval_suite/eval_suite_report.json`
- `runtime/reports/eval_suite/eval_suite_report.html`

## LLM-as-a-Judge

Comando:

```bash
python agent-service/scripts/llm_judge_eval.py \
  --limit 6 \
  --output runtime/reports/llm_judge_report.json
```

O juiz usa Azure OpenAI (`AZURE_DEPLOYMENT_MINI`) e avalia uma amostra curta com
criterios objetivos: nao inventar preco, PII mascarada, handoff aceitavel,
resposta util e decisao terminal.

Resultado local apos calibragem:

- `passed=6`;
- `failed=0`;
- `avg_score=97,5`.

Falha descoberta pelo juiz e corrigida: apos o lead recusar ou aceitar a cotacao,
o agente nao deve repetir uma resposta generica. Agora aceite vai para handoff de
emissao humana e recusa vai para handoff de retencao/registro de perda.

## Cache e estimativa

Testes adicionados:

- chave de cache nao guarda CEP completo;
- cache hit retorna sem chamada HTTP;
- estimador marca `estimated=true` e `requires_human_validation=true`;
- indisponibilidade do legado pode gerar `quote_status=estimated`;
- agente faz handoff quando a resposta e estimada.

Politica validada:

- cache de cotacao real pode ser usado como resposta;
- cache stale so entra em contingencia;
- estimativa nao e preco oficial;
- estimativa sempre exige validacao humana e segue para `handoff_packet`.

## O que ainda seria melhorado com mais tempo

- Persistir estado em Redis/Postgres.
- Transcrever audio/imagem/documento em vez de handoff imediato.
- Separar replay de carga total usando cliente in-process para reduzir tempo.
- Adicionar dashboard simples para ler `FlightRecorder`.
- Rodar LLM-as-a-judge em amostras de conversas para avaliar tom e completude.
## Smoke de entrega

O comando recomendado para uma revisao rapida e:

```bash
cd agent-service
python scripts/smoke_delivery.py --limit 250
```

Ele executa, em sequencia:

1. `pytest`;
2. `ruff`;
3. profile do dataset;
4. eval suite com quote in-process;
5. acceptance suite;
6. chaos matrix;
7. trace replay HTML;
8. demo walkthrough;
9. security scan;
10. control tower HTML.

Saidas principais:

- `runtime/reports/delivery_smoke/delivery_smoke_report.json`
- `runtime/reports/delivery_smoke/delivery_smoke_report.md`
- `runtime/reports/delivery_smoke/control_tower.html`
- `runtime/reports/delivery_smoke/trace_replay.html`
- `runtime/reports/delivery_smoke/acceptance/acceptance_report.html`
- `runtime/reports/delivery_smoke/chaos_matrix/chaos_matrix_report.html`
- `runtime/reports/delivery_smoke/demo_walkthrough/demo_walkthrough.html`
- `runtime/reports/delivery_smoke/security_scan/security_scan_report.html`

O modo completo usa o dataset inteiro:

```bash
cd agent-service
python scripts/smoke_delivery.py --full
```

## Trace Replay

O trace replay seleciona uma conversa do dataset, roda o agente e gera um HTML
redigido com:

- mensagem do lead;
- resposta do agente;
- status e `quote_status` por turno;
- slots faltantes;
- estado do lead apos cada turno;
- handoff packet / estado final.

```bash
python agent-service/scripts/build_trace_replay.py \
  --dataset-dir dataset \
  --output runtime/reports/trace_replay.html \
  --json-output runtime/reports/trace_replay.json
```

Esse artefato foi criado para responder rapidamente: "da para rastrear o que
aconteceu em uma conversa real?".

## Acceptance Suite

```bash
python agent-service/scripts/run_acceptance_suite.py \
  --output-dir runtime/reports/acceptance
```

A suite cobre os criterios de produto mais importantes:

- caminho feliz com cotacao oficial;
- midia sem transcricao vira handoff;
- pedido de humano vira handoff;
- legado indisponivel vira handoff;
- regras de recusa por idade e veiculo sao respeitadas;
- aceite pos-cotacao vai para emissao humana;
- objecao comercial vai para humano;
- lead incompleto recebe proxima pergunta objetiva.

## Chaos Matrix

```bash
python agent-service/scripts/run_chaos_matrix.py \
  --dataset-dir dataset \
  --limit 250 \
  --output-dir runtime/reports/chaos_matrix
```

A matriz roda o agente variando a instabilidade do legado:

- 0% falha / 0% timeout;
- 20% falha;
- 50% falha / 5% timeout;
- 80% falha / 10% timeout.

O gate e objetivo: se a cotacao ficar `unavailable`, a conversa precisa terminar
em handoff e nunca apresentar preco inventado.

## Demo Walkthrough

```bash
python agent-service/scripts/demo_walkthrough.py \
  --output-dir runtime/reports/demo_walkthrough
```

O walkthrough gera uma narrativa visual para revisao humana com quatro casos:

- cotacao oficial;
- legado indisponivel;
- midia sem transcricao;
- objecao comercial depois da cotacao.

## Security Scan

```bash
python agent-service/scripts/security_scan.py \
  --paths runtime/logs runtime/reports \
  --output-dir runtime/reports/security_scan
```

O scanner falha se encontrar CPF, telefone, e-mail ou placa em claro nos logs e
relatorios gerados. CEP completo e reportado como warning porque faz parte do
dominio de cotacao, mas nao deve ser usado em chave de cache junto com PII.

## HTTP E2E Smoke opcional

Comando:

```bash
cd agent-service
python scripts/http_e2e_smoke.py --start-services
```

O smoke sobe localmente `quote-service` e `agent-service`, valida `GET /health`,
envia quatro conversas via `POST /chat` e checa:

- `X-Trace-Id` no header;
- status final esperado;
- `quote_status=success` apenas no caminho feliz;
- nenhum preco oficial quando nao houve cotacao oficial;
- reports JSON/HTML em `runtime/reports/http_e2e/`.

Tambem pode ser executado dentro do delivery smoke:

```bash
python scripts/smoke_delivery.py --limit 250 --include-http-e2e --http-e2e-start-services
```

## LLM Judge opcional no delivery smoke

Comando:

```bash
python scripts/smoke_delivery.py --limit 250 --include-llm-judge
```

Sem variaveis de Azure/OpenAI, o judge escreve report com `status=skipped` e o gate
principal continua `PASS`. Com variaveis preenchidas, roda uma amostra curta e
reporta `llm_judge_status`, `avg_score` e falhas.

## LLM Provider Smoke opcional

O adapter real de LLM e validado fora do smoke default:

```bash
cd agent-service
python scripts/llm_provider_smoke.py --list
python scripts/llm_provider_smoke.py --provider fake
python scripts/llm_provider_smoke.py --provider openai
python scripts/llm_provider_smoke.py --provider azure_openai
python scripts/llm_provider_smoke.py --provider openai_compatible
```

Sem envs reais, providers externos ficam `SKIPPED` e nao quebram o produto principal.
Com envs reais, o script valida resposta JSON no schema agentic, latencia, provider e
modelo/deployment, sem imprimir ou persistir chaves.

Os testes unitarios cobrem a factory, provider fake, fallback de erro e guardrails
contra `reply_draft` com preco inventado. Nenhum teste unitario chama OpenAI/Azure real.
