# AutoSeguro AgentOps — FDE / AI Engineer Take-home

Esta entrega transforma o desafio original em uma camada operacional auditavel para
atendimento de seguro auto. Nao e apenas um chatbot: o agente conversa com o lead,
coleta dados minimos, chama o legado `/quote`, decide quando pode resolver sozinho,
encaminha quando precisa de humano, nao inventa preco quando a infraestrutura falha e
gera evidencias locais de qualidade, resiliencia e seguranca.

## Evaluator Fast Path — 10-minute review

```bash
cd agent-service
python -m pip install -e ".[dev]"
python scripts/smoke_delivery.py --limit 250
```

Open:

- `runtime/reports/delivery_smoke/control_tower.html`
- `runtime/reports/delivery_smoke/trace_replay.html`
- `runtime/reports/delivery_smoke/eval_suite/eval_suite_report.html`
- `runtime/reports/delivery_smoke/acceptance/acceptance_report.html`
- `runtime/reports/delivery_smoke/chaos_matrix/chaos_matrix_report.html`
- `runtime/reports/delivery_smoke/demo_walkthrough/demo_walkthrough.html`
- `runtime/reports/delivery_smoke/security_scan/security_scan_report.html`

Expected:

- `delivery_smoke_report.json` => `gate=PASS`
- `terminal_handoff_violations` => `0`
- no raw CPF/phone/email/plate in generated logs/reports

Optional deeper checks:

```bash
python scripts/smoke_delivery.py --full
python scripts/smoke_delivery.py --limit 250 --include-llm-judge
python scripts/http_e2e_smoke.py --start-services
python scripts/llm_provider_smoke.py --provider fake
```

If Azure/OpenAI variables are absent, the LLM judge is reported as `skipped`; the
main flow still runs deterministically.

## What this is

- Operational agent layer for AutoSeguro leads, built to sit in front of an unstable
  legacy quotation service.
- Public HTTP API: `/health`, `POST /chat`, `GET /conversations/{conversation_id}`,
  `GET /ops/metrics`.
- Dataset-driven evaluation: replay/eval suite, acceptance suite, chaos matrix, trace
  replay, security scan and control tower.
- LLM-first when configured, deterministic-safe when not configured. The core flow
  works without API keys.

## What to inspect first

- `agent-service/app/agent.py`: conversation orchestration and handoff decisions.
- `agent-service/app/llm/`: provider adapters for disabled/fake/OpenAI/Azure/OpenAI-compatible.
- `agent-service/app/quote_client.py`: timeout, retry, backoff, circuit breaker,
  cache and estimate fallback.
- `agent-service/app/pii.py`: masking of CPF, phone, email and plate.
- `agent-service/scripts/run_eval_suite.py`: dataset replay at scale.
- `agent-service/scripts/run_chaos_matrix.py`: unstable legacy behavior.
- `agent-service/scripts/security_scan.py`: raw PII gate for generated artifacts.

## Core decisions

- Official price only appears when `quote_status=success` from the real `/quote` call
  or from a real cached quote.
- Preliminary estimate is never official quote and always requires human validation.
- Handoff is terminal: after human routing, later messages are stored as context and do
  not reopen quotation automatically.
- Logs, replay reports, SQLite state and debug endpoints use redacted state.
- The dataset is used as evaluation material, not just as prompt inspiration.

## LLM-first, deterministic-safe

The agent runs in two modes:

1. **LLM-first**, when a provider is configured:
   - interprets free-form lead messages;
   - extracts slots into a typed contract;
   - classifies intent and commercial objections;
   - proposes a premium consultant-style reply.

2. **Deterministic-safe**, when no provider is configured:
   - any evaluator can run the project without external keys;
   - local gates do not depend on OpenAI/Azure availability;
   - pricing and handoff policies remain reproducible.

In both modes, critical decisions are protected by deterministic code: official price
only after `/quote` success, legacy failure becomes safe handoff, handoff is terminal
and PII is redacted.

Provider selection is controlled by `AUTOSEGURO_LLM_PROVIDER`:

```text
disabled | fake | openai | azure_openai | openai_compatible | azure_foundry | auto
```

`auto` priority:

