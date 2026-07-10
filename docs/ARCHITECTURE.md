# AutoSeguro AgentOps - Arquitetura

## Objetivo

Construir um agente que conversa com leads de seguro auto, coleta os dados minimos,
cota no legado `/quote`, decide quando resolver sozinho e quando encaminhar para um
humano. O foco da implementacao e confiabilidade operacional, nao apenas texto bonito.

## Componentes

- `agent-service/app/main.py`: API FastAPI do agente.
- `agent-service/app/agent.py`: orquestracao da conversa e decisao de handoff.
- `agent-service/app/store.py`: store conversacional em memoria ou SQLite opcional.
- `agent-service/app/extraction.py`: extracao de slots deterministica com complemento
  opcional via camada LLM provider.
- `agent-service/app/llm/`: adapters `disabled`, `fake`, `openai`, `azure_openai`
  e `openai_compatible` para manter LLM-first quando configurado e deterministic-safe
  quando nao configurado.
- `agent-service/app/quote_client.py`: cliente resiliente do legado, com timeout,
  retry, backoff e classificacao de resultado.
- `agent-service/app/circuit_breaker.py`: protecao para nao martelar o legado
  quando falhas consecutivas indicam indisponibilidade.
- `agent-service/app/quote_cache.py`: cache de cotacoes reais com chave sem PII
  desnecessaria.
- `agent-service/app/quote_estimator.py`: estimativa preliminar para contingencia,
  sempre pendente de validacao humana.
- `agent-service/app/handoff_packet.py`: pacote operacional para o corretor humano.
- `agent-service/app/recorder.py`: flight recorder em JSONL com PII redigida.
- `agent-service/app/dataset_loader.py`: loader robusto do dataset via DuckDB,
  pandas ou `sample.jsonl`.
- `agent-service/scripts/profile_dataset.py`: profiling do historico de conversas.
- `agent-service/scripts/replay_arena.py`: replay das conversas contra o agente.
- `agent-service/scripts/run_acceptance_suite.py`: cenarios de aceite de produto.
- `agent-service/scripts/run_chaos_matrix.py`: matriz de resiliencia do legado.
- `agent-service/scripts/build_trace_replay.py`: replay HTML redigido com estado por turno.
- `agent-service/scripts/demo_walkthrough.py`: demo narrativa com quatro fluxos-chave.
- `agent-service/scripts/security_scan.py`: gate para PII crua em artefatos gerados.
- `agent-service/scripts/http_e2e_smoke.py`: smoke HTTP opcional entre agent e quote API.

## Diagrama

```mermaid
flowchart TD
    Lead[Lead / WhatsApp simulator] --> Chat[POST /chat]
    Chat --> State[Conversation State]
    Chat --> Store[Memory or SQLite Store]
    Chat --> Extractor[Slot Extractor deterministic + optional LLM Provider]
    Extractor --> Provider[disabled/fake/OpenAI/Azure/compatible]
    Extractor --> Decision{Enough data?}
    Decision -- No --> Ask[Ask next best question]
    Decision -- Yes --> QuoteClient[Resilient QuoteClient]
    QuoteClient --> Cache[Quote Cache without unnecessary PII]
    QuoteClient --> Breaker[Circuit Breaker]
    QuoteClient --> Legacy[/quote legacy service]
    Legacy -- success --> Official[Official Quote]
    Legacy -- refused --> Handoff[Human Handoff Packet]
    Legacy -- unavailable --> Estimate[Preliminary Estimate]
    Estimate --> Handoff
    Official --> Resolve{Accept / objection / reject?}
    Resolve --> Handoff
    Chat --> Recorder[Flight Recorder JSONL redacted]
    Recorder --> Trace[Trace Replay HTML]
    Recorder --> Security[Security Scan]
    Dataset[conversations.parquet] --> Eval[Eval Suite / Replay / Chaos]
```

## Estado

