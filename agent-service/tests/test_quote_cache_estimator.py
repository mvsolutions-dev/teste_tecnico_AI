from __future__ import annotations

import pytest

from app.models import QuoteResult
from app.quote_cache import QuoteCache, quote_cache_key
from app.quote_client import QuoteClient
from app.quote_estimator import QuoteEstimator


def test_quote_cache_key_does_not_store_full_cep() -> None:
    key = quote_cache_key(
        {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}
    )

    assert "01310-100" not in key
    assert "01310100" not in key
    assert '"cep_prefix":"01"' in key


def test_quote_estimator_marks_preliminary_and_validation_required() -> None:
    estimate = QuoteEstimator().estimate(
        {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}
    )

    assert estimate
    assert estimate["estimated"] is True
    assert estimate["requires_human_validation"] is True
    assert estimate["premio_mensal_estimado"] == 209.9


@pytest.mark.asyncio
async def test_quote_client_returns_fresh_cache_before_http_call() -> None:
    cache = QuoteCache()
    payload = {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}
    cache.set(payload, {"plano_nome": "Completo", "premio_mensal": 209.9})
    client = QuoteClient("http://127.0.0.1:1", cache=cache)

    result = await client.quote(payload)

    assert result.status == "success"
    assert result.quote["premio_mensal"] == 209.9
    assert result.attempts[0].status == "cache_hit"


@pytest.mark.asyncio
async def test_quote_client_returns_estimate_when_legacy_unavailable() -> None:
    client = QuoteClient(
        "http://127.0.0.1:1",
        timeout_seconds=0.01,
        max_attempts=1,
        estimator=QuoteEstimator(),
    )

    result = await client.quote(
        {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}
    )

    assert isinstance(result, QuoteResult)
    assert result.status == "estimated"
    assert result.quote
    assert result.quote["estimated"] is True
    assert result.attempts[-1].status == "estimate"
