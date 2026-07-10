from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .circuit_breaker import CircuitBreaker
from .models import QuoteAttempt, QuoteResult
from .quote_cache import QuoteCache
from .quote_estimator import QuoteEstimator


class QuoteClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 3.0,
        max_attempts: int = 3,
        backoff_seconds: float = 0.35,
        circuit_breaker: CircuitBreaker | None = None,
        cache: QuoteCache | None = None,
        estimator: QuoteEstimator | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.circuit_breaker = circuit_breaker
        self.cache = cache
        self.estimator = estimator

    async def quote(self, payload: dict[str, Any]) -> QuoteResult:
        if self.cache:
            cached = self.cache.get(payload)
            if cached:
                return QuoteResult(
                    status="success",
                    quote=cached,
                    attempts=[
                        QuoteAttempt(
                            attempt=0,
                            status="cache_hit",
                            latency_ms=0,
                            error="fresh_cache",
                        )
                    ],
                )

        if self.circuit_breaker and not self.circuit_breaker.allow_request():
            return self._contingency_result(
                payload,
                "Circuit breaker aberto para o sistema legado de cotacao.",
                [
                    QuoteAttempt(
                        attempt=0,
                        status="failed",
                        latency_ms=0,
                        error="circuit_open",
                    )
                ],
            )

        attempts: list[QuoteAttempt] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(1, self.max_attempts + 1):
                started = time.perf_counter()
                try:
                    response = await client.post(f"{self.base_url}/quote", json=payload)
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    if response.status_code == 200:
                        attempts.append(
                            QuoteAttempt(
                                attempt=attempt,
                                status="success",
                                latency_ms=latency_ms,
                                http_status=200,
                            )
                        )
                        if self.circuit_breaker:
                            self.circuit_breaker.record_success()
                        if self.cache:
                            self.cache.set(payload, response.json())
                        return QuoteResult(status="success", quote=response.json(), attempts=attempts)
                    if response.status_code == 422:
                        body = response.json()
                        attempts.append(
                            QuoteAttempt(
                                attempt=attempt,
                                status="refused",
                                latency_ms=latency_ms,
                                http_status=422,
                                error=body.get("motivo") or body.get("error"),
                            )
                        )
                        if self.circuit_breaker:
                            self.circuit_breaker.record_success()
                        return QuoteResult(
                            status="refused",
                            reason=body.get("motivo") or "Cotacao recusada.",
                            attempts=attempts,
                        )
                    if response.status_code == 400:
                        body = response.json()
                        attempts.append(
                            QuoteAttempt(
                                attempt=attempt,
                                status="invalid",
                                latency_ms=latency_ms,
                                http_status=400,
                                error=body.get("detalhe") or body.get("error"),
                            )
                        )
                        if self.circuit_breaker:
                            self.circuit_breaker.record_success()
                        return QuoteResult(
                            status="invalid",
                            reason=body.get("detalhe") or "Payload invalido.",
                            attempts=attempts,
                        )

                    attempts.append(
                        QuoteAttempt(
                            attempt=attempt,
                            status="retryable_error",
                            latency_ms=latency_ms,
                            http_status=response.status_code,
                            error=response.text[:240],
                        )
                    )
                except httpx.TimeoutException:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    attempts.append(
                        QuoteAttempt(
                            attempt=attempt,
                            status="timeout",
                            latency_ms=latency_ms,
                            error=f"timeout after {self.timeout_seconds}s",
                        )
                    )
                except httpx.HTTPError as exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    attempts.append(
                        QuoteAttempt(
                            attempt=attempt,
                            status="failed",
                            latency_ms=latency_ms,
                            error=str(exc),
                        )
                    )

                if attempt < self.max_attempts:
                    await asyncio.sleep(self.backoff_seconds * attempt)

        if self.circuit_breaker:
            self.circuit_breaker.record_failure()
        return self._contingency_result(
            payload,
            "Servico de cotacao indisponivel apos tentativas com retry.",
            attempts,
        )

    def _contingency_result(
        self,
        payload: dict[str, Any],
        reason: str,
        attempts: list[QuoteAttempt],
    ) -> QuoteResult:
        if self.cache:
            cached = self.cache.get(payload, allow_stale=True)
            if cached:
                return QuoteResult(
                    status="success",
                    quote=cached,
                    reason=f"{reason} Resultado veio de cache stale.",
                    attempts=[
                        *attempts,
                        QuoteAttempt(
                            attempt=0,
                            status="cache_hit",
                            latency_ms=0,
                            error="stale_cache_after_error",
                        ),
                    ],
                )
        if self.estimator:
            estimate = self.estimator.estimate(payload)
            if estimate:
                return QuoteResult(
                    status="estimated",
                    quote=estimate,
                    reason=reason,
                    attempts=[
                        *attempts,
                        QuoteAttempt(
                            attempt=0,
                            status="estimate",
                            latency_ms=0,
                            error="preliminary_estimate_after_error",
                        ),
                    ],
                )
        return QuoteResult(
            status="unavailable",
            reason=reason,
            attempts=attempts,
        )
