"""The orchestration: which agent runs, and what runs after it."""

import time
import uuid

from langgraph.graph import END, START, StateGraph

from app import llm, memory, metrics, store, tracing
from app.agents import escalation
from app.agents.knowledge import knowledge_node
from app.agents.router import guardrail_node, router_node
from app.agents.support import support_node
from app.agents.synthesizer import synthesizer_node
from app.agents.verifier import verifier_node
from app.config import settings
from app.guardrails import mask_card_numbers
from app.schemas import ChatResponse
from app.state import ChatState, make_finding
from app.tools import support_tools
from app.tracing import traced

FALLBACK_RESPONSE = "Sorry, something went wrong on our side."


def after_guardrail(state: ChatState) -> str:
    if state.get("route") == "blocked":
        return "end"
    return "hold" if state.get("open_ticket") else "router"  # hold: a human already has this conversation


def after_router(state: ChatState) -> str:
    if state.get("escalation_reason"):  # asked for a human, low confidence, nothing grounded, or the router failed
        return "escalation"
    if state.get("route") == "blocked":
        return "end"
    if state.get("route") == "finish":
        return "synthesizer"
    return state["route"]  # "knowledge" or "support"


def after_specialist(state: ChatState) -> str:
    # Back to the router, which reviews the result and decides what is next.
    return "escalation" if state.get("escalation_reason") else "router"


def after_synthesizer(_state: ChatState) -> str:
    return "verifier" if settings.verifier_enabled else "end"  # off only to measure what the verifier adds


def failed_finding(agent: str, state: dict) -> dict:
    """A specialist crashed: tell the router instead of giving up, so it can try another path."""
    return {"findings": [make_finding(agent, state)]}


def build_graph():
    graph = StateGraph(ChatState)
    # traced() times and meters each agent, records it in the response, and turns a crash into a handoff.
    graph.add_node("guardrail", traced("guardrail", guardrail_node))
    graph.add_node("hold", traced("hold", escalation.hold_node))
    graph.add_node("router", traced("router", router_node))
    graph.add_node("knowledge", traced("knowledge", knowledge_node, on_error=failed_finding))
    graph.add_node("support", traced("support", support_node, on_error=failed_finding))
    graph.add_node("synthesizer", traced("synthesizer", synthesizer_node))
    graph.add_node("verifier", traced("verifier", verifier_node))
    graph.add_node("escalation", traced("escalation", escalation.escalation_node))

    graph.add_edge(START, "guardrail")
    graph.add_conditional_edges("guardrail", after_guardrail, {"router": "router", "hold": "hold", "end": END})
    graph.add_conditional_edges(
        "router",
        after_router,
        {
            "knowledge": "knowledge",
            "support": "support",
            "synthesizer": "synthesizer",
            "escalation": "escalation",
            "end": END,
        },
    )
    graph.add_conditional_edges("knowledge", after_specialist, {"router": "router", "escalation": "escalation"})
    graph.add_conditional_edges("support", after_specialist, {"router": "router", "escalation": "escalation"})
    graph.add_conditional_edges("synthesizer", after_synthesizer, {"verifier": "verifier", "end": END})
    graph.add_edge("verifier", END)
    graph.add_edge("escalation", END)
    graph.add_edge("hold", END)
    return graph.compile()


GRAPH = build_graph()


CHECKPOINT_FIELDS = ("language", "plan", "findings", "rejected", "steps")  # what a continued turn starts from
RESPONSE_FIELDS = ("response", "steps", "sources", "handoff", "trace_id", "conversation_id", "usage", "route")


def _usage(meter: llm.Usage, earlier: dict) -> dict:
    """This run's usage plus what an interrupted attempt at the same turn had already used."""
    return {
        "input_tokens": meter.input_tokens + earlier.get("input_tokens", 0),
        "output_tokens": meter.output_tokens + earlier.get("output_tokens", 0),
        "llm_calls": meter.calls + earlier.get("llm_calls", 0),
        "estimated_cost_usd": round(meter.cost_usd + earlier.get("estimated_cost_usd", 0), 6),
    }


