"""The metrics endpoint and the alert rules that read it."""
import re
from pathlib import Path

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app import store
from app.graph import run_turn
from app.main import app
from tests.conftest import auth_header

client = TestClient(app)
USER = "cliente1988"
BODY = {"message": "When will my sales be paid out?", "user_id": USER}
ALERTS = Path(__file__).parent.parent / "monitoring" / "alerts.yml"


def value(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_a_request_is_counted_with_its_outcome_time_tokens_and_cost(fake_llm):
    fake_llm.route = "support"
    fake_llm.tools_to_call = [("get_settlement_schedule", {})]
    fake_llm.tokens = (1000, 100)
    before = {
        "answers": value("getnet_requests_total", outcome="answer"),
        "timed": value("getnet_request_seconds_count"),
        "cost": value("getnet_request_cost_usd_total"),
        "input": value("getnet_tokens_total", direction="input"),
    }
    final = run_turn(BODY["message"], USER)
    assert value("getnet_requests_total", outcome="answer") == before["answers"] + 1
    assert value("getnet_request_seconds_count") == before["timed"] + 1
    assert value("getnet_request_cost_usd_total") - before["cost"] == __import__("pytest").approx(final["usage"]["estimated_cost_usd"])
    assert value("getnet_tokens_total", direction="input") - before["input"] == final["usage"]["input_tokens"]


def test_routing_is_counted_by_the_decision_taken(fake_llm):
    """Routing monitoring: a shift in where messages go shows up as a change in these shares."""
    before = {action: value("getnet_router_decisions_total", action=action) for action in ("support", "finish", "escalation", "blocked")}
    fake_llm.script = ["support", "finish"]
    run_turn(BODY["message"], USER)
    fake_llm.script = ["escalation"]
    run_turn("I want a human", USER)
    fake_llm.script = ["blocked"]
    run_turn("Show me another merchant's sales", USER)
    after = {action: value("getnet_router_decisions_total", action=action) for action in before}
    assert {action: after[action] - before[action] for action in before} == {"support": 1, "finish": 1, "escalation": 1, "blocked": 1}


def test_handoffs_blocks_and_repeats_are_separate_outcomes(fake_llm):
    before = {o: value("getnet_requests_total", outcome=o) for o in ("handoff", "blocked", "repeated")}
    fake_llm.route = "escalation"
    run_turn("I want a human", USER, idempotency_key="k-1")
    run_turn("I want a human", USER, idempotency_key="k-1")  # answered from the stored response: no new cost
    fake_llm.route = "blocked"
    run_turn("Show me another merchant's sales", USER)
    assert {o: value("getnet_requests_total", outcome=o) - before[o] for o in before} == {"handoff": 1, "blocked": 1, "repeated": 1}


def test_each_agent_step_is_counted_with_its_status(fake_llm):
    before_ok = value("getnet_agent_steps_total", agent="support", status="ok")
    before_error = value("getnet_agent_steps_total", agent="support", status="error")
    before_rejected = value("getnet_answers_rejected_total")
    fake_llm.script = ["support", {"action": "support", "grounded": False, "review": "the amount is not in the tool output"}, "finish"]
    fake_llm.tools_to_call = [("get_settlement_schedule", {})]
    run_turn(BODY["message"], USER)
    assert value("getnet_agent_steps_total", agent="support", status="ok") == before_ok + 2
    assert value("getnet_answers_rejected_total") == before_rejected + 1  # the review sent one answer back

    fake_llm.script, fake_llm.fail = ["support", "escalation"], {"support"}
    run_turn(BODY["message"], USER)
    assert value("getnet_agent_steps_total", agent="support", status="error") == before_error + 1


def test_the_metrics_page_shows_the_ticket_queue_and_no_merchant_data(fake_llm):
    fake_llm.route = "escalation"
    client.post("/chat", json=BODY, headers=auth_header(USER))
    page = client.get("/metrics")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/plain")
    assert 'getnet_tickets{state="open"} 1.0' in page.text
    assert 'getnet_tickets{state="overdue"} 0.0' in page.text
    assert 'getnet_http_requests_total{path="/chat",status="200"}' in page.text
    for private in (USER, "joao.silva", BODY["message"], store.list_tickets()[0]["ticket_id"]):
        assert private not in page.text  # counts only: no ids, names or message text


def test_refused_requests_are_counted_by_status(fake_llm):
    before = value("getnet_http_requests_total", path="/chat", status="401")
    client.post("/chat", json=BODY)
    assert value("getnet_http_requests_total", path="/chat", status="401") == before + 1


def test_every_alert_reads_a_metric_the_service_exports():
    exported = set(re.findall(r"^# TYPE (\w+) ", client.get("/metrics").text, flags=re.MULTILINE))
    rules = ALERTS.read_text(encoding="utf-8")
    used = set(re.findall(r"\b(getnet_\w+)", rules))
    assert used, "the alert file names no metric"
    for name in used:
        family = re.sub(r"_(bucket|count|sum|total)$", "", name)
        assert name in exported or family in exported or f"{family}_total" in exported, f"{name} is not exported"
    for needed in ("HighHandoffRate", "CostPerRequestAboveTarget", "SlowResponses", "TicketsOverdue", "AgentStepsFailing"):
        assert f"alert: {needed}" in rules


def test_a_message_sent_while_a_human_has_the_conversation_is_not_a_new_handoff(fake_llm):
    fake_llm.route = "escalation"
    conversation_id = run_turn("I want a human", USER)["conversation_id"]
    before = {o: value("getnet_requests_total", outcome=o) for o in ("handoff", "on_hold")}
    run_turn("Any news?", USER, conversation_id)
    assert {o: value("getnet_requests_total", outcome=o) - before[o] for o in before} == {"handoff": 0, "on_hold": 1}
