from typing import TypedDict
from langgraph.graph import StateGraph, END

from app.data.mock_orders import get_order

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

class TicketState(TypedDict):
    raw_message: str
    analysis: dict | None
    order_info: dict | None
    final_response: str | None

def fake_extract(message: str) -> dict:
    """
    Gerçek LLM yerine geçici, kural tabanlı sahte analiz.
    Gün 2'de gerçek LLM çağrısıyla değiştirilecek.
    """
    urgency = "high" if ("hakem" in message or "iade" in message or "avukat" in message) else "low"

    order_id = None
    for word in message.split():
        if word.startswith("ORD-"):
            order_id = word.strip(".,!?")
            break

    return {
        "topic": "refund_request" if "iade" in message else "other",
        "urgency": urgency,
        "order_id": order_id,
        "legal_threat": "hakem" in message or "avukat" in message,
    }

async def extract_node(state: TicketState) -> dict:
    analysis = fake_extract(state["raw_message"])
    return {"analysis": analysis}


async def fetch_order_node(state: TicketState) -> dict:
    order_id = state["analysis"].get("order_id")
    if order_id is None:
        return {"order_info": None}
    return {"order_info": get_order(order_id)}


async def auto_respond_node(state: TicketState) -> dict:
    return {"final_response": "Talebiniz alınmıştır, standart süreçte işleme konulacaktır."}


async def await_approval_node(state: TicketState) -> dict:
    decision = interrupt({
        "reason": "high_risk",
        "analysis": state["analysis"],
        "order_info": state["order_info"],
    })

    if decision["decision"] == "approve":
        return {"final_response": f"Talebiniz onaylandı. Not: {decision.get('note', '')}"}
    else:
        return {"final_response": f"Talebiniz değerlendirildi, onaylanmadı. Not: {decision.get('note', '')}"}
def route_by_risk(state: TicketState) -> str:
    analysis = state["analysis"]
    if analysis["urgency"] == "high" or analysis.get("legal_threat"):
        return "risky"
    return "not_risky"

def build_graph():
    graph = StateGraph(TicketState)

    graph.add_node("extract", extract_node)
    graph.add_node("fetch_order", fetch_order_node)
    graph.add_node("auto_respond", auto_respond_node)
    graph.add_node("await_approval", await_approval_node)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "fetch_order")

    graph.add_conditional_edges(
        "fetch_order",
        route_by_risk,
        {
            "not_risky": "auto_respond",
            "risky": "await_approval",
        }
    )

    graph.add_edge("auto_respond", END)
    graph.add_edge("await_approval", END)  # Gün 2'de bu satır kalkacak, interrupt gelecek

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)

_compiled_graph = build_graph()


async def start_ticket_flow(ticket_id: str, message: str) -> dict:
    config = {"configurable": {"thread_id": ticket_id}}
    result = await _compiled_graph.ainvoke({"raw_message": message}, config=config)

    state = await _compiled_graph.aget_state(config)
    is_waiting = bool(state.next)

    return {"result": result, "is_waiting": is_waiting}


async def resume_ticket_flow(ticket_id: str, decision: dict) -> dict:
    from langgraph.types import Command

    config = {"configurable": {"thread_id": ticket_id}}
    result = await _compiled_graph.ainvoke(Command(resume=decision), config=config)
    return result