def run_turn(message: str, user_id: str, conversation_id: str | None = None, idempotency_key: str | None = None) -> dict:
    """One merchant message through the graph. Returns the final state, which the evaluation also reads.

    `user_id` is the authenticated merchant. Raises store.NotFound when the conversation is not theirs,
    and store.Conflict when a turn is already running in it.

    The state is saved after every step. With an `idempotency_key`, sending the request again returns
    the stored response when the turn finished, and continues from the last saved step when it did not:
    specialists that already answered are not called again.
    """
    turn = store.begin_turn(user_id, conversation_id, mask_card_numbers(message), idempotency_key)
    if turn["status"] == "done":
        tracing.log_event("turn_repeated", trace_id=turn["result"]["trace_id"], conversation_id=turn["conversation_id"])
        metrics.record_repeat()
        return turn["result"]

    conversation_id = turn["conversation_id"]
    conversation = store.get_conversation(conversation_id, user_id)
    ticket = store.unresolved_ticket(conversation_id)
    saved = turn["checkpoint"] or {}
    trace_id = saved.get("trace_id") or uuid.uuid4().hex
    earlier_usage = saved.get("usage", {})
    if saved:
        tracing.log_event("turn_continued", trace_id=trace_id, conversation_id=conversation_id, steps_kept=len(saved.get("steps", [])))

    started = time.perf_counter()
    try:
        with tracing.span("chat", trace_id=trace_id, conversation_id=conversation_id), llm.meter() as usage:
            state = {
                "message": message,
                "user_id": user_id,
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "history": memory.load(conversation),
                "open_ticket": ticket["ticket_id"] if ticket else "",
                **{field: saved[field] for field in CHECKPOINT_FIELDS if field in saved},
            }
            for state in GRAPH.stream(state, stream_mode="values"):  # the state after each step
                checkpoint = {field: state[field] for field in CHECKPOINT_FIELDS if field in state}
                store.save_step(turn["id"], checkpoint | {"trace_id": trace_id, "usage": _usage(usage, earlier_usage)})
            final = state
            final["response"] = final.get("response") or FALLBACK_RESPONSE
            final["usage"] = _usage(usage, earlier_usage)
            # A blocked message must not come back through the history.
            said = [] if final.get("route") == "blocked" else [("user", final["message"]), ("assistant", final["response"])]
            store.finish_turn(turn["id"], {field: final.get(field) for field in RESPONSE_FIELDS}, said, trace_id)
            if said:
                calls = usage.calls
                memory.summarize_if_long(conversation)
                if usage.calls != calls:  # the summary used the model: count it in this request
                    final["usage"] = _usage(usage, earlier_usage)
                    store.update_turn_result(turn["id"], {field: final.get(field) for field in RESPONSE_FIELDS})
    except BaseException:
        store.interrupt_turn(turn["id"])  # does nothing once the turn is done
        raise
    metrics.record_request(final, time.perf_counter() - started)
    return final


def run_chat(message: str, user_id: str, conversation_id: str | None = None, idempotency_key: str | None = None) -> ChatResponse:
    final = run_turn(message, user_id, conversation_id, idempotency_key)
    return ChatResponse(
        response=final["response"],
        agent_workflow=final.get("steps") or [],
        sources=final.get("sources") or [],
        handoff=final.get("handoff"),
        trace_id=final["trace_id"],
        conversation_id=final["conversation_id"],
        usage=final["usage"],
    )


def resume_after_human(ticket_id: str, operator: str, reply: str) -> dict:
    """An operator answered: the agent words the answer for the merchant and the conversation reopens.

    Safe to repeat: a second call by the same operator returns the stored result and runs nothing.
    """
    ticket = store.get_ticket(ticket_id)
    if ticket["status"] == "resolved" and ticket["operator"] == operator:
        return ticket
    if ticket["status"] != "claimed" or ticket["operator"] != operator:
        raise store.Conflict("ticket must be claimed by this operator before it can be answered")
    with tracing.span("ticket.resume", ticket_id=ticket_id), llm.meter() as usage:
        merchant_message = escalation.write_resume_message(ticket, reply)
    resolved, _ = store.resolve_ticket(ticket_id, operator, reply, merchant_message)
    tracing.log_event(
        "ticket_resolved",
        ticket_id=ticket_id,
        conversation_id=resolved["conversation_id"],
        operator=operator,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
    return resolved


def resume_after_decision(ticket_id: str, operator: str, approved: bool, reason: str = "") -> dict:
    """An operator approved or rejected a proposed action. Approval executes it exactly once; either
    way the agent tells the merchant and the ticket is resolved.

    Safe to repeat: the same decision again returns the stored result. The opposite decision is a Conflict.
    """
    ticket, action = store.get_ticket(ticket_id), store.action_for_ticket(ticket_id)
    if action is None:
        raise store.Conflict("this ticket has no action to approve or reject")
    wanted = ("approved", "executed") if approved else ("rejected",)
    if action["status"] != "pending":
        if action["status"] in wanted and action["decided_by"] == operator:
            return {**ticket, "action": action}
        raise store.Conflict(f"this action was already {action['status']}")
    if ticket["status"] != "claimed" or ticket["operator"] != operator:
        raise store.Conflict("ticket must be claimed by this operator before its action can be decided")

    if store.decide_action(action["action_id"], operator, approved, reason) and approved:  # only the call that decided executes
        store.record_execution(action["action_id"], support_tools.execute_terminal_replacement(action))
    action = store.action_for_ticket(ticket_id)
    outcome = (
        f"Approved. The replacement of terminal {action['target']} was requested, order {action['result']}."
        if approved
        else f"Not approved: the replacement of terminal {action['target']} was not requested. {reason}".strip()
    )
    with llm.meter():
        merchant_message = escalation.write_resume_message(ticket, outcome)
    resolved, _ = store.resolve_ticket(ticket_id, operator, outcome, merchant_message)
    tracing.log_event("action_decided", ticket_id=ticket_id, action_id=action["action_id"], status=action["status"], operator=operator)
    return {**resolved, "action": action}