1. OpenAI-compatible / Azure Foundry when complete envs exist;
2. Azure OpenAI;
3. OpenAI direct;
4. disabled.

### Enable OpenAI direct

```bash
cd agent-service
cp .env.example .env
# fill only locally:
AUTOSEGURO_LLM_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini

python scripts/llm_provider_smoke.py --provider openai
```

### Enable Azure OpenAI

```bash
AUTOSEGURO_LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=<deployment-name>
AZURE_OPENAI_API_VERSION=2024-02-15-preview

python scripts/llm_provider_smoke.py --provider azure_openai
```

### Enable OpenAI-compatible / Foundry

```bash
AUTOSEGURO_LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_API_KEY=...
OPENAI_COMPATIBLE_BASE_URL=...
OPENAI_COMPATIBLE_MODEL=...

python scripts/llm_provider_smoke.py --provider openai_compatible
```

The provider smoke writes reports under `runtime/reports/` and never prints or persists
API keys.

## How the conversation dataset was used

I did not use the dataset as raw few-shot prompt examples or model training data. The
history contains synthetic PII, media markers, objections and varied outcomes; copying
raw examples into prompts would increase leakage risk and make behavior harder to audit.

Instead, the dataset became operational engineering material:

1. **EDA / Dataset Profiler**: message volume, media incidence, free-text PII, objections and outcomes.
2. **Agent design**: required slots, handoff rules, media fallback, PII protection and post-quote objection handling.
3. **Replay Arena**: conversations replayed against the agent with status, quote_status and handoff reasons.
4. **Eval Suite**: full in-process dataset evaluation for fast reproducibility.
5. **Chaos Matrix**: dataset plus simulated legacy failures to prove `unavailable` never invents price.
6. **Trace Replay**: visual redacted transcript with state after each turn.

In short: the dataset did not become loose LLM memory. It became evidence, tests,
decision criteria and operational design.

## Optional and out of scope

- Optional: OpenAI/Azure OpenAI extraction assist and LLM-as-a-Judge.
- Optional: local SQLite state with `AUTOSEGURO_STATE_STORE=sqlite`.
- Out of scope: cloud deploy, policy issuance, real media transcription, billing or a
  complex web UI.

## Original challenge statement

Bem-vindo(a)! Este é um teste **take-home** que espelha o trabalho real de um FDE
(Forward Deployed Engineer) na Namastex: subir um **agente de verdade**, conectado a
sistemas que nem sempre colaboram, em cima de **dados bagunçados do mundo real**.

> ⏱️ **Tempo:** ~3 dias de relógio. **Espera-se que você use AI coding tools**
> (Claude Code, Cursor, etc.) — isso é a régua aqui, não trapaça. A gente quer ver
> você orquestrando IA pra entregar com qualidade e velocidade.

---

## O cenário

Você é o engenheiro responsável por uma seguradora fictícia, a **AutoSeguro**. O time
de vendas atende leads por **WhatsApp** e fecha seguro de **veículo**. Sua missão é
construir um **agente** que:

1. **Conversa** com o lead, qualifica e **cota um plano** usando a nossa API de cotação.
2. **Decide** quando consegue resolver sozinho e quando precisa **passar pra um humano**.
3. Não trava nem inventa preço quando a infraestrutura falha.

Te entregamos três coisas (tudo neste repo):

| Insumo | Onde | O que é |
|---|---|---|
| **API de cotação** | `quote-service/` | Serviço HTTP `POST /quote` que você sobe local com Docker |
| **Histórico de conversas** | `dataset/conversations.parquet` | ~2.500 conversas reais* lead↔vendedor (*sintéticas, ver dicionário) |
| **Dicionário de dados** | `dataset/DICIONARIO.md` | Esquema do dataset |

---

## Subindo a API de cotação

```bash
docker compose up --build
# API em http://localhost:8000
```

Sem Docker? Dá pra rodar direto:

```bash
cd quote-service && uv run uvicorn app.main:app --port 8000
```

Endpoints:

- `GET  /health` — health check
- `GET  /planos` — tabela de planos **e as regras de cotação** (leia com atenção)
- `POST /quote` — calcula a cotação

