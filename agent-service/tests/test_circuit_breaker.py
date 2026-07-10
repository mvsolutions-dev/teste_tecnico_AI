from __future__ import annotations

import pytest

from app.circuit_breaker import CircuitBreaker, CircuitState
from app.quote_client import QuoteClient


def test_circuit_opens_after_threshold_and_closes_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)

    assert breaker.allow_request()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()

    assert breaker.state == CircuitState.OPEN
    assert not breaker.allow_request()

    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.consecutive_failures == 0


@pytest.mark.asyncio
async def test_quote_client_short_circuits_when_circuit_is_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    breaker.record_failure()
    client = QuoteClient("http://127.0.0.1:1", circuit_breaker=breaker)

    result = await client.quote(
        {"plano_id": "completo", "idade": 35, "veiculo_ano": 2022, "cep": "01310-100"}
    )

    assert result.status == "unavailable"
    assert "Circuit breaker aberto" in result.reason
    assert result.attempts[0].error == "circuit_open"
