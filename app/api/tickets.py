import uuid
from fastapi import APIRouter

from app.schemas.ticket import TicketRequest, TicketResponse
from app.orchestration.graph import start_ticket_flow, resume_ticket_flow
from app.schemas.ticket import ResumeRequest

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/tickets", response_model=TicketResponse)
async def create_ticket(request: TicketRequest):
    ticket_id = str(uuid.uuid4())

    outcome = await start_ticket_flow(ticket_id, request.message)

    if outcome["is_waiting"]:
        return TicketResponse(
            ticket_id=ticket_id,
            status="pending_approval",
            reason_for_review="Yüksek risk tespit edildi, inceleme bekleniyor.",
        )

    return TicketResponse(
        ticket_id=ticket_id,
        status="completed",
        response=outcome["result"]["final_response"],
    )


@router.post("/tickets/{ticket_id}/resume", response_model=TicketResponse)
async def resume_ticket(ticket_id: str, request: ResumeRequest):
    result = await resume_ticket_flow(
        ticket_id,
        {"decision": request.decision, "note": request.note},
    )

    return TicketResponse(
        ticket_id=ticket_id,
        status="completed",
        response=result["final_response"],
    )