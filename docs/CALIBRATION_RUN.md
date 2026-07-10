# Ciclo Autonomo de Calibragem

Data: 2026-07-09

## Hipotese inicial

A primeira versao funcionava, mas ainda parecia uma solução de endpoint. Para
subir a regua FDE/AI Engineer, o agente precisava usar melhor o dataset, deixar
as decisões auditaveis e provar comportamento sob instabilidade.

## Ajustes executados

1. **Azure OpenAI**
   - O extrator agora usa Azure OpenAI quando `AZURE_OPENAI_API_KEY` e
     `AZURE_OPENAI_ENDPOINT` existem.
   - `AZURE_DEPLOYMENT_MINI` tem prioridade como modelo de extração.
   - Se o LLM falhar, o fluxo cai para extração determinística e registra
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
   - Achado na arena instável: após handoff por indisponibilidade, mensagens
     futuras podiam reabrir cotação.
   - Corrigido: handoff agora é terminal e mensagens seguintes são anexadas ao
     contexto para o humano.

5. **Parsing de veículo**
   - Corrigido parser para não carregar intenção de plano dentro de `veiculo_texto`.
   - Exemplo: `Honda Civic de 2021 e queria o premium` vira `Honda Civic de 2021`.

## Validações

### Testes e lint

- `python -m pytest -q --basetemp .pytest-tmp`: `15 passed`
- após ajustes finais: `13+` evoluiu para `15 passed`
- `python -m ruff check .`: sem violações

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

### Arena instável calibrada

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

O agente passou de um fluxo simples de extração/cotação para uma entrega com:

- uso concreto do dataset;
- evals reprodutiveis;
- fallback LLM auditável;
- handoff terminal;
- metadados do canal usados corretamente;
- logs e estado redigidos.

## Próximos incrementos recomendados

- UI simples de trace/replay para demonstração.
- LLM-as-a-judge em amostras selecionadas para avaliar tom e qualidade de decisão.
- Persistência de estado em Redis/Postgres.

## Rodada adicional de 24h

Incremento implementado: `agent-service/scripts/run_eval_suite.py`.

O que mudou:

- avaliação in-process usando a mesma lógica de negócio do `quote-service`;
- cenário estavel com 2.500 conversas;
- cenário instável com falha/timeout simulados;
- gate automatico para:
  - violação de handoff terminal;
  - vazamento de PII não mascarada em trace persistido;
- relatório JSON e HTML.

Resultado:

- gate: `PASS`;
- 2.500 conversas em `2,288s`;
- `0` violações de handoff terminal;
- cobertura obrigatoria de slots em `100%`;
- relatório HTML gerado em `runtime/reports/eval_suite/eval_suite_report.html`.

Próximos incrementos restantes:

- UI simples de trace/replay para demonstração;
- LLM-as-a-judge em amostras selecionadas para avaliar tom e qualidade de decisão;
- persistência de estado em Redis/Postgres.
