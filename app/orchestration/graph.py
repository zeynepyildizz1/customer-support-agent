from typing import TypedDict
from langgraph.graph import StateGraph, END

from app.data.mock_orders import get_order

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from app.tools.order_tools import get_order_status, check_return_eligibility
from app.prompts.extraction_prompt import SYSTEM_PROMPT
from app.schemas.ticket import TicketAnalysis

load_dotenv()
llm = ChatGroq(model="openai/gpt-oss-120b", api_key=os.environ["GROQ_API_KEY"])
llm_with_tools = llm.bind_tools([get_order_status, check_return_eligibility])

class LLMUnavailableError(Exception):
    """LLM çağrısı başarısız olduğunda fırlatılır (timeout, rate limit, bağlantı hatası vb.)."""
    pass

class TicketNotFoundError(Exception):
    """Verilen ticket_id için kayıtlı bir state bulunamadığında fırlatılır."""
    pass


class TicketNotWaitingError(Exception):
    """Ticket zaten tamamlanmış veya beklemede değilken resume çağrıldığında fırlatılır."""
    pass


class TicketState(TypedDict):
    raw_message: str
    analysis: dict | None
    order_info: dict | None
    final_response: str | None
    risk_reasons: list[str]
    steps: list[str]
    order_id_valid: bool


async def validate_order_node(state: TicketState) -> dict:
    message = state["raw_message"]

    order_id = None
    for word in message.split():
        if word.startswith("ORD-"):
            order_id = word.strip(".,!?")
            break

    if order_id is None:
        return {"order_id_valid": True, "steps": ["Mesajda sipariş numarası belirtilmemiş, geçildi."]}

    order = get_order(order_id)
    if order is None:
        return {
            "order_id_valid": False,
            "final_response": f"Belirttiğiniz sipariş numarası ({order_id}) sistemimizde bulunamadı. Lütfen numarayı kontrol edip tekrar deneyin.",
            "steps": [f"Sipariş numarası ({order_id}) doğrulandı: bulunamadı, LLM'e gidilmeden yanıt üretildi."],
        }

    return {"order_id_valid": True, "steps": [f"Sipariş numarası ({order_id}) doğrulandı: geçerli."]}

"""def fake_extract(message: str) -> dict:
    
    Gerçek LLM yerine geçici, kural tabanlı sahte analiz. ilk etapta kullanıldı
    
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
    }"""

async def extract_node(state: TicketState) -> dict:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=state["raw_message"]),
    ]

    try:
        ai_response = await llm_with_tools.ainvoke(messages)
        messages.append(ai_response)

        tool_results = {}
        if ai_response.tool_calls:
            for tool_call in ai_response.tool_calls:
                if tool_call["name"] == "get_order_status":
                    result = get_order_status.invoke(tool_call["args"])
                elif tool_call["name"] == "check_return_eligibility":
                    result = check_return_eligibility.invoke(tool_call["args"])
                else:
                    result = {"error": "unknown tool"}

                tool_results[tool_call["name"]] = result
                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

            final_response = await llm_with_tools.ainvoke(messages)
        else:
            final_response = ai_response

        order_info = tool_results.get("get_order_status")

        structured_llm = llm.with_structured_output(TicketAnalysis)
        analysis = await structured_llm.ainvoke(
            f"Şu bilgilere göre yapılandırılmış analiz üret:\n"
            f"Müşteri mesajı: {state['raw_message']}\n"
            f"Toplanan bilgiler: {tool_results}\n"
            f"Model notu: {final_response.content}"
        )
    except Exception as exc:
        raise LLMUnavailableError(f"LLM çağrısı başarısız oldu: {exc}") from exc

    steps = state.get("steps", []) + ["Müşteri mesajı analiz edildi."]
    if tool_results:
        called_tools = ", ".join(tool_results.keys())
        steps.append(f"Şu tool(lar) çağrıldı: {called_tools}.")
    else:
        steps.append("Hiçbir tool çağrılmadı (sipariş numarası bulunamadı veya gerekli görülmedi).")

    return {"analysis": analysis.model_dump(), "order_info": order_info, "steps": steps}


