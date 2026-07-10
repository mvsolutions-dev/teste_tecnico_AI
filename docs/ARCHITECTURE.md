# AutoSeguro AgentOps - Arquitetura

## Objetivo

Construir um agente que conversa com leads de seguro auto, coleta os dados mínimos,
cota no legado `/quote`, decide quando resolver sozinho e quando encaminhar para um
humano. O foco da implementação é confiabilidade operacional, não apenas texto bonito.

## Componentes

- `agent-service/app/main.py`: API FastAPI do agente.
- `agent-service/app/agent.py`: orquestração da conversa e decisão de handoff.
- `agent-service/app/store.py`: store conversacional em memória ou SQLite opcional.
- `agent-service/app/extraction.py`: extração de slots determinística com complemento
  opcional via camada LLM provider.
- `agent-service/app/llm/`: adapters `disabled`, `fake`, `openai`, `azure_openai`
  e `openai_compatible` para manter LLM-first quando configurado e deterministic-safe
  quando não configurado.
- `agent-service/app/quote_client.py`: cliente resiliente do legado, com timeout,
  retry, backoff e classificação de resultado.
- `agent-service/app/circuit_breaker.py`: proteção para não martelar o legado
  quando falhas consecutivas indicam indisponibilidade.
- `agent-service/app/quote_cache.py`: cache de cotações reais com chave sem PII
  desnecessária.
- `agent-service/app/quote_estimator.py`: estimativa preliminar para contingência,
  sempre pendente de validação humana.
- `agent-service/app/handoff_packet.py`: pacote operacional para o corretor humano.
- `agent-service/app/recorder.py`: flight recorder em JSONL com PII redigida.
- `agent-service/app/dataset_loader.py`: loader robusto do dataset via DuckDB,
  pandas ou `sample.jsonl`.
- `agent-service/scripts/profile_dataset.py`: profiling do histórico de conversas.
- `agent-service/scripts/replay_arena.py`: replay das conversas contra o agente.
- `agent-service/scripts/run_acceptance_suite.py`: cenários de aceite de produto.
- `agent-service/scripts/run_chaos_matrix.py`: matriz de resiliência do legado.
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
slots do lead, resultado de cotação e motivo de handoff. O estado fica em memória
por default para o desafio local. Para demonstrar maturidade sem infra externa,
também existe `SQLiteConversationStore`, ativado com:

```text
AUTOSEGURO_STATE_STORE=sqlite
AUTOSEGURO_SQLITE_PATH=runtime/state/autoseguro.db
```

O SQLite salva uma cópia redigida do estado: mensagens persistidas usam
`redacted_content` como `content`. O banco gerado fica em `runtime/state/` e não
deve ser commitado.

O endpoint `POST /chat` também devolve `X-Trace-Id` no header para correlacionar
HTTP, logs JSONL e trace replay. O endpoint `GET /ops/metrics` expõe contadores
simples de operação sem PII.

## Contratos de decisão

O agente só chama `/quote` quando possui:

- idade;
- ano do veículo;
- CEP;
- plano.

Se o único slot faltante for plano, o agente usa `Completo` como default
auditável, registrando essa decisão em `observações` e no flight recorder.

## Handoff humano

O handoff é terminal e auditável. Uma vez em handoff, mensagens seguintes não
reabrem a cotação automaticamente. O agente encaminha para humano quando:

- lead pede humano/corretor/atendente;
- chega áudio, imagem ou documento sem transcrição;
- `/quote` recusa por regra de negócio;
- `/quote` fica indisponível após retries;
- lead traz objeção comercial após cotação.
- lead aceita a cotação e precisa de emissão humana;
- lead recusa a proposta e deve ir para retenção ou registro de perda.

Cada handoff retorna `handoff_packet` com lead redigido, veículo, contexto
comercial, quote, motivo, resumo e próxima melhor ação.

## Cache e estimativa

Quando `/quote` está instável, a ordem de contingência é:

1. usar cache fresco de uma cotação real para o mesmo perfil;
2. em erro do legado, aceitar cache stale dentro de janela controlada;
3. se não houver cache, gerar uma estimativa preliminar;
4. encaminhar para humano se a resposta for estimada.

A estimativa nunca é tratada como preço oficial. Ela entra no `handoff_packet`
com `estimated=true` e `requires_human_validation=true`.

A chave de cache não usa CPF, nome, telefone ou CEP completo. Como a regra de
preço usa apenas o prefixo de CEP, a chave guarda somente `cep_prefix`.

## Proteção de dados sensíveis

CPF, telefone, e-mail e placa são mascarados antes de persistir logs. A resposta
HTTP pode expor estado redigido para debug, mas não retorna conteúdo bruto das
mensagens no campo `state`.

## LLM Provider Layer

O uso de LLM é opcional. `AUTOSEGURO_LLM_PROVIDER=disabled` é o default seguro.
Quando o avaliador configura OpenAI, Azure OpenAI ou endpoint OpenAI-compatible, o
extrator usa um contrato estruturado com:

- `extracted_slots`;
- `intent`;
- `commercial_signals`;
- `suggested_next_action`;
- `reply_draft`.

O LLM pode sugerir campos, intenção e tom de resposta, mas não decide sozinho preço,
estimativa oficial, handoff terminal ou política de fallback. Se provider falhar,
retornar JSON inválido ou estiver ausente, o fluxo determinístico continua.

Teste opcional:

```bash
cd agent-service
python scripts/llm_provider_smoke.py --list
python scripts/llm_provider_smoke.py --provider fake
python scripts/llm_provider_smoke.py --provider azure_openai
```

## Limites assumidos

- Estado em memória, adequado ao take-home local.
- SQLite opcional e local, não banco externo.
- Sem transcrição real de audio/imagem/documento; esses casos viram handoff.
- Sem emissão de apólice; a entrega para depois da cotação é conceitual.
- Sem UI; a interface publica e HTTP.
