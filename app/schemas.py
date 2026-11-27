"""HTTP request and response models."""
from pydantic import BaseModel, Field

from app.config import settings


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    user_id: str = Field(min_length=1, max_length=64)  # must match the merchant in the token
    conversation_id: str | None = Field(default=None, max_length=64)  # omit to start a new conversation


class ChatResponse(BaseModel):
    response: str
    agent_workflow: list[dict]  # one entry per agent run, in order
    sources: list[str] = []
    handoff: dict | None = None  # {"ticket_id", "reason", "status"} when a human takes over
    trace_id: str
    conversation_id: str  # send it back to continue this conversation
    usage: dict = {}  # tokens and estimated cost of this request


class TicketReply(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
