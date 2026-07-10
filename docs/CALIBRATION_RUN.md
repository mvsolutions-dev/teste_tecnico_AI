# Ciclo Autonomo de Calibragem

Data: 2026-07-09

## Hipotese inicial

A primeira versao funcionava, mas ainda parecia uma solucao de endpoint. Para
subir a regua FDE/AI Engineer, o agente precisava usar melhor o dataset, deixar
as decisoes auditaveis e provar comportamento sob instabilidade.

## Ajustes executados

1. **Azure OpenAI**
   - O extrator agora usa Azure OpenAI quando `AZURE_OPENAI_API_KEY` e
     `AZURE_OPENAI_ENDPOINT` existem.
   - `AZURE_DEPLOYMENT_MINI` tem prioridade como modelo de extracao.
   - Se o LLM falhar, o fluxo cai para extracao deterministica e registra
     `llm_error_type`.

2. **Metadados do WhatsApp/dataset**
   - `POST /chat` aceita `sender_name` e `message_type`.
   - A Replay Arena passa `sender_name` e `message_type` do dataset.
   - `sender_name` preenche `lead.nome` quando disponivel.
   - `message_type=image|audio|document` aciona handoff mesmo sem marcador textual.

3. **Dataset completo**
   - `dataset_loader.py` le `conversations.parquet` via DuckDB.
   - Teste garante `26.470` mensagens e `2.500` conversas.

4. **Handoff terminal**
   - Achado na arena instavel: apos handoff por indisponibilidade, mensagens
     futuras podiam reabrir cotacao.
   - Corrigido: handoff agora e terminal e mensagens seguintes sao anexadas ao
     contexto para o humano.

5. **Parsing de veiculo**
   - Corrigido parser para nao carregar intencao de plano dentro de `veiculo_texto`.
   - Exemplo: `Honda Civic de 2021 e queria o premium` vira `Honda Civic de 2021`.

## Validacoes

### Testes e lint

- `python -m pytest -q --basetemp .pytest-tmp`: `15 passed`
- apos ajustes finais: `13+` evoluiu para `15 passed`
- `python -m ruff check .`: sem violacoes

### Smoke Azure

Mensagem:

```text
Me chamo Carlos Eduardo. Tenho trinta e cinco anos, moro no CEP 01310-100,
meu carro e um Honda Civic de 2021 e queria o premium.
```

Resultado:

```json
{
  "source": "deterministic+llm",
  "llm_error_type": null,
  "idade": 35,
  "veiculo_texto": "Honda Civic de 2021",
  "plano_id": "premium"
}
```

### Arena estavel calibrada

Comando: `replay_arena.py --limit 100` com `/quote` estavel.

- Dataset: parquet completo via DuckDB
- `quoted=30`
- `handoff=70`
- `quote_status.success=73`
- `quote_status.refused=27`
- cobertura:
  - `nome=100%`
  - `idade=100%`
  - `cep=100%`
  - `veiculo_ano=100%`
  - `plano_id=100%`

### Arena instavel calibrada

Comando: `replay_arena.py --limit 50` com `QUOTE_FAILURE_RATE=0.45`,
`QUOTE_SEED=7`.

- `quoted=10`
- `handoff=40`
- `quote_status.success=32`
- `quote_status.unavailable=13`
- `quote_status.refused=5`
- max quote attempts: `2`
- avg quote attempts: `1.52`

## Resultado

O agente passou de um fluxo simples de extracao/cotacao para uma entrega com:

- uso concreto do dataset;
- evals reprodutiveis;
- fallback LLM auditavel;
- handoff terminal;
- metadados do canal usados corretamente;
- logs e estado redigidos.

## Proximos incrementos recomendados

- UI simples de trace/replay para demonstracao.
- LLM-as-a-judge em amostras selecionadas para avaliar tom e qualidade de decisao.
- Persistencia de estado em Redis/Postgres.

## Rodada adicional de 24h

Incremento implementado: `agent-service/scripts/run_eval_suite.py`.

O que mudou:

- avaliacao in-process usando a mesma logica de negocio do `quote-service`;
- cenario estavel com 2.500 conversas;
- cenario instavel com falha/timeout simulados;
- gate automatico para:
  - violacao de handoff terminal;
  - vazamento de PII nao mascarada em trace persistido;
- relatorio JSON e HTML.

Resultado:

- gate: `PASS`;
- 2.500 conversas em `2,288s`;
- `0` violacoes de handoff terminal;
- cobertura obrigatoria de slots em `100%`;
- relatorio HTML gerado em `runtime/reports/eval_suite/eval_suite_report.html`.

Proximos incrementos restantes:

- UI simples de trace/replay para demonstracao;
- LLM-as-a-judge em amostras selecionadas para avaliar tom e qualidade de decisao;
- persistencia de estado em Redis/Postgres.
