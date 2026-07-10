from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any


def quote_cache_key(payload: dict[str, Any]) -> str:
    """Chave de cache sem PII desnecessaria.

    A regra de regiao usa apenas os dois primeiros digitos do CEP, entao nao
    armazenamos CEP completo na chave. O ano corrente entra porque a idade do
    veiculo depende de `date.today().year` no legado.
    """
    cep = str(payload.get("cep") or "").replace("-", "").strip()
    safe_payload = {
        "plano_id": payload.get("plano_id"),
        "idade": payload.get("idade"),
        "veiculo_ano": payload.get("veiculo_ano"),
        "cep_prefix": cep[:2] if cep else None,
        "data_inicio": payload.get("data_inicio"),
        "pricing_year": date.today().year,
    }
    return json.dumps(safe_payload, sort_keys=True, separators=(",", ":"))


@dataclass
class QuoteCacheEntry:
    quote: dict[str, Any]
    created_at: float
    key: str


@dataclass
class QuoteCache:
    ttl_seconds: float = 900.0
    stale_if_error_seconds: float = 86_400.0
    _items: dict[str, QuoteCacheEntry] = field(default_factory=dict)

    def get(self, payload: dict[str, Any], *, allow_stale: bool = False) -> dict[str, Any] | None:
        key = quote_cache_key(payload)
        entry = self._items.get(key)
        if not entry:
            return None
        age = time.monotonic() - entry.created_at
        if age <= self.ttl_seconds:
            return dict(entry.quote)
        if allow_stale and age <= self.stale_if_error_seconds:
            quote = dict(entry.quote)
            quote["cache_stale"] = True
            return quote
        return None

    def set(self, payload: dict[str, Any], quote: dict[str, Any]) -> None:
        key = quote_cache_key(payload)
        quote_copy = dict(quote)
        quote_copy["cache_key_version"] = "v1"
        self._items[key] = QuoteCacheEntry(quote=quote_copy, created_at=time.monotonic(), key=key)