Exemplo:

```bash
curl -X POST localhost:8000/quote -H 'content-type: application/json' \
  -d '{"plano_id":"completo","idade":35,"veiculo_ano":2022,"cep":"01310-100","data_inicio":"2026-07-15"}'
```

> ⚠️ **Aviso de operação:** a `/quote` simula um sistema legado real — ela **não responde
> de primeira toda vez** (falhas e lentidão acontecem). Seu agente precisa lidar com isso
> de forma elegante. Tratar bem a instabilidade é parte central do desafio.

---

## O que entregar

1. **Um agente** que atende um lead de ponta a ponta: conversa → qualifica → cota → decide
   (resolve ou encaminha pro humano, com critério claro).
2. **Repositório público no GitHub** com o código.
3. **README** explicando como rodar e **as decisões que você tomou** (e por quê).
4. **Log de uma execução completa** (uma conversa do início ao fim, com a cotação saindo).

Você pode usar o dataset de conversas como bem entender (ex.: few-shot, avaliação,
entender padrões de objeção, testar seu agente). Use o que fizer sentido pra sua solução.

---

## Como a gente vai olhar

Sem pegadinha escondida na avaliação — o que importa:

- **Funciona de ponta a ponta?** O agente cota certo e não quebra no caminho feliz.
- **O que ele faz quando a `/quote` falha?** (esse é o ponto que mais separa.)
- **O critério de passar pro humano é explícito e defensável?**
- **Dá pra rastrear o que aconteceu?** (cada mensagem/cotação, com id e status.)
- **Cuidado com dados sensíveis.** O histórico tem informação pessoal — pense nisso.
- **Qualidade:** outro engenheiro consegue pegar seu código e entender as decisões?

> 💡 Não existe "formato de saída certo" definido de propósito. Queremos ver **a sua decisão** de engenharia.

---

## Entrega

Mande o link do repo público. Qualquer dúvida, fale com quem te enviou o desafio.
Quando começar, **avise** — a gente marca a conversa de feedback logo depois da entrega.

Boa! 🚀

---

## Rodada "fora da caixa": AutoSeguro AgentOps

Esta branch inclui uma primeira solucao de produto para o desafio em `agent-service/`.
A proposta nao e apenas um chatbot: e um agente operacional auditavel, com uma
"caixa-preta" de execucao e uma mini arena de replay.

### O que foi implementado

- `POST /chat`: endpoint conversacional do agente.
- Estado estruturado por conversa:
  - idade;
  - CEP;
  - veiculo/ano;
  - plano;
  - data de inicio;
  - PII mascarada.
- `QuoteClient` resiliente para o sistema legado:
  - timeout;
  - retry;
  - backoff;
  - circuit breaker;
  - cache de cotacoes reais;
  - estimativa preliminar quando o legado cai;
  - classificacao de `success`, `refused`, `invalid` e `unavailable`.
- Handoff humano explicito quando:
  - o lead pede humano/corretor;
  - chega midia sem conteudo textual util;
  - a cotacao e recusada;
  - o legado fica indisponivel apos retries;
  - surge objecao comercial apos cotacao.
- `handoff_packet` estruturado para o corretor humano:
  - lead e veiculo;
  - cotacao;
  - motivo;
  - resumo;
  - proxima melhor acao.
- `FlightRecorder` em JSONL com:
  - mensagens mascaradas;
  - slots extraidos;
  - tentativas de cotacao;
  - decisao final.
- `Replay Arena` para rodar conversas do dataset contra o agente e gerar um resumo.
- `Dataset Profiler` para transformar o historico em insumos de engenharia:
  distribuicao de outcomes, midia, PII, objecoes e implicacoes para o agente.
