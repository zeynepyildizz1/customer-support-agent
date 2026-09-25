import uuid
from fastapi import APIRouter

import os
from app.schemas.ticket import TicketRequest, TicketResponse
from app.schemas.ticket import ResumeRequest
from fastapi import HTTPException
from app.orchestration.graph import (
    start_ticket_flow,
    resume_ticket_flow,
    get_ticket_steps,
    LLMUnavailableError,
    TicketNotFoundError,
    TicketNotWaitingError,
)
router = APIRouter()


@router.get("/health")
async def health():
    groq_configured = bool(os.environ.get("GROQ_API_KEY"))
    return {
        "status": "ok" if groq_configured else "degraded",
        "dependencies": {
            "groq_api_key_configured": groq_configured
        }
    }

@router.post("/tickets", response_model=TicketResponse)
async def create_ticket(request: TicketRequest):
    ticket_id = str(uuid.uuid4())

    try:
        outcome = await start_ticket_flow(ticket_id, request.message)
    except LLMUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Şu anda talebinizi işleyemiyoruz, lütfen daha sonra tekrar deneyin."
        )

    steps = await get_ticket_steps(ticket_id)

    if outcome["is_waiting"]:
        payload = outcome.get("interrupt_payload") or {}
        reasons = payload.get("risk_reasons", [])
        reason_text = " ".join(reasons) if reasons else "Yüksek risk tespit edildi, inceleme bekleniyor."

        return TicketResponse(
            ticket_id=ticket_id,
            status="pending_approval",
            reason_for_review=reason_text,
            steps_summary=steps,
        )

    return TicketResponse(
        ticket_id=ticket_id,
        status="completed",
        response=outcome["result"]["final_response"],
        steps_summary=steps,
    )


@router.post("/tickets/{ticket_id}/resume", response_model=TicketResponse)
async def resume_ticket(ticket_id: str, request: ResumeRequest):
    try:
        result = await resume_ticket_flow(
            ticket_id,
            {"decision": request.decision, "note": request.note},
        )
    except TicketNotFoundError:
        raise HTTPException(status_code=404, detail="Belirtilen talep referansı bulunamadı.")
    except TicketNotWaitingError:
        raise HTTPException(status_code=409, detail="Bu talep zaten tamamlanmış.")

    steps = await get_ticket_steps(ticket_id)

    return TicketResponse(
        ticket_id=ticket_id,
        status="completed",
        response=result["final_response"],
        steps_summary=steps,
    )