from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_chat_returns_trace_header_and_updates_metrics(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("FLIGHT_RECORDER_PATH", str(tmp_path / "events.jsonl"))
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/chat",
        json={
            "conversation_id": "ops-test",
            "message": "Quero cotar meu seguro.",
            "sender_name": "Ana Silva",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"]
    metrics = client.get("/ops/metrics").json()
    assert metrics["counters"]["conversations_started"] == 1
    assert metrics["counters"]["messages_received"] == 1
    assert metrics["counters"]["messages_sent"] == 1
    assert metrics["active_conversations"] == 1