- Loader robusto do parquet via DuckDB, com fallback para pandas e `sample.jsonl`.
- `Eval Suite` in-process para rodar 2.500 conversas sem depender de HTTP.
- Relatorio HTML executivo em `runtime/reports/eval_suite/eval_suite_report.html`.
- Control Tower consolidada em `runtime/reports/control_tower.html`.
- LLM-as-a-Judge opcional via Azure OpenAI para auditar uma amostra de conversas.
- Acceptance Suite com cenarios de produto alinhados aos criterios do desafio.
- Chaos Matrix para medir comportamento sob falha/timeout do legado.
- Endpoint de debug redigido: `GET /conversations/{conversation_id}`.
- Endpoint operacional simples: `GET /ops/metrics`.
- Header `X-Trace-Id` em `POST /chat`.
- Modo OpenAI opcional:
  - se `OPENAI_API_KEY` estiver definida, o agente pode usar LLM para complementar a extracao;
  - sem chave, o fluxo roda por extracao deterministica e testes continuam verdes.

Documentos de entrega:

- `docs/ARCHITECTURE.md`: arquitetura, estado, contratos de decisao e limites.
- `docs/EVALUATION.md`: gates, dataset profile, replay arena e achados.
- `docs/REVIEW_GUIDE.md`: roteiro objetivo para avaliacao tecnica em 10 minutos.
- `docs/DOSSIE_TECNICO_AUTOSEGURO.md`: dossie executivo-tecnico da entrega.
- `docs/BASELINE.md`: baseline local antes do polish 10/10.
- `docs/FRESH_CLONE_CHECKLIST.md`: roteiro para validar em clone limpo.

### Revisao rapida para avaliador

Para validar a entrega sem subir tudo manualmente:

```bash
cd agent-service
python -m pip install -e ".[dev]"
python scripts/smoke_delivery.py --limit 250
```

O comando gera:

- `runtime/reports/delivery_smoke/delivery_smoke_report.json`;
- `runtime/reports/delivery_smoke/control_tower.html`;
- `runtime/reports/delivery_smoke/trace_replay.html`;
- `runtime/reports/delivery_smoke/acceptance/acceptance_report.html`;
- `runtime/reports/delivery_smoke/chaos_matrix/chaos_matrix_report.html`;
- `runtime/reports/delivery_smoke/demo_walkthrough/demo_walkthrough.html`;
- `runtime/reports/delivery_smoke/security_scan/security_scan_report.html`;
- `runtime/reports/delivery_smoke/eval_suite/eval_suite_report.html`.

Use `--full` para rodar a avaliacao no dataset completo:

```bash
python scripts/smoke_delivery.py --full
```

Com `make` instalado:

```bash
make install
make smoke
make smoke-full
```

No Windows, os mesmos atalhos existem via PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 smoke
```

Tambem ha CI em `.github/workflows/ci.yml`, rodando `pytest` e `ruff` para o
`agent-service`.

### Como rodar

Subir quote API e agent API:

```bash
docker compose up --build
```

Ou localmente, em dois terminais:

```bash
cd quote-service
uv run uvicorn app.main:app --port 8000
```

```bash
cd agent-service
cp .env.example .env  # opcional; coloque sua OPENAI_API_KEY se quiser usar LLM
uv run uvicorn app.main:app --port 8010
```

Teste rapido:

```bash
curl -X POST localhost:8010/chat \
  -H "content-type: application/json" \
  -d '{
    "conversation_id": "demo-001",
    "message": "Sou Ana, tenho 35 anos, CEP 01310-100. Meu carro e um Corolla 2022 e quero completo com inicio em 15/07/2026."
  }'
```

Endpoints do agente:

- `GET /health`
- `POST /chat`
- `GET /conversations/{conversation_id}` — estado redigido para debug
- `GET /ops/metrics` — contadores simples de operacao

O `POST /chat` retorna `X-Trace-Id` no header para correlacionar chamada HTTP,
logs e replay.

### Smoke HTTP E2E local

Para provar a integracao HTTP real entre `agent-service` e `quote-service`:

```bash
cd agent-service
python scripts/http_e2e_smoke.py --start-services
```

Saidas:

- `runtime/reports/http_e2e/http_e2e_report.json`
- `runtime/reports/http_e2e/http_e2e_report.html`

Tambem pode ser anexado ao delivery smoke:

```bash
python scripts/smoke_delivery.py --limit 250 --include-http-e2e --http-e2e-start-services
```

### Persistencia SQLite opcional

O default segue sendo memoria. Para testar estado local persistente e redigido:

```bash
cd agent-service
AUTOSEGURO_STATE_STORE=sqlite AUTOSEGURO_SQLITE_PATH=runtime/state/autoseguro.db uvicorn app.main:app --port 8010
```

PowerShell:

```powershell
$env:AUTOSEGURO_STATE_STORE="sqlite"
$env:AUTOSEGURO_SQLITE_PATH="runtime/state/autoseguro.db"
uvicorn app.main:app --port 8010
```

### Rodar testes

```bash
cd agent-service
uv run pytest -q --basetemp .pytest-tmp
```

No ambiente Windows local desta rodada, o `--basetemp` evita erro de permissao no
diretorio temporario global do pytest.

### Rodar Replay Arena

Com a quote API ativa:

```bash
python agent-service/scripts/replay_arena.py \
  --limit 20 \
  --quote-api-url http://localhost:8000 \
  --output runtime/reports/arena_report.json \
  --markdown-output runtime/reports/arena_report.md
