from __future__ import annotations

from pathlib import Path

import pytest

from app.models import QuoteResult
from scripts.run_eval_suite import InProcessQuoteClient


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_in_process_quote_client_uses_real_quote_logic() -> None:
    client = InProcessQuoteClient(
        quote_service_dir=REPO_ROOT / "quote-service",
        failure_rate=0,
        timeout_rate=0,
        max_attempts=2,
    )

    result = await client.quote(
        {
            "plano_id": "completo",
            "idade": 35,
            "veiculo_ano": 2022,
            "cep": "01310-100",
            "data_inicio": "2026-07-15",
        }
    )

    assert isinstance(result, QuoteResult)
    assert result.status == "success"
    assert result.quote
    assert result.quote["plano_nome"] == "Completo"
    assert result.quote["primeiro_pagamento_pro_rata"]["valor_primeiro_pagamento"] == 115.11