Cada conversa possui `conversation_id`, `trace_id`, status, mensagens redigidas,
slots do lead, resultado de cotacao e motivo de handoff. O estado fica em memoria
por default para o desafio local. Para demonstrar maturidade sem infra externa,
tambem existe `SQLiteConversationStore`, ativado com:

```text
AUTOSEGURO_STATE_STORE=sqlite
AUTOSEGURO_SQLITE_PATH=runtime/state/autoseguro.db
```

O SQLite salva uma copia redigida do estado: mensagens persistidas usam
`redacted_content` como `content`. O banco gerado fica em `runtime/state/` e nao
deve ser commitado.

O endpoint `POST /chat` tambem devolve `X-Trace-Id` no header para correlacionar
HTTP, logs JSONL e trace replay. O endpoint `GET /ops/metrics` expoe contadores
simples de operacao sem PII.

## Contratos de decisao

O agente so chama `/quote` quando possui:

- idade;
- ano do veiculo;
- CEP;
- plano.

Se o unico slot faltante for plano, o agente usa `Completo` como default
auditavel, registrando essa decisao em `observacoes` e no flight recorder.

## Handoff humano

O handoff e terminal e auditavel. Uma vez em handoff, mensagens seguintes nao
reabrem a cotacao automaticamente. O agente encaminha para humano quando:

- lead pede humano/corretor/atendente;
- chega audio, imagem ou documento sem transcricao;
- `/quote` recusa por regra de negocio;
- `/quote` fica indisponivel apos retries;
- lead traz objecao comercial apos cotacao.
- lead aceita a cotacao e precisa de emissao humana;
- lead recusa a proposta e deve ir para retencao ou registro de perda.

Cada handoff retorna `handoff_packet` com lead redigido, veiculo, contexto
comercial, quote, motivo, resumo e proxima melhor acao.

## Cache e estimativa

Quando `/quote` esta instavel, a ordem de contingencia e:

1. usar cache fresco de uma cotacao real para o mesmo perfil;
2. em erro do legado, aceitar cache stale dentro de janela controlada;
3. se nao houver cache, gerar uma estimativa preliminar;
4. encaminhar para humano se a resposta for estimada.

A estimativa nunca e tratada como preco oficial. Ela entra no `handoff_packet`
com `estimated=true` e `requires_human_validation=true`.

A chave de cache nao usa CPF, nome, telefone ou CEP completo. Como a regra de
preco usa apenas o prefixo de CEP, a chave guarda somente `cep_prefix`.

## Protecao de dados sensiveis

CPF, telefone, e-mail e placa sao mascarados antes de persistir logs. A resposta
HTTP pode expor estado redigido para debug, mas nao retorna conteudo bruto das
mensagens no campo `state`.

## LLM Provider Layer

O uso de LLM e opcional. `AUTOSEGURO_LLM_PROVIDER=disabled` e o default seguro.
Quando o avaliador configura OpenAI, Azure OpenAI ou endpoint OpenAI-compatible, o
extrator usa um contrato estruturado com:

- `extracted_slots`;
- `intent`;
- `commercial_signals`;
- `suggested_next_action`;
- `reply_draft`.

O LLM pode sugerir campos, intencao e tom de resposta, mas nao decide sozinho preco,
estimativa oficial, handoff terminal ou politica de fallback. Se provider falhar,
retornar JSON invalido ou estiver ausente, o fluxo deterministico continua.

Teste opcional:

```bash
cd agent-service
python scripts/llm_provider_smoke.py --list
python scripts/llm_provider_smoke.py --provider fake
python scripts/llm_provider_smoke.py --provider azure_openai
```

## Limites assumidos

- Estado em memoria, adequado ao take-home local.
- SQLite opcional e local, nao banco externo.
- Sem transcricao real de audio/imagem/documento; esses casos viram handoff.
- Sem emissao de apolice; a entrega para depois da cotacao e conceitual.
- Sem UI; a interface publica e HTTP.