```

O loader tenta DuckDB primeiro, depois pandas, e so cai para `dataset/sample.jsonl`
se o parquet estiver indisponivel. No ambiente Windows desta rodada, DuckDB leu o
parquet completo com `26.470` mensagens e `2.500` conversas.

### Rodar Dataset Profiler

```bash
python agent-service/scripts/profile_dataset.py \
  --dataset-dir dataset \
  --output runtime/reports/dataset_profile.json \
  --markdown-output runtime/reports/dataset_profile.md
```

O profile local indicou:

- `56,8%` das conversas com midia;
- `2.500` CPFs e `2.500` CEPs em texto livre;
- objecoes comerciais frequentes de preco, concorrente e franquia.

Se quiser regenerar o dataset:

```bash
uv run scripts/generate_dataset.py --n 2500 --seed 42 --out dataset/conversations.parquet
```

### Rodar Eval Suite completa

Esta e a avaliacao mais importante da entrega. Ela usa o mesmo agente, mas chama
a logica de cotacao in-process para rodar o dataset inteiro rapidamente.

```bash
python agent-service/scripts/run_eval_suite.py \
  --limit 2500 \
  --unstable-limit 250 \
  --output-dir runtime/reports/eval_suite
```

Saidas:

- `runtime/reports/eval_suite/eval_suite_report.json`
- `runtime/reports/eval_suite/eval_suite_report.html`

Resultado local desta rodada:

- gate: `PASS`;
- cenario estavel: `2.500` conversas em `2,288s`;
- throughput: `1.092 conversas/s`;
- `0` violacoes de handoff terminal;
- cobertura de slots obrigatorios: `100%` para nome, idade, CEP, ano do veiculo e plano;
- cenario instavel: `250` conversas com falha/timeout simulados e `0` violacoes de gate.

### Rodar Acceptance Suite

Valida cenarios de produto diretamente ligados aos criterios do desafio: caminho
feliz, midia, pedido humano, legado indisponivel, cotacao recusada, aceite,
rejeicao, objecao comercial e lead incompleto.

```bash
python agent-service/scripts/run_acceptance_suite.py \
  --output-dir runtime/reports/acceptance
```

Saidas:

- `runtime/reports/acceptance/acceptance_report.json`
- `runtime/reports/acceptance/acceptance_report.html`

### Rodar Chaos Matrix

Executa o agente contra o dataset variando a instabilidade do legado. O gate
principal verifica que `quote_status=unavailable` termina em handoff, nunca em
preco inventado.

```bash
python agent-service/scripts/run_chaos_matrix.py \
  --dataset-dir dataset \
  --limit 250 \
  --output-dir runtime/reports/chaos_matrix
```

Saidas:

- `runtime/reports/chaos_matrix/chaos_matrix_report.json`
- `runtime/reports/chaos_matrix/chaos_matrix_report.html`

### Rodar Demo Walkthrough

Gera uma demonstracao narrativa com quatro conversas curtas: cotacao oficial,
legado indisponivel, midia sem transcricao e objecao comercial apos cotacao.

```bash
python agent-service/scripts/demo_walkthrough.py \
  --output-dir runtime/reports/demo_walkthrough
