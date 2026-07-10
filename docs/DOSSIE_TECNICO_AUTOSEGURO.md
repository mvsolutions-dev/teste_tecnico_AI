# Dossie Tecnico - AutoSeguro AgentOps

Este documento resume o desafio tecnico, o que foi implementado, como a solucao
se encaixa nos criterios de avaliacao e quais seriam os proximos passos para
chegar o mais perto possivel de uma entrega 10/10 sem deploy em nuvem.

## 1. O que e o desafio tecnico

O desafio simula o trabalho de um FDE / AI Engineer em um contexto realista:
uma seguradora ficticia, a AutoSeguro, atende leads por WhatsApp e precisa de um
agente que qualifique o cliente, colete dados minimos, chame uma API de cotacao
e decida quando resolver sozinho ou transferir para um humano.

O repo original entrega tres insumos:

- `quote-service/`: API HTTP com `POST /quote`, `GET /health` e `GET /planos`.
- `dataset/conversations.parquet`: cerca de 2.500 conversas lead-vendedor.
- `dataset/DICIONARIO.md`: dicionario do dataset.

O ponto mais importante do desafio nao e criar apenas um chatbot. A avaliacao
valoriza:

- funcionamento ponta a ponta;
- comportamento quando a API de cotacao falha;
- criterio claro para handoff humano;
- rastreabilidade de mensagens, cotacoes e decisoes;
- cuidado com dados sensiveis;
- qualidade de codigo e documentacao.

## 2. Como a solucao responde ao que o desafio pede

| Criterio do desafio | O que foi entregue | Evidencia no repo |
| --- | --- | --- |
| Conversar com o lead | Endpoint `POST /chat` com estado por conversa | `agent-service/app/main.py`, `agent-service/app/agent.py` |
| Qualificar dados minimos | Extracao de idade, CEP, veiculo/ano, plano, data de inicio e PII mascarada | `agent-service/app/extraction.py`, `agent-service/app/models.py` |
| Operar como agente LLM-first | Provider adapters opcionais para OpenAI, Azure OpenAI e OpenAI-compatible, com fallback deterministico | `agent-service/app/llm/`, `agent-service/scripts/llm_provider_smoke.py` |
| Cotar via API | `QuoteClient` chama `/quote` e classifica resposta | `agent-service/app/quote_client.py` |
| Nao inventar preco | Preco oficial so aparece com `quote_status=success` | `agent-service/app/agent.py`, tests |
| Lidar com legado instavel | Retry, timeout, backoff, circuit breaker, cache e estimativa preliminar | `quote_client.py`, `circuit_breaker.py`, `quote_cache.py`, `quote_estimator.py` |
| Handoff defensavel | Motivos explicitos e `handoff_packet` estruturado | `handoff_packet.py`, `agent.py` |
| Rastreabilidade | `trace_id`, `X-Trace-Id`, Flight Recorder, Trace Replay HTML | `recorder.py`, `build_trace_replay.py`, `/ops/metrics` |
| Dados sensiveis | Mascaramento de CPF, telefone, e-mail e placa + security scan | `pii.py`, `security_scan.py` |
| Uso do dataset | Profile, eval suite, acceptance suite e chaos matrix | `scripts/profile_dataset.py`, `scripts/run_eval_suite.py`, `scripts/run_acceptance_suite.py`, `scripts/run_chaos_matrix.py` |
| Avaliacao simples pelo revisor | Smoke unico e Review Guide | `scripts/smoke_delivery.py`, `docs/REVIEW_GUIDE.md` |

## 3. Arquitetura em alto nivel

```text
Lead / avaliador
  |
  v
FastAPI agent-service
  |
  +-- Agent state por conversation_id
  +-- LeadExtractor deterministico + LLM provider opcional
  +-- QuoteClient resiliente
  |     +-- retry/backoff
  |     +-- circuit breaker
  |     +-- cache sem PII desnecessaria
  |     +-- estimativa preliminar se legado cair
  |
  +-- FlightRecorder JSONL com PII redigida
  +-- HandoffPacket para corretor humano
  +-- Ops metrics / trace id

quote-service
  |
  +-- /quote com regras reais e instabilidade simulada
```

## 4. Como rodar como avaliador

Fluxo recomendado para um avaliador clonar e testar localmente:

```bash
git clone <repo-publico>
cd namastex-fde-challenge/agent-service
python -m pip install -e ".[dev]"
python scripts/smoke_delivery.py --full
```

Artefatos principais gerados:

```text
runtime/reports/delivery_smoke/control_tower.html
runtime/reports/delivery_smoke/trace_replay.html
runtime/reports/delivery_smoke/eval_suite/eval_suite_report.html
runtime/reports/delivery_smoke/acceptance/acceptance_report.html
runtime/reports/delivery_smoke/chaos_matrix/chaos_matrix_report.html
runtime/reports/delivery_smoke/demo_walkthrough/demo_walkthrough.html
runtime/reports/delivery_smoke/security_scan/security_scan_report.html
```

Para rodar o agente via HTTP:

```bash
docker compose up --build
```

Ou em dois terminais:

```bash
cd quote-service
uv run uvicorn app.main:app --port 8000
```

```bash
cd agent-service
python -m pip install -e ".[dev]"
uvicorn app.main:app --port 8010
```

Teste rapido:

```bash
curl -X POST localhost:8010/chat \
  -H "content-type: application/json" \
  -d '{
    "conversation_id": "demo-001",
    "message": "Sou Ana, tenho 35 anos, CEP 01310-100. Meu carro e um Corolla 2022 e quero completo com inicio em 2026-07-15."
  }'
```

O `POST /chat` devolve `X-Trace-Id` no header. Para metricas:

```bash
curl localhost:8010/ops/metrics
```

## 5. Variaveis de ambiente para o avaliador

O sistema funciona sem chave de LLM usando extracao deterministica. Se o avaliador
quiser testar o complemento por LLM, basta preencher `.env` em `agent-service/`
usando `.env.example` como base.

Variaveis aceitas:

```text
QUOTE_API_URL=http://localhost:8000
QUOTE_TIMEOUT_SECONDS=3
QUOTE_MAX_ATTEMPTS=3
QUOTE_CIRCUIT_FAILURE_THRESHOLD=3
QUOTE_CIRCUIT_COOLDOWN_SECONDS=10
QUOTE_CACHE_TTL_SECONDS=900
QUOTE_CACHE_STALE_IF_ERROR_SECONDS=86400

AUTOSEGURO_LLM_PROVIDER=disabled
AUTOSEGURO_LLM_TIMEOUT_SECONDS=8

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_DEPLOYMENT_MINI=

OPENAI_COMPATIBLE_API_KEY=
OPENAI_COMPATIBLE_BASE_URL=
OPENAI_COMPATIBLE_MODEL=
```

Nenhuma chave real deve ser commitada.

Smoke opcional de provider:

```bash
cd agent-service
python scripts/llm_provider_smoke.py --list
python scripts/llm_provider_smoke.py --provider fake
python scripts/llm_provider_smoke.py --provider azure_openai
```

Sem envs reais, providers externos ficam `SKIPPED` e nao quebram o smoke principal.

## 6. Trechos de codigo relevantes

### 6.1 Handoff terminal

O agente nao reabre fluxo de cotacao depois que decidiu passar para humano:

```python
if state.status == AgentStatus.HANDOFF:
    reply = (
        "Seu atendimento ja esta encaminhado para um especialista humano. "
        "Vou manter esta nova mensagem no contexto para ele continuar sem perda de historico."
    )
    return self._respond(state, reply)
```

Arquivo: `agent-service/app/agent.py`

### 6.2 Nao inventar preco

O fluxo so gera resposta com preco quando `quote_result.status == "success"`:

```python
quote_result = await self.quote_client.quote(state.lead.quote_payload())
state.quote_result = quote_result

if quote_result.status == "success":
    state.status = AgentStatus.QUOTED
    reply = self._quote_success_reply(quote_result)
elif quote_result.status == "estimated":
    reply = self._handoff(
        state,
        "legado indisponivel; estimativa preliminar gerada para validacao humana",
    )
elif quote_result.status == "refused":
    reply = self._handoff(state, f"cotacao recusada: {quote_result.reason}")
elif quote_result.status == "invalid":
    reply = self._handoff(state, f"payload invalido para cotacao: {quote_result.reason}")
else:
    reply = self._handoff(state, "sistema legado de cotacao indisponivel apos retries")
```

Arquivo: `agent-service/app/agent.py`

### 6.3 Cliente resiliente do legado

Retry, classificacao de erro, cache e contingencia ficam encapsulados no cliente:

```python
async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
    for attempt in range(1, self.max_attempts + 1):
        try:
            response = await client.post(f"{self.base_url}/quote", json=payload)
            if response.status_code == 200:
                if self.cache:
                    self.cache.set(payload, response.json())
                return QuoteResult(status="success", quote=response.json(), attempts=attempts)
            if response.status_code == 422:
                return QuoteResult(status="refused", reason=body.get("motivo"), attempts=attempts)
        except httpx.TimeoutException:
            attempts.append(QuoteAttempt(..., status="timeout", ...))

return self._contingency_result(payload, "Servico de cotacao indisponivel apos tentativas com retry.", attempts)
```

Arquivo: `agent-service/app/quote_client.py`

### 6.4 Cache sem PII desnecessaria

