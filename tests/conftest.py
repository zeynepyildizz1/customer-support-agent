import pytest
from httpx import AsyncClient, ASGITransport
from langchain_core.messages import ToolMessage

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

class FakeAIMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeLLMWithTools:
    """Gerçek Groq modelini taklit eder: ilk çağrıda tool çağırma isteği,
    tool sonucu geldikten sonra düz bir cevap döner."""

    async def ainvoke(self, messages):
        has_tool_result = any(isinstance(m, ToolMessage) for m in messages)
        if not has_tool_result:
            return FakeAIMessage(
                tool_calls=[{"name": "get_order_status", "args": {"order_id": "ORD-10432"}, "id": "call_1"}]
            )
        return FakeAIMessage(content="Sipariş bilgisi alındı.")


class FakeStructuredLLM:
    def __init__(self, analysis):
        self._analysis = analysis

    async def ainvoke(self, prompt):
        return self._analysis


class FakeLLM:
    def __init__(self, analysis):
        self._analysis = analysis

    def with_structured_output(self, schema):
        return FakeStructuredLLM(self._analysis)


@pytest.fixture
def mock_llm_routine(monkeypatch):
    from app.schemas.ticket import TicketAnalysis

    analysis = TicketAnalysis(
        topic="other", urgency="low", order_id="ORD-10432",
        legal_threat=False, reasoning="Test: düşük riskli talep."
    )
    monkeypatch.setattr("app.orchestration.graph.llm_with_tools", FakeLLMWithTools())
    monkeypatch.setattr("app.orchestration.graph.llm", FakeLLM(analysis))


@pytest.fixture
def mock_llm_risky(monkeypatch):
    from app.schemas.ticket import TicketAnalysis

    analysis = TicketAnalysis(
        topic="refund_request", urgency="high", order_id="ORD-10432",
        legal_threat=True, reasoning="Test: yüksek riskli talep."
    )
    monkeypatch.setattr("app.orchestration.graph.llm_with_tools", FakeLLMWithTools())
    monkeypatch.setattr("app.orchestration.graph.llm", FakeLLM(analysis))