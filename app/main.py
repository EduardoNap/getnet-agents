"""HTTP API. Run with: uvicorn app.main:app"""
from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse, Response

from app import auth, metrics, ratelimit, store, tracing
from app.auth import Principal, require_merchant_user, require_principal, require_scope
from app.graph import resume_after_decision, resume_after_human, run_chat
from app.schemas import ChatRequest, ChatResponse, TicketReply

tracing.configure_logging()
store.init()

app = FastAPI(title="Getnet Multi Agent Support", version="3.0.0")


@app.exception_handler(store.NotFound)
def not_found(_request, _error) -> JSONResponse:
    # One body for "does not exist" and "not yours", so ids cannot be probed.
    return JSONResponse({"detail": "not found"}, status_code=404)


@app.exception_handler(store.Conflict)
def conflict(_request, error) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=409)


@app.exception_handler(ratelimit.RateLimited)
def rate_limited(_request, _error) -> JSONResponse:
    return JSONResponse(
        {"detail": "too many requests"}, status_code=429, headers={"Retry-After": str(ratelimit.WINDOW_SECONDS)}
    )


def within_rate_limit(principal: Principal = Depends(require_principal)) -> None:
    ratelimit.check(principal.subject)


LIMITED = [Depends(within_rate_limit)]


@app.middleware("http")
async def count_responses(request, call_next):
    """Every response is counted by endpoint and status, so refused, limited and failed requests can be watched."""
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        route = request.scope.get("route")
        path = route.path if route else "unmatched"  # the route template, never the URL: no ids in labels
        if path not in ("/metrics", "/health"):
            metrics.HTTP.labels(path=path, status=status).inc()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics_page() -> Response:
    """Counts for Prometheus. No token: it carries no merchant data, and is meant to be reachable only inside the network."""
    return Response(metrics.page(), media_type=metrics.CONTENT_TYPE)


# --- merchants -----------------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse, dependencies=LIMITED)
def chat(
    request: ChatRequest,
    principal: Principal = Depends(require_merchant_user),
    idempotency_key: str | None = Header(default=None, max_length=128),  # the Idempotency-Key header
) -> ChatResponse:
    # The token says who the person is. `user_id` chooses one of the merchants that person may act for;
    # the merchant id the agents work on is the one the lookup returns.
    merchant_id = auth.act_for(principal, request.user_id)
    store.audit(actor=principal.subject, action="chat", user_id=merchant_id)
    # With an Idempotency-Key, a request sent twice is answered once, and one that was interrupted continues.
    return run_chat(request.message, merchant_id, request.conversation_id, idempotency_key)


@app.get("/conversations/{conversation_id}", dependencies=LIMITED)
def read_conversation(conversation_id: str, principal: Principal = Depends(require_merchant_user)) -> dict:
    """The transcript of a conversation of one of the person's merchants, including answers from human agents."""
    if not auth.may_act_for(principal, store.conversation_owner(conversation_id)):
        raise store.NotFound("conversation not found")  # someone else's looks the same as one that does not exist
    ticket = store.unresolved_ticket(conversation_id)
    return {
        "conversation_id": conversation_id,
        "messages": [
            {"role": m["role"], "text": m["text"], "at": m["created_at"]} for m in store.get_messages(conversation_id)
        ],
        "handoff": {"ticket_id": ticket["ticket_id"], "status": ticket["status"]} if ticket else None,
    }


# --- operators -----------------------------------------------------------------------------
# Each endpoint names the scope it needs. Reading the queue, answering tickets and approving actions are separate.

read_tickets, write_tickets, approve_actions = (
    require_scope("tickets:read"), require_scope("tickets:write"), require_scope("actions:approve")
)


@app.get("/tickets", dependencies=LIMITED)
def ticket_queue(
    status: str | None = "open", overdue: bool = False, _operator: Principal = Depends(read_tickets)
) -> list[dict]:
    """The queue: fraud and complaints first, then oldest first. `overdue=true` lists unresolved tickets past their due time."""
    return store.list_tickets(status, overdue)


@app.get("/tickets/{ticket_id}", dependencies=LIMITED)
def read_ticket(ticket_id: str, operator: Principal = Depends(read_tickets)) -> dict:
    ticket = store.get_ticket(ticket_id)
    store.audit(actor=operator.subject, action="read_ticket", user_id=ticket["user_id"])
    return {
        "ticket": ticket,
        "action": store.action_for_ticket(ticket_id),  # what is to be approved or rejected; null for a question
        "conversation": store.get_messages(ticket["conversation_id"]),
    }


@app.post("/tickets/{ticket_id}/claim", dependencies=LIMITED)
def claim_ticket(ticket_id: str, operator: Principal = Depends(write_tickets)) -> dict:
    return store.claim_ticket(ticket_id, operator.subject)


@app.post("/tickets/{ticket_id}/reply", dependencies=LIMITED)
def reply_to_ticket(ticket_id: str, reply: TicketReply, operator: Principal = Depends(write_tickets)) -> dict:
    """The human's answer. The agent resumes to word it for the merchant, and the conversation reopens."""
    return resume_after_human(ticket_id, operator.subject, reply.message)


@app.post("/tickets/{ticket_id}/release", dependencies=LIMITED)
def release_ticket(ticket_id: str, operator: Principal = Depends(write_tickets)) -> dict:
    """Give a claimed ticket back to the queue."""
    return store.release_ticket(ticket_id, operator.subject)


@app.post("/tickets/{ticket_id}/approve", dependencies=LIMITED)
def approve_action(ticket_id: str, operator: Principal = Depends(approve_actions)) -> dict:
    """Approve the action this ticket proposes. It is executed once, and the merchant is told."""
    return resume_after_decision(ticket_id, operator.subject, approved=True)


@app.post("/tickets/{ticket_id}/reject", dependencies=LIMITED)
def reject_action(ticket_id: str, reply: TicketReply, operator: Principal = Depends(approve_actions)) -> dict:
    """Reject the action this ticket proposes, with the reason the merchant will read. Nothing is executed."""
    return resume_after_decision(ticket_id, operator.subject, approved=False, reason=reply.message)