```

Saidas:

- `runtime/reports/demo_walkthrough/demo_walkthrough.json`
- `runtime/reports/demo_walkthrough/demo_walkthrough.html`

### Rodar Security Scan

Varre logs e relatorios gerados em busca de CPF, telefone, e-mail e placa em claro.
CEP completo entra como warning, pois pode ser necessario para cotacao.

```bash
python agent-service/scripts/security_scan.py \
  --paths runtime/logs runtime/reports \
  --output-dir runtime/reports/security_scan
```

Saidas:

- `runtime/reports/security_scan/security_scan_report.json`
- `runtime/reports/security_scan/security_scan_report.html`

### Decisoes de engenharia

1. **Nao inventar preco**: preco so sai depois de chamada real a `/quote`.
2. **Legado instavel e tratado como regra de produto**: falha/timeout vira retry e,
   se persistir, handoff com motivo claro.
3. **Plano padrao defensavel**: se idade, CEP e veiculo estao completos e so falta
   plano, o agente usa `Completo` como recomendacao equilibrada e registra isso em
   `slot_defaulted`.
4. **PII protegida nos logs**: CPF, telefone, e-mail e placa sao mascarados antes
   de persistir eventos.
5. **Handoff auditavel**: toda passagem para humano tem `handoff_reason`.
6. **Handoff terminal**: depois de encaminhar ao humano, o agente nao reabre o
   fluxo de cotacao automaticamente com mensagens posteriores.
7. **Estimativa nao e cotacao oficial**: se o legado cair e nao houver cache, o
   agente gera apenas uma estimativa preliminar para orientar o humano, marcada
   com `requires_human_validation=true`.

### Smoke local desta rodada

Com quote API estavel (`QUOTE_FAILURE_RATE=0`, `QUOTE_SLOW_RATE=0`):

- conversa completa cotou plano Completo;
- premio mensal: `R$ 209,90`;
- primeiro pagamento proporcional para 15/07/2026: `R$ 115,11`;
- testes unitarios: `11 passed`;
- arena sobre `sample.jsonl`: 3 conversas, 2 cotadas, 1 handoff por midia sem texto.

### Validacao ampliada desta rodada

- testes unitarios: `11 passed`;
- lint: `ruff check .` sem violacoes;
- profile: parquet completo via DuckDB, `26.470` mensagens / `2.500` conversas;
- arena estavel: 200 conversas, `58 quoted`, `142 handoff`;
- arena instavel: 50 conversas com `QUOTE_FAILURE_RATE=0.45`, `10 unavailable`
  encaminhadas com handoff claro.
- eval suite in-process: 2.500 conversas em 2,288s, gate `PASS`.

### Rodar LLM-as-a-Judge

Com Azure OpenAI configurado:

```bash
python agent-service/scripts/llm_judge_eval.py \
  --limit 6 \
  --output runtime/reports/llm_judge_report.json
```

Resultado local apos calibragem:

- `passed=6`;
- `failed=0`;
- `avg_score=97.5`.

### Gerar Control Tower

```bash
python agent-service/scripts/build_control_tower.py \
  --profile runtime/reports/dataset_profile.json \
  --eval-report runtime/reports/eval_suite/eval_suite_report.json \
  --output runtime/reports/control_tower.html
```

### Gerar Trace Replay visual

O Trace Replay gera uma pagina HTML redigida com a conversa, resposta do agente,
status, slots e decisao por turno. Serve para auditar rapidamente uma execucao
sem abrir logs JSONL.

```bash
python agent-service/scripts/build_trace_replay.py \
  --dataset-dir dataset \
  --output runtime/reports/trace_replay.html \
  --json-output runtime/reports/trace_replay.json
```

### Smoke de entrega em um comando

```bash
cd agent-service
python scripts/smoke_delivery.py --limit 250
```

O smoke roda:

1. testes unitarios;
2. lint;
3. profile do dataset;
4. eval suite;
5. acceptance suite;
6. chaos matrix;
7. trace replay;
8. demo walkthrough;
9. security scan;
10. control tower.

Se tudo passar, o arquivo `runtime/reports/delivery_smoke/delivery_smoke_report.md`
consolida o resultado com comandos, tempos e artefatos.
