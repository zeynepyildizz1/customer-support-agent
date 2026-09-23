import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_routine_ticket_completes_immediately(client, mock_llm_routine):
    resp = await client.post("/tickets", json={"message": "ORD-10432 kargo durumu nedir"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["response"] is not None


@pytest.mark.asyncio
async def test_risky_ticket_goes_to_pending(client, mock_llm_risky):
    resp = await client.post("/tickets", json={"message": "ORD-10432 iade istiyorum yoksa hakeme giderim"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_approval"
    assert body["ticket_id"] is not None


@pytest.mark.asyncio
async def test_full_hitl_flow_resume_after_pending(client, mock_llm_risky):
    resp1 = await client.post("/tickets", json={"message": "ORD-10432 iade istiyorum yoksa hakeme giderim"})
    ticket_id = resp1.json()["ticket_id"]
    assert resp1.json()["status"] == "pending_approval"

    resp2 = await client.post(f"/tickets/{ticket_id}/resume", json={"decision": "approve", "note": "test onayı"})
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "completed"
    assert "onaylandı" in resp2.json()["response"]


@pytest.mark.asyncio
async def test_double_resume_returns_409(client, mock_llm_risky):
    resp1 = await client.post("/tickets", json={"message": "ORD-10432 iade istiyorum yoksa hakeme giderim"})
    ticket_id = resp1.json()["ticket_id"]

    await client.post(f"/tickets/{ticket_id}/resume", json={"decision": "approve"})
    resp2 = await client.post(f"/tickets/{ticket_id}/resume", json={"decision": "approve"})

    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_resume_with_invalid_ticket_id_returns_404(client):
    resp = await client.post("/tickets/nonexistent-id-123/resume", json={"decision": "approve"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_message_returns_422(client):
    resp = await client.post("/tickets", json={"message": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_too_long_message_returns_422(client):
    resp = await client.post("/tickets", json={"message": "a" * 6000})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_order_returns_graceful_response(client, monkeypatch):
    from app.schemas.ticket import TicketAnalysis
    from tests.conftest import FakeLLMWithTools, FakeLLM

    analysis = TicketAnalysis(
        topic="other", urgency="low", order_id="ORD-00000",
        legal_threat=False, reasoning="Test: olmayan sipariş."
    )
    monkeypatch.setattr("app.orchestration.graph.llm_with_tools", FakeLLMWithTools())
    monkeypatch.setattr("app.orchestration.graph.llm", FakeLLM(analysis))

    resp = await client.post("/tickets", json={"message": "ORD-00000 siparişim nerede"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_llm_failure_returns_503(client, monkeypatch):
    class BrokenLLM:
        async def ainvoke(self, messages):
            raise TimeoutError("simulated timeout")

    monkeypatch.setattr("app.orchestration.graph.llm_with_tools", BrokenLLM())

    resp = await client.post("/tickets", json={"message": "ORD-10432 siparişim nerede"})
    assert resp.status_code == 503