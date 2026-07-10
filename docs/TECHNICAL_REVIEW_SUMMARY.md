# AutoSeguro AgentOps — Resumo Técnico de Revisão

## Resumo Executivo

AutoSeguro AgentOps é uma camada local de agente para o desafio de seguro auto. A
solução qualifica leads, chama o serviço legado `/quote`, lida com instabilidade do
legado de forma segura e produz evidências auditáveis por meio de testes, avaliação
com dataset, chaos testing e security scan.

Status técnico atual: **PASS**.

## Tese de Arquitetura

O agente foi desenhado como **LLM-first quando configurado** e
**deterministic-safe quando não configurado**.

- Com provider LLM, o agente interpreta mensagens livres, extrai slots estruturados,
  classifica intenção, identifica sinais comerciais e pode sugerir um rascunho de
  resposta mais consultivo.
- Sem provider LLM, o fluxo determinístico continua executável por qualquer avaliador
  sem chaves externas.
- Nos dois modos, decisões críticas continuam determinísticas: preço oficial só após
  cotação com sucesso, estimativas exigem validação humana, handoff é terminal e PII é
  redigida.

## Providers LLM

Providers implementados:

- `disabled`: provider seguro default, sem chamadas de rede.
- `fake`: provider determinístico para testes e smoke local.
- `openai`: OpenAI direto via configuração de ambiente.
- `azure_openai`: Azure OpenAI via configuração de ambiente.
- `openai_compatible`: suporte a endpoint compatível com OpenAI/Foundry.

A seleção é controlada por `AUTOSEGURO_LLM_PROVIDER`.

## Guardrails Críticos

O sistema evita:

- preço oficial sem `quote_status=success`;
- estimativa tratada como cotação oficial;
- resposta gerada por LLM com preço inventado;
- reabertura automática depois de handoff;
- vazamento de CPF, telefone, e-mail ou placa em logs/reports gerados;
- falha de LLM quebrando o caminho determinístico principal;
- falha do legado virando cotação falsa.

## Uso do Dataset

O dataset histórico de conversas é usado como evidência de engenharia, não como
memória textual bruta.

Ele alimenta:

- profiling do dataset;
- replay e avaliação sobre conversas históricas;
- cenários de aceite;
- chaos testing contra comportamento instável do legado;
- trace replay com estado redigido;
- security checks para artefatos gerados.

Essa abordagem reduz o risco de vazamento e evita ajustar o comportamento a exemplos
brutos sem rastreabilidade.

## Snapshot de Validação

Gates recentes:

| Gate | Status |
| --- | --- |
| pytest | PASS |
| ruff | PASS |
| smoke delivery fast | PASS |
| smoke delivery full | PASS |
| HTTP E2E smoke | PASS |
| LLM provider fake | PASS |
| OpenAI provider smoke | PASS quando env está configurado |
| Azure OpenAI provider smoke | PASS quando env está configurado |
| OpenAI-compatible provider smoke | SKIPPED quando env está ausente |

## Caminho de Revisão

Fluxo recomendado para avaliadores:

```bash
cd agent-service
python -m pip install -e ".[dev]"
python scripts/smoke_delivery.py --limit 250
```

Opcional:

```bash
python scripts/smoke_delivery.py --full
python scripts/http_e2e_smoke.py --start-services
python scripts/llm_provider_smoke.py --provider fake
```

Checks por provider podem ser executados depois de preencher variáveis de ambiente
locais:

```bash
python scripts/llm_provider_smoke.py --provider openai
python scripts/llm_provider_smoke.py --provider azure_openai
python scripts/llm_provider_smoke.py --provider openai_compatible
```

Nenhuma chave real é necessária para o smoke default.

## Prontidão Para Commit

O commit de entrega deve incluir:

- `README.md`
- `.gitignore`
- `docker-compose.yml`
- `.github/`
- `agent-service/`
- `docs/`
- `AGENTS.md`

Relatórios gerados em runtime, bancos locais, caches e arquivos `.env` locais devem
ficar fora do commit.

