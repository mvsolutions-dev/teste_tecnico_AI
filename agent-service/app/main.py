from __future__ import annotations

import os

from fastapi import FastAPI, Response

from .agent import AutoSeguroAgent
from .circuit_breaker import CircuitBreaker
from .config import load_default_env
from .extraction import LeadExtractor
from .models import ChatRequest, ChatResponse
from .quote_cache import QuoteCache
from .quote_client import QuoteClient
from .quote_estimator import QuoteEstimator
from .recorder import FlightRecorder
from .store import build_conversation_store


def create_app() -> FastAPI:
    load_default_env()
    quote_url = os.getenv("QUOTE_API_URL", "http://localhost:8000")
    recorder_path = os.getenv("FLIGHT_RECORDER_PATH", "runtime/logs/conversations.jsonl")
    agent = AutoSeguroAgent(
        quote_client=QuoteClient(
            quote_url,
            timeout_seconds=float(os.getenv("QUOTE_TIMEOUT_SECONDS", "3")),
            max_attempts=int(os.getenv("QUOTE_MAX_ATTEMPTS", "3")),
            circuit_breaker=CircuitBreaker(
                failure_threshold=int(os.getenv("QUOTE_CIRCUIT_FAILURE_THRESHOLD", "3")),
                cooldown_seconds=float(os.getenv("QUOTE_CIRCUIT_COOLDOWN_SECONDS", "10")),
            ),
            cache=QuoteCache(
                ttl_seconds=float(os.getenv("QUOTE_CACHE_TTL_SECONDS", "900")),
                stale_if_error_seconds=float(os.getenv("QUOTE_CACHE_STALE_IF_ERROR_SECONDS", "86400")),
            ),
            estimator=QuoteEstimator(),
        ),
        extractor=LeadExtractor(),
        recorder=FlightRecorder(recorder_path),
        store=build_conversation_store(),
    )

    app = FastAPI(
        title="AutoSeguro AgentOps",
        version="0.1.0",
        description="Agente conversacional auditavel para cotacao de seguro auto.",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, response: Response) -> ChatResponse:
        result = await agent.handle(
            req.conversation_id,
            req.message,
            sender_name=req.sender_name,
            message_type=req.message_type,
        )
        response.headers["X-Trace-Id"] = result.trace_id
        return result

    @app.get("/conversations/{conversation_id}")
    async def conversation_state(conversation_id: str) -> dict:
        state = agent.store.get(conversation_id)
        return state.model_dump(mode="json", exclude={"messages": {"__all__": {"content"}}})

    @app.get("/ops/metrics")
    async def ops_metrics() -> dict:
        return agent.metrics_snapshot()

    app.state.agent = agent
    return app


app = create_app()
