# AutoSeguro - Agentic LLM Design

## Tese

O agente opera em dois modos:

- **LLM-first**, quando `AUTOSEGURO_LLM_PROVIDER` aponta para um provider configurado.
- **Deterministic-safe**, quando não há provider ou quando o provider falha.

Isso permite demonstrar uma experiência de agente premium sem transformar LLM em ponto
único de falha.

## Fluxo

```text
Mensagem do lead
  -> redação de PII / contexto seguro
  -> LLM provider opcional
      -> extracted_slots
      -> intent
      -> commercial_signals
      -> suggested_next_action
      -> reply_draft
  -> merge determinístico de slots
  -> guardrails de política
  -> quote_client ou pergunta objetiva ou handoff
  -> resposta final redigida no FlightRecorder
```

## Providers suportados

| Provider | Uso | Rede externa |
| --- | --- | --- |
| `disabled` | default seguro | não |
| `fake` | testes e smoke sem custo | não |
| `openai` | OpenAI direto | sim |
| `azure_openai` | Azure OpenAI | sim |
| `openai_compatible` | Foundry ou endpoint compatível | sim |

Factory:

```text
AUTOSEGURO_LLM_PROVIDER=disabled|fake|openai|azure_openai|openai_compatible|azure_foundry|auto
```

`auto` prioriza OpenAI-compatible/Foundry, depois Azure OpenAI, depois OpenAI direto e
por fim `disabled`.

## Contrato estruturado

O LLM deve retornar:

```json
{
  "extracted_slots": {
    "nome": null,
    "idade": null,
    "cep": null,
    "veiculo_texto": null,
    "veiculo_marca": null,
    "veiculo_modelo": null,
    "veiculo_ano": null,
    "plano_id": null,
    "data_inicio": null
  },
  "intent": "quote_request",
  "commercial_signals": {
    "price_objection": false,
    "competitor_mentioned": false,
    "urgency": false,
    "trust_concern": false
  },
  "suggested_next_action": "continue",
  "reply_draft": ""
}
```

O payload é validado com Pydantic. Se vier inválido, o agente usa fallback
determinístico.

## Guardrails

O LLM pode sugerir, mas não pode sozinho:

- inventar preço, franquia, cobertura ou desconto;
- tratar estimativa como cotação oficial;
- reabrir handoff;
- ignorar falha do legado;
- pular slot obrigatório;
- persistir PII crua em logs/reports.

`reply_draft` com marcadores de preço como `R$` é bloqueado antes de chegar ao lead.

## Como testar providers reais

```bash
cd agent-service
python scripts/llm_provider_smoke.py --list
python scripts/llm_provider_smoke.py --provider fake
python scripts/llm_provider_smoke.py --provider openai
python scripts/llm_provider_smoke.py --provider azure_openai
python scripts/llm_provider_smoke.py --provider openai_compatible
```

Sem envs, providers externos ficam `SKIPPED`. Com envs, o script valida JSON, latência
e schema sem imprimir chaves.

## Uso do dataset

O dataset não foi usado como few-shot bruto. Ele foi usado para:

- profiling de volume, PII, mídia e outcomes;
- desenho de slots e handoffs;
- eval suite em massa;
- chaos matrix com legado instável;
- trace replay redigido para auditoria.

## Fora de escopo

- Fine-tuning;
- memória vetorial com conversas brutas;
- transcrição real de mídia;
- deploy cloud;
- emissão de apólice.
