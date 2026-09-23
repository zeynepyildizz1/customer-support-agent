from typing import TypedDict
from langgraph.graph import StateGraph, END

from app.data.mock_orders import get_order

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from app.tools.order_tools import get_order_status
from app.prompts.extraction_prompt import SYSTEM_PROMPT
from app.schemas.ticket import TicketAnalysis

load_dotenv()
llm = ChatGroq(model="openai/gpt-oss-120b", api_key=os.environ["GROQ_API_KEY"])
llm_with_tools = llm.bind_tools([get_order_status])

class LLMUnavailableError(Exception):
    """LLM çağrısı başarısız olduğunda fırlatılır (timeout, rate limit, bağlantı hatası vb.)."""
    pass

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
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=state["raw_message"]),
    ]

    try:
        ai_response = await llm_with_tools.ainvoke(messages)
        messages.append(ai_response)

        tool_result = None
        if ai_response.tool_calls:
            for tool_call in ai_response.tool_calls:
                result = get_order_status.invoke(tool_call["args"])
                tool_result = result
                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

            final_response = await llm_with_tools.ainvoke(messages)
        else:
            final_response = ai_response

        structured_llm = llm.with_structured_output(TicketAnalysis)
        analysis = await structured_llm.ainvoke(
            f"Şu bilgilere göre yapılandırılmış analiz üret:\n"
            f"Müşteri mesajı: {state['raw_message']}\n"
            f"Sipariş bilgisi: {tool_result}\n"
            f"Model notu: {final_response.content}"
        )
    except Exception as exc:
        raise LLMUnavailableError(f"LLM çağrısı başarısız oldu: {exc}") from exc

    return {"analysis": analysis.model_dump(), "order_info": tool_result}

async def auto_respond_node(state: TicketState) -> dict:
    order = state.get("order_info")
    if order and not order.get("not_found"):
        response = (
            f"Talebiniz alınmıştır. Sipariş durumu: {order['status']}, "
            f"kargo takip no: {order.get('tracking_number', 'yok')}."
        )
    else:
        response = "Talebiniz alınmıştır, ancak sipariş bilginize ulaşılamadı."
    return {"final_response": response}

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
    graph.add_node("auto_respond", auto_respond_node)
    graph.add_node("await_approval", await_approval_node)

    graph.set_entry_point("extract")

    graph.add_conditional_edges(
        "extract",
        route_by_risk,
        {
            "not_risky": "auto_respond",
            "risky": "await_approval",
        }
    )

    graph.add_edge("auto_respond", END)
    graph.add_edge("await_approval", END)

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

    status = await get_ticket_status(ticket_id)
    if status != "waiting":
        raise TicketNotWaitingError(f"'{ticket_id}' zaten tamamlanmış, tekrar sürdürülemez.")

    config = {"configurable": {"thread_id": ticket_id}}
    result = await _compiled_graph.ainvoke(Command(resume=decision), config=config)
    return result

class TicketNotFoundError(Exception):
    """Verilen ticket_id için kayıtlı bir state bulunamadığında fırlatılır."""
    pass


class TicketNotWaitingError(Exception):
    """Ticket zaten tamamlanmış veya beklemede değilken resume çağrıldığında fırlatılır."""
    pass


async def get_ticket_status(ticket_id: str) -> str:
    config = {"configurable": {"thread_id": ticket_id}}
    state = await _compiled_graph.aget_state(config)

    if not state.values:
        raise TicketNotFoundError(f"'{ticket_id}' için kayıtlı bir talep bulunamadı.")

    return "waiting" if state.next else "completed"