O cache nao usa nome, CPF, telefone nem CEP completo:

```python
safe_payload = {
    "plano_id": payload.get("plano_id"),
    "idade": payload.get("idade"),
    "veiculo_ano": payload.get("veiculo_ano"),
    "cep_prefix": cep[:2] if cep else None,
    "data_inicio": payload.get("data_inicio"),
    "pricing_year": date.today().year,
}
```

Arquivo: `agent-service/app/quote_cache.py`

### 6.5 PII masking

O scanner falha se encontrar PII crua em logs/relatorios gerados:

```python
FAIL_PATTERNS = {
    "raw_cpf_formatted": CPF_FORMATTED_RE,
    "raw_cpf_unformatted": CPF_UNFORMATTED_RE,
    "raw_email": EMAIL_RE,
    "raw_phone": PHONE_RE,
    "raw_plate": PLATE_RE,
}

return {
    "gate": "PASS" if not failures else "FAIL",
    "scanned_files": len(files),
    "failure_count": len(failures),
}
```

Arquivo: `agent-service/scripts/security_scan.py`

### 6.6 Smoke unico de entrega

O avaliador roda um comando e recebe os principais gates:

```python
"gate": "PASS"
if (
    not failed
    and eval_report.get("gate") == "PASS"
    and acceptance_report.get("gate") == "PASS"
    and chaos_report.get("gate") == "PASS"
    and demo_report.get("gate") == "PASS"
    and security_report.get("gate") == "PASS"
)
else "FAIL"
```

Arquivo: `agent-service/scripts/smoke_delivery.py`

## 7. Exemplos de conversas geradas pelo sistema

Os exemplos abaixo sairam de:

```text
runtime/reports/delivery_smoke/demo_walkthrough/demo_walkthrough.json
```

### 7.1 Caminho feliz: cotacao oficial

Lead:

```text
Oi, sou a Ana. Tenho 35 anos, CPF ***.083.863-**, CEP 01310-100. Meu carro e um Corolla 2022 e quero o plano completo com inicio em 2026-07-15.
```

Agente:

```text
Consegui cotar o plano Completo por R$ 209.90/mes. Franquia: R$ 3000. Coberturas: colisao, roubo, furto, terceiros, vidros Roubo/furto tem carencia de 30 dias, conforme regra do plano. Como a vigencia comeca no meio do mes, o primeiro pagamento fica proporcional: R$ 115.11. Quer seguir com esse plano ou prefere falar com um especialista?
```

Resultado:

```text
status=quoted
quote_status=success
```

### 7.2 Legado indisponivel: retry e handoff seguro

Lead:

```text
Tenho 41 anos, CEP 01310-100, carro T-Cross 2021, quero plano premium.
```

Agente:

```text
Vou encaminhar para um especialista humano com o contexto que ja coletei. Motivo: sistema legado de cotacao indisponivel apos retries. Assim evitamos travar seu atendimento ou passar uma cotacao insegura.
```

Resultado:

```text
status=handoff
quote_status=unavailable
handoff_reason=sistema legado de cotacao indisponivel apos retries
```

Trecho do pacote de handoff:

```json
{
  "lead": {
    "nome": "Bruno Rocha",
    "idade": 41,
    "cep": "01310-100"
  },
  "vehicle": {
    "texto": "T-Cross 2021",
    "ano": 2021
  },
  "quote": {
    "status": "unavailable",
    "attempts": [
      {"attempt": 1, "status": "retryable_error", "http_status": 503},
      {"attempt": 2, "status": "retryable_error", "http_status": 503}
    ]
  },
  "next_best_action": "Validar a estimativa/reprocessar cotacao quando o legado estabilizar e avisar o lead."
}
```

### 7.3 Midia sem transcricao: passa para humano

Lead:

```text
[documento] CNH_frente.pdf
```

Agente:

```text
Vou encaminhar para um especialista humano com o contexto que ja coletei. Motivo: lead enviou midia sem conteudo textual suficiente. Assim evitamos travar seu atendimento ou passar uma cotacao insegura.
```

Resultado:

```text
status=handoff
handoff_reason=lead enviou midia sem conteudo textual suficiente
```

### 7.4 Objecao comercial apos cotacao

Lead:

```text
Tenho 35 anos, CEP 01310-100, carro Corolla 2022, plano completo.
```

Agente:

```text
Consegui cotar o plano Completo por R$ 209.90/mes. Franquia: R$ 3000. Coberturas: colisao, roubo, furto, terceiros, vidros Roubo/furto tem carencia de 30 dias, conforme regra do plano. Quer seguir com esse plano ou prefere falar com um especialista?
```

Lead:

```text
Achei caro, o concorrente me ofereceu menos.
```

Agente:

```text
Vou encaminhar para um especialista humano com o contexto que ja coletei. Motivo: lead trouxe negociacao ou objecao comercial apos cotacao. Assim evitamos travar seu atendimento ou passar uma cotacao insegura.
```

Resultado:

```text
status=handoff
quote_status=success
handoff_reason=lead trouxe negociacao ou objecao comercial apos cotacao
```

## 8. Evidencias de validacao atual

Ultima rodada local:

```text
pytest: 36 passed, 1 warning
ruff: All checks passed
smoke_delivery --full: PASS
eval_gate: PASS
acceptance_gate: PASS
chaos_gate: PASS
demo_gate: PASS
security_gate: PASS
eval_conversations: 2500
```

O warning atual vem de `fastapi.testclient` / Starlette sobre `httpx`; nao e falha
funcional do projeto.

## 9. Como os relatorios ajudam a banca

| Relatorio | Pergunta que responde |
| --- | --- |
| `control_tower.html` | "Qual e o status executivo da entrega?" |
| `trace_replay.html` | "Da para rastrear uma conversa real por turno?" |
| `eval_suite_report.html` | "O agente segura o dataset completo?" |
| `acceptance_report.html` | "Os cenarios de negocio essenciais passam?" |
| `chaos_matrix_report.html` | "O que acontece quando a API falha muito?" |
| `demo_walkthrough.html` | "Como eu demonstro isso em 3 minutos?" |
| `security_scan_report.html` | "Ha PII crua vazando em logs/relatorios?" |
| `http_e2e_report.html` | "A integracao HTTP real entre agent e quote API funciona localmente?" |

## 10. Proximos passos para aproximar de 10/10 sem deploy

Nao vamos fazer deploy em Azure. Considerando que a entrega sera um repo publico
para o avaliador clonar e preencher envs, os pontos de maior impacto ficaram assim:

### Fechado nesta versao

1. **README reviewer-first**
   - O README abre com o fast path de 10 minutos, artefatos a abrir e decisoes
     centrais.

2. **E2E HTTP local opcional**
   - `agent-service/scripts/http_e2e_smoke.py` valida `quote-service` e
     `agent-service` via HTTP real, com `X-Trace-Id` e report JSON/HTML.

3. **Persistencia SQLite opcional**
   - `AUTOSEGURO_STATE_STORE=sqlite` ativa `SQLiteConversationStore`.
   - O payload persistido usa mensagens redigidas, nao texto bruto com PII.

4. **Normalizacao de veiculo**
   - `veiculo_texto` agora tende a sair como `Toyota Corolla 2022`,
     `Volkswagen T-Cross 2021`, `Honda Civic 2020`, etc.
   - `veiculo_marca` e `veiculo_modelo` foram adicionados mantendo compatibilidade
     com os campos antigos.

5. **LLM Judge opcional no delivery smoke**
   - Comando:

   ```bash
   python scripts/smoke_delivery.py --limit 250 --include-llm-judge
   ```

   Sem envs, o report fica `skipped` e nao quebra o gate principal.

6. **Makefile e PowerShell runner**
   - `make smoke`, `make test`, `make lint`.
   - `scripts/dev.ps1 smoke` para Windows.

### Ainda opcional para uma versao futura

1. **Rodada fresh clone local**
   - Clonar o proprio repo em outra pasta e rodar:

   ```bash
   cd agent-service
   python -m pip install -e ".[dev]"
   python scripts/smoke_delivery.py --full
   ```

   Isso simula a banca e pega dependencia faltando.

2. **Gravar GIF ou screenshots dos HTMLs**
   - Sem deploy, uma evidencia visual no README pode aumentar muito a percepcao.
   - Pode ser uma imagem do `control_tower.html` e do `demo_walkthrough.html`.

3. **Persistencia multiusuario real**
   - SQLite e suficiente para o take-home local.
   - Em producao, a evolucao natural seria Postgres/Redis com isolamento de tenant.

11. **Arquitetura em diagrama Mermaid**
   - Incluir no README ou `ARCHITECTURE.md`.
   - Ajuda leitura rapida por CTO/tech lead.

## 11. Veredito atual

A entrega atual esta acima do minimo do desafio. Ela nao e apenas um chatbot;
ela funciona como uma camada de AgentOps para atendimento comercial com legado
instavel:

- agente conversacional;
- cotacao real;
- resiliencia operacional;
- handoff seguro;
- PII masking;
- avaliacao em massa;
- chaos testing;
- acceptance testing;
- demo visual;
- trace replay;
- control tower;
- security scan.

Sem deploy, o caminho para uma nota maxima e garantir que o revisor consiga
clonar, preencher envs opcionais, rodar um comando e enxergar evidencias
objetivas em poucos minutos.
