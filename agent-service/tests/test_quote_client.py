import httpx
import pytest

from app.quote_client import QuoteClient


@pytest.mark.asyncio
async def test_quote_client_retries_legacy_failure_then_succeeds(monkeypatch) -> None:
    calls = {"count": 0}

    async def fake_post(self, url, json):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": "upstream_unavailable"})
        return httpx.Response(200, json={"plano_nome": "Completo", "premio_mensal": 209.9})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = QuoteClient("http://quote.test", timeout_seconds=0.1, max_attempts=2, backoff_seconds=0)

    result = await client.quote({"plano_id": "completo", "idade": 35, "veiculo_ano": 2022})

    assert result.status == "success"
    assert calls["count"] == 2
    assert result.attempts[0].status == "retryable_error"


@pytest.mark.asyncio
async def test_quote_client_returns_unavailable_after_failures(monkeypatch) -> None:
    async def fake_post(self, url, json):  # noqa: ANN001
        return httpx.Response(503, json={"error": "upstream_unavailable"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = QuoteClient("http://quote.test", timeout_seconds=0.1, max_attempts=2, backoff_seconds=0)

    result = await client.quote({"plano_id": "completo", "idade": 35, "veiculo_ano": 2022})

    assert result.status == "unavailable"
    assert len(result.attempts) == 2

