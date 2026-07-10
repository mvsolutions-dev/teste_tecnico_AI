# Roadmap de Evolução para Produção

## Objetivo

A entrega atual foi otimizada para avaliação local, reprodutibilidade e clareza dentro
do escopo do take-home. O objetivo deste documento é descrever como a solução evoluiria
para um ambiente de produção real, sem alterar os compromissos que já estão validados:
cotação oficial apenas via legado, handoff seguro, PII redigida e LLM opcional.

## Princípios de evolução

- Preservar o caminho simples de revisão local.
- Manter LLM opcional, seguro e protegido por validação determinística.
- Não permitir preço oficial sem cotação real.
- Manter handoff terminal.
- Manter PII redigida em logs, reports, debug e persistência.
- Tornar estado, cache e observabilidade independentes de memória local.
- Evoluir a operação por etapas, sem transformar a base em uma plataforma distribuída
  antes de existir necessidade real.

## O que já está pronto

- Agente conversacional com estado por `conversation_id`.
- Arquitetura LLM-first/deterministic-safe.
- Adapters LLM para `disabled`, `fake`, `openai`, `azure_openai` e
  `openai_compatible`.
- `QuoteClient` resiliente com timeout, retry, circuit breaker, cache e fallback de
  estimativa.
- `handoff_packet` estruturado para continuidade humana.
- `FlightRecorder` com PII redigida.
- Replay, Eval, Chaos Matrix e Security Scan.
- Smoke HTTP E2E entre `agent-service` e `quote-service`.
- Documentação de revisão com fast path para avaliadores.

## P0 — Produção local realista

### 1. Postgres para persistência de conversa

O primeiro passo seria substituir a dependência de memória local por Postgres como
fonte persistente de estado. A camada atual de `ConversationStore` já cria um ponto de
entrada natural para essa evolução.

Escopo recomendado:

- Persistir `ConversationState`.
- Persistir eventos do `FlightRecorder`.
- Persistir handoff e motivo de handoff.
- Separar estado operacional de auditoria.
- Criar migrações versionadas.
- Garantir que mensagens persistidas estejam redigidas, não em texto bruto com PII.

Trade-off: Postgres aumenta setup e operação, mas resolve restart, múltiplas instâncias
e auditoria de longo prazo. Para o take-home local, memória/SQLite eram suficientes e
mais fáceis de revisar.

### 2. Redis para responsabilidade operacional

Redis seria útil para dados temporários e coordenação entre instâncias.

Escopo recomendado:

- Cache distribuído de cotação real.
- Estado compartilhado do circuit breaker.
- Rate limit simples por lead/canal.
- Idempotência de requests com `conversation_id` e `trace_id`.
- TTLs explícitos para evitar retenção indevida.

Trade-off: Redis melhora resiliência e escala, mas também aumenta a superfície de PII.
Por isso, qualquer chave/valor em Redis deve evitar CPF, telefone, e-mail, placa e CEP
completo.

### 3. Docker Compose completo

A próxima versão local deveria subir a pilha de plataforma inteira:

- `agent-service`;
- `quote-service`;
- `postgres`;
- `redis`;
- healthchecks;
- smoke de plataforma.

Critério esperado:

```bash
docker compose up --build
```

deve subir a pilha, aguardar healthchecks e permitir um smoke que prove conversa,
cotação, handoff, persistência e cache.

### 4. Segurança

Segurança precisa continuar como invariante, não como etapa final.

Escopo recomendado:

- Secrets apenas por env ou secret manager.
- Scan de PII em banco, cache, logs e reports.
- Política de retenção de dados.
- Mascaramento em debug endpoints.
- Auditoria explícita para acesso a conversas.
- Separação entre payload operacional e payload redigido para observabilidade.

## P1 — Observabilidade e operação

A solução já expõe métricas simples em `/ops/metrics`. Em produção, isso evoluiria para
métricas Prometheus-compatible e dashboards operacionais.

Sinais recomendados:

