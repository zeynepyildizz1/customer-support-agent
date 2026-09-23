import uuid
from fastapi import APIRouter

from app.schemas.ticket import TicketRequest, TicketResponse
from app.orchestration.graph import run_ticket_flow

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/tickets", response_model=TicketResponse)
async def create_ticket(request: TicketRequest):
    ticket_id = str(uuid.uuid4())

    result = await run_ticket_flow(request.message)

    if result["final_response"] and "bekleniyor" in result["final_response"]:
        return TicketResponse(
            ticket_id=ticket_id,
            status="pending_approval",
            reason_for_review="Yüksek risk tespit edildi.",
        )

    return TicketResponse(
        ticket_id=ticket_id,
        status="completed",
        response=result["final_response"],
    )