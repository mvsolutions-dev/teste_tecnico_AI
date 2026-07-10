# AutoSeguro AgentOps — Guia do Repositório

## Objetivo

Este repositório contém um agente de atendimento para seguro auto. O agente conversa
com leads, coleta dados mínimos, chama uma API legada de cotação, decide quando
consegue seguir sozinho e realiza handoff humano quando necessário. A entrega também
inclui rastreabilidade, proteção de PII e avaliação com dataset histórico.

## Arquitetura em Uma Visão

- `quote-service/`: serviço legado local de cotação.
- `agent-service/app/main.py`: API FastAPI do agente.
- `agent-service/app/agent.py`: orquestração da conversa, decisão de cotação e handoff.
- `agent-service/app/extraction.py`: extração de slots com fallback determinístico e LLM opcional.
- `agent-service/app/llm/`: providers LLM (`disabled`, `fake`, `openai`, `azure_openai`, `openai_compatible`).
- `agent-service/app/quote_client.py`: cliente resiliente do `/quote`.
- `agent-service/app/handoff_packet.py`: pacote estruturado para o corretor humano.
- `agent-service/app/recorder.py`: flight recorder redigido.
- `agent-service/scripts/`: suítes de avaliação, smoke, chaos, trace e security scan.
- `docs/`: documentação técnica e guia de revisão.

## Invariantes Principais

1. Preço oficial só pode aparecer quando `quote_status == "success"`.
2. Falha persistente do legado deve virar handoff, não preço inventado.
3. Estimativa nunca é cotação oficial.
4. Handoff é terminal.
5. CPF, telefone, e-mail e placa devem ser redigidos em logs, reports, debug e store.
6. LLM é opcional; o smoke default deve rodar sem chave.
7. O dataset deve ser usado para avaliação, profiling e replay, não como exemplos brutos com PII.

## Notas Sobre Providers LLM

- `disabled`: default seguro sem chave.
- `fake`: provider determinístico para testes sem rede.
- `openai`: provider OpenAI direto.
- `azure_openai`: provider Azure OpenAI.
- `openai_compatible`: endpoint Foundry ou compatível com OpenAI.

O LLM pode sugerir extração, intenção, sinais comerciais e rascunho de resposta.
Decisões críticas continuam validadas por código determinístico.

## Fluxo Seguro de Desenvolvimento

```bash
cd agent-service
python -m pytest -q --basetemp .pytest-tmp
python -m ruff check .
python scripts/smoke_delivery.py --limit 250
python scripts/llm_provider_smoke.py --provider fake
```

Validações opcionais:

```bash
python scripts/http_e2e_smoke.py --start-services --output-dir runtime/reports/http_e2e_started
python scripts/smoke_delivery.py --full
```

## Onde Alterar

- Conversa e decisão: `agent-service/app/agent.py`
- Extração: `agent-service/app/extraction.py`
- Providers LLM: `agent-service/app/llm/`
- Cotação e resiliência: `agent-service/app/quote_client.py`
- PII: `agent-service/app/pii.py` e `agent-service/scripts/security_scan.py`
- Avaliação: `agent-service/scripts/`

## Não Commitar

- `.env`
- `runtime/`
- `.pytest-tmp/`
- caches
- `__pycache__/`
- `*.pyc`
- `*.db`
- `*.sqlite`
- relatórios gerados
- chaves de API
- segredos

## Caminho Rápido Para Avaliação

Para instruções de revisão, comece por `README.md` e depois consulte
`docs/REVIEW_GUIDE.md`.

## Nota Final

Ao alterar este repositório, prefira mudanças pequenas, testáveis e que preservem os
invariantes de segurança acima.

