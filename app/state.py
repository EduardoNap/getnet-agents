"""The shared state every agent reads from and writes to."""
import operator
from typing import Annotated, TypedDict


class ChatState(TypedDict, total=False):
    message: str
    user_id: str  # the authenticated merchant, from the token
    trace_id: str
    conversation_id: str
    history: str  # summary and recent turns of this conversation, as prompt text
    language: str  # the language of the merchant's message, named by the router: "English", "Portuguese"
    open_ticket: str  # ticket id when a human already has this conversation
    route: str  # the router's latest decision: knowledge | support | escalation | finish | blocked
    confidence: str  # high | medium | low
    task: str  # what the router asked the current specialist to do
    plan: list[str]  # the router's remaining steps
    # Each specialist run adds one finding; operator.add appends it.
    findings: Annotated[list[dict], operator.add]
    rejected: Annotated[list[int], operator.add]  # positions of findings the router's review did not accept
    response: str
    sources: list[str]
    escalation_reason: str  # set by any node that wants a human handoff
    handoff: dict  # {"ticket_id", "reason", "status"} once a ticket exists
    # Each node returns a one-item list; operator.add appends it to the history.
    steps: Annotated[list[dict], operator.add]


def make_finding(agent: str, state: dict, result=None) -> dict:
    """What one specialist run produced. Without a result, the run failed."""
    return {
        "agent": agent,
        "task": state.get("task") or state["message"],
        "status": "ok" if result else "failed",
        "answer": result.text if result else "",
        "tools": result.tools_used if result else [],
        "sources": result.sources if result else [],
        "evidence": result.evidence if result else [],  # raw tool output; never leaves the service
    }


def usable_findings(state: dict, also_rejected: list[int] | None = None) -> list[dict]:
    """Findings that succeeded, that no review rejected and that did not ask for a human: the only material for the final answer."""
    rejected = set(state.get("rejected", [])) | set(also_rejected or [])
    return [
        finding
        for position, finding in enumerate(state.get("findings", []))
        if finding["status"] == "ok" and finding["answer"] and not finding.get("handoff") and position not in rejected
    ]