async def auto_respond_node(state: TicketState) -> dict:
    order = state.get("order_info")
    if order and not order.get("not_found"):
        response = (
            f"Talebiniz alınmıştır. Sipariş durumu: {order['status']}, "
            f"kargo takip no: {order.get('tracking_number', 'yok')}."
        )
    else:
        response = "Talebiniz alınmıştır, ancak sipariş bilginize ulaşılamadı."

    steps = state.get("steps", []) + ["Düşük riskli bulundu, otomatik yanıt üretildi."]
    return {"final_response": response, "steps": steps}

async def prepare_approval_node(state: TicketState) -> dict:
    reasons = get_risk_reasons(state)
    steps = state.get("steps", []) + [f"Riskli bulundu ({'; '.join(reasons)}), insan onayı bekleniyor."]
    return {"steps": steps}

async def await_approval_node(state: TicketState) -> dict:
    reasons = get_risk_reasons(state)

    decision = interrupt({
        "reason": "high_risk",
        "risk_reasons": reasons,
        "analysis": state["analysis"],
        "order_info": state["order_info"],
    })

    if decision["decision"] == "approve":
        response = f"Talebiniz onaylandı. Not: {decision.get('note', '')}"
        final_steps = state.get("steps", []) + ["Destek uzmanı onayladı, final yanıt üretildi."]
    else:
        response = f"Talebiniz değerlendirildi, onaylanmadı. Not: {decision.get('note', '')}"
        final_steps = state.get("steps", []) + ["Destek uzmanı reddetti, final yanıt üretildi."]

    return {"final_response": response, "steps": final_steps}


def get_risk_reasons(state: TicketState) -> list[str]:
    analysis = state["analysis"]
    order_info = state.get("order_info") or {}
    reasons = []

    if analysis["urgency"] == "high":
        reasons.append("Yüksek aciliyet tespit edildi.")
    if analysis.get("legal_threat"):
        reasons.append("Hukuki tehdit içeriyor.")
    if analysis["topic"] == "refund_request" and order_info.get("amount", 0) > 1000:
        reasons.append(f"Yüksek tutarlı iade talebi ({order_info.get('amount')} TL).")

    return reasons

def route_by_order_validity(state: TicketState) -> str:
    return "valid" if state.get("order_id_valid", True) else "invalid"

def route_by_risk(state: TicketState) -> str:
    reasons = get_risk_reasons(state)
    return "risky" if reasons else "not_risky"


def build_graph():
    graph = StateGraph(TicketState)

    graph.add_node("validate_order", validate_order_node)
    graph.add_node("extract", extract_node)
    graph.add_node("auto_respond", auto_respond_node)
    graph.add_node("prepare_approval", prepare_approval_node)
    graph.add_node("await_approval", await_approval_node)

    graph.set_entry_point("validate_order")

    graph.add_conditional_edges(
        "validate_order",
        route_by_order_validity,
        {
            "valid": "extract",
            "invalid": END,
        }
    )

    graph.add_conditional_edges(
        "extract",
        route_by_risk,
        {
            "not_risky": "auto_respond",
            "risky": "prepare_approval",
        }
    )

    graph.add_edge("prepare_approval", "await_approval")
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

    interrupt_payload = None
    if "__interrupt__" in result:
        interrupt_payload = result["__interrupt__"][0].value

    return {"result": result, "is_waiting": is_waiting, "interrupt_payload": interrupt_payload}

async def resume_ticket_flow(ticket_id: str, decision: dict) -> dict:
    from langgraph.types import Command

    status = await get_ticket_status(ticket_id)
    if status != "waiting":
        raise TicketNotWaitingError(f"'{ticket_id}' zaten tamamlanmış, tekrar sürdürülemez.")

    config = {"configurable": {"thread_id": ticket_id}}
    result = await _compiled_graph.ainvoke(Command(resume=decision), config=config)
    return result


async def get_ticket_status(ticket_id: str) -> str:
    config = {"configurable": {"thread_id": ticket_id}}
    state = await _compiled_graph.aget_state(config)

    if not state.values:
        raise TicketNotFoundError(f"'{ticket_id}' için kayıtlı bir talep bulunamadı.")

    return "waiting" if state.next else "completed"

async def get_ticket_steps(ticket_id: str) -> list[str]:
    config = {"configurable": {"thread_id": ticket_id}}
    state = await _compiled_graph.aget_state(config)
    return state.values.get("steps", [])