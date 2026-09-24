from pydantic import BaseModel, Field

from typing import Literal

class TicketRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)

class TicketAnalysis(BaseModel):
    topic: Literal["shipping_delay", "refund_request", "complaint", "other"]
    urgency: Literal["low", "medium", "high"]
    order_id: str | None = None
    legal_threat: bool = False
    reasoning: str

class TicketResponse(BaseModel):
    ticket_id: str
    status: Literal["completed", "pending_approval"]
    response: str | None = None
    reason_for_review: str | None = None
    steps_summary: list[str] = []
    

class ResumeRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None