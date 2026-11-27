"""Numbers for monitoring, served at GET /metrics in the Prometheus text format.

Counts only: no merchant ids, names, ticket ids or message text ever become a label. Each process
keeps its own counters and Prometheus adds them up across processes. The alert rules that read
these numbers are in `monitoring/alerts.yml`.
"""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app import store

CONTENT_TYPE = CONTENT_TYPE_LATEST

# How messages end: answer | handoff | on_hold | blocked | repeated (answered again from a stored response).
REQUESTS = Counter("getnet_requests", "Chat messages handled, by how they ended", ["outcome"])
REQUEST_SECONDS = Histogram(
    "getnet_request_seconds", "Time to handle one chat message", buckets=(1, 2, 5, 10, 20, 30, 60, 120)
)
COST = Counter("getnet_request_cost_usd", "Estimated model cost of the chat messages handled, in US dollars")
TOKENS = Counter("getnet_tokens", "Model tokens used", ["direction"])  # input | output
# Routing: where the Router sends messages. A shift in these shares is the first sign of a prompt or model change.
ROUTER_DECISIONS = Counter("getnet_router_decisions", "Decisions taken by the Router", ["action"])
AGENT_STEPS = Counter("getnet_agent_steps", "Agent runs, by agent and result", ["agent", "status"])
REJECTED = Counter("getnet_answers_rejected", "Specialist answers the Router's review did not accept as grounded")
HTTP = Counter("getnet_http_requests", "HTTP responses, by endpoint and status", ["path", "status"])
TICKETS = Gauge("getnet_tickets", "Tickets waiting for a human, read from the database on every scrape", ["state"])


def outcome(final: dict) -> str:
    if final.get("route") == "blocked":
        return "blocked"
    if any(step["agent"] == "hold" for step in final.get("steps") or []):
        return "on_hold"  # a human already has this conversation: not a new handoff
    return "handoff" if final.get("handoff") else "answer"


def record_request(final: dict, seconds: float) -> None:
    REQUESTS.labels(outcome=outcome(final)).inc()
    REQUEST_SECONDS.observe(seconds)
    usage = final.get("usage") or {}
    COST.inc(usage.get("estimated_cost_usd", 0))
    TOKENS.labels(direction="input").inc(usage.get("input_tokens", 0))
    TOKENS.labels(direction="output").inc(usage.get("output_tokens", 0))


def record_repeat() -> None:
    REQUESTS.labels(outcome="repeated").inc()


def record_step(agent: str, step: dict, update: dict) -> None:
    AGENT_STEPS.labels(agent=agent, status=step["status"]).inc()
    if agent == "router":
        if update.get("route"):
            ROUTER_DECISIONS.labels(action=update["route"]).inc()
        if step.get("grounded") is False:
            REJECTED.inc()


def page() -> bytes:
    TICKETS.labels(state="open").set(len(store.list_tickets("open")))
    TICKETS.labels(state="claimed").set(len(store.list_tickets("claimed")))
    TICKETS.labels(state="overdue").set(len(store.list_tickets(None, overdue=True)))
    return generate_latest()
