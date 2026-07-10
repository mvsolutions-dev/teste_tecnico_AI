# AutoSeguro AgentOps — Technical Review Summary

## Executive Summary

AutoSeguro AgentOps is a local, reviewer-friendly agent layer for the AutoSeguro take-home challenge. It qualifies insurance leads, calls the legacy `/quote` service, handles legacy instability safely and produces auditable evidence through tests, dataset evaluation, chaos testing and security scans.

Current technical status: **PASS**.

## Architecture Thesis

The agent is designed as **LLM-first when configured** and **deterministic-safe when not configured**.

- With an LLM provider, the agent interprets free-form messages, extracts structured slots, classifies intent, identifies commercial signals and can use a safer premium-style reply draft.
- Without an LLM provider, the deterministic flow remains fully runnable by any evaluator without API keys.
- In both modes, critical business decisions remain deterministic: official price only after quote success, estimates require human validation, handoff is terminal and PII is redacted.

## LLM Providers

Implemented providers:

- `disabled`: default safe provider, no network calls.
- `fake`: deterministic provider for tests and local smoke.
- `openai`: OpenAI direct through environment configuration.
- `azure_openai`: Azure OpenAI through environment configuration.
- `openai_compatible`: compatible endpoint support for Foundry-style deployments.

Selection is controlled by `AUTOSEGURO_LLM_PROVIDER`.

## Critical Guardrails

The system prevents:

- official prices without `quote_status=success`;
- treating estimates as official quotes;
- LLM-generated replies with invented prices;
- automatic reopening after handoff;
- raw CPF, phone, email or plate leakage in generated logs/reports;
- LLM failures breaking the main deterministic path;
- legacy failures turning into fake quotes.

## Dataset Usage

The historical conversation dataset is used as engineering evidence, not as raw few-shot prompt memory.

It powers:

- dataset profiling;
- replay/evaluation over historical conversations;
- acceptance scenarios;
- chaos testing against unstable legacy behavior;
- trace replay with redacted state;
- security checks for generated artifacts.

This avoids overfitting prompts to raw examples and reduces leakage risk.

## Validation Snapshot

Recent gates:

| Gate | Status |
| --- | --- |
| pytest | PASS |
| ruff | PASS |
| smoke delivery fast | PASS |
| smoke delivery full | PASS |
| HTTP E2E smoke | PASS |
| LLM provider fake | PASS |
| OpenAI provider smoke | PASS when env is configured |
| Azure OpenAI provider smoke | PASS when env is configured |
| OpenAI-compatible provider smoke | SKIPPED when env is absent |

## Review Path

Recommended reviewer flow:

```bash
cd agent-service
python -m pip install -e ".[dev]"
python scripts/smoke_delivery.py --limit 250
```

Optional:

```bash
python scripts/smoke_delivery.py --full
python scripts/http_e2e_smoke.py --start-services
python scripts/llm_provider_smoke.py --provider fake
```

Provider-specific checks can be run after filling local environment variables:

```bash
python scripts/llm_provider_smoke.py --provider openai
python scripts/llm_provider_smoke.py --provider azure_openai
python scripts/llm_provider_smoke.py --provider openai_compatible
```

No real keys are required for the default smoke.

## Commit Readiness

The intended commit should include:

- `README.md`
- `.gitignore`
- `docker-compose.yml`
- `.github/`
- `agent-service/`
- `docs/`

Generated runtime reports, local databases, caches and local `.env` files should remain outside the commit.