- Volume de conversas iniciadas.
- Distribuição de `handoff_reason`.
- `quote_status`: `success`, `refused`, `invalid`, `unavailable`, `estimated`.
- Latência do legado `/quote`.
- Taxa de retry e timeout.
- Estado do circuit breaker.
- Uso de cache fresco e stale-if-error.
- Tracing por `trace_id`.
- Alertas para falha persistente do legado.

O objetivo não é apenas saber se a API está viva, mas entender quando a operação está
ficando menos confiável ou gerando handoff demais.

## P2 — Experiência e inteligência comercial

Depois de estabilizar estado e operação, a evolução natural seria melhorar a
experiência e a inteligência comercial.

Possíveis frentes:

- Transcrição de áudio, imagem e documentos.
- Classificação mais rica de objeções comerciais.
- Avaliação semântica de qualidade de atendimento.
- LLM-as-a-Judge em amostra controlada.
- A/B de instruções e estilo de resposta.
- Aprendizado a partir de outcomes: ganho, perdido, sem resposta, negociação.
- Recomendações de próxima melhor ação para o corretor humano.

Trade-off: essas frentes aumentam o potencial comercial, mas precisam de governança.
O LLM não deve decidir preço, cobertura ou elegibilidade sem validação determinística.

## P3 — Escala e confiabilidade

Em uma operação com maior volume, a arquitetura poderia evoluir para processamento
assíncrono e releases mais seguros.

Escopo recomendado:

- Workers assíncronos para tarefas demoradas.
- Fila/outbox para eventos de handoff, transcrição e reprocessamento.
- Retry de tarefas com backoff.
- Testes de carga.
- Suporte a múltiplas instâncias.
- Blue/green ou canary.
- Observabilidade centralizada.
- Gestão de custo e latência por provider LLM.

Trade-off: filas e workers aumentam robustez, mas também criam complexidade de
consistência, idempotência e troubleshooting. A adoção deve ser guiada por volume real.

## Decisões deliberadas do take-home

- **Postgres/Redis não estão no caminho crítico atual**: a entrega prioriza clareza,
  execução local e validação objetiva. A arquitetura já deixa pontos de extensão para
  persistência e cache distribuído.
- **O smoke default roda sem chave de LLM**: isso garante que qualquer avaliador consiga
  testar a solução sem depender de credenciais externas ou disponibilidade de provider.
- **O dataset não foi usado como exemplos brutos para o modelo**: o dataset virou
  profiling, replay, avaliação e chaos testing. Isso reduz risco de vazamento e evita
  acoplar comportamento a exemplos sensíveis.
- **Mídia sem transcrição vira handoff**: sem transcrição confiável, o sistema preserva
  segurança e continuidade humana em vez de fingir que entendeu o anexo.
- **Segurança vem antes de fechamento agressivo**: o agente não inventa preço, não
  reabre handoff terminal e não trata estimativa como cotação oficial.

## Critérios de aceite para a próxima fase

- `docker compose up --build` sobe `agent-service`, `quote-service`, `postgres` e
  `redis`.
- Platform smoke passa de ponta a ponta.
- Estado de conversa persiste após restart do `agent-service`.
- Redis não contém CPF, telefone, e-mail, placa ou CEP completo.
- Security scan passa contra logs, reports, banco e cache.
- Full smoke continua verde.
- HTTP E2E continua verde.
- README mantém um fast path simples para revisão local.
- Migrações de banco são versionadas e reproduzíveis.
- Handoff continua terminal.
- Estimativa continua marcada como não oficial e pendente de validação humana.

## Conclusão

A entrega atual resolve o desafio localmente com foco em segurança, rastreabilidade e
reprodutibilidade. A evolução descrita aqui transformaria a solução em uma plataforma
operacional mais próxima de produção, sem sacrificar os invariantes que tornam o agente
confiável: preço oficial apenas com cotação real, handoff seguro, PII redigida e LLM
sempre subordinado a validações determinísticas.
