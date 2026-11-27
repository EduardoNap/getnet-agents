"""Observability: JSON logs, token usage and cost, spans, the audit log and the rate limit."""
import json
import logging

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import store, tracing
from app.config import settings
from app.graph import run_chat
from app.main import app
from tests.conftest import auth_header

USER = "cliente1988"
client = TestClient(app)


def test_every_step_is_one_json_log_line(fake_llm, caplog):
    fake_llm.route = "support"
    fake_llm.tools_to_call = [("get_terminal_status", {})]  # with tool output, so the verifier has something to check
    with caplog.at_level(logging.INFO, logger="getnet"):
        response = run_chat("My card machine won't connect", USER)
    lines = [json.loads(tracing.JsonFormatter().format(record)) for record in caplog.records]
    steps = [line for line in lines if line["event"] == "agent_step"]
    assert [step["agent"] for step in steps] == ["guardrail", "router", "support", "router", "synthesizer", "verifier"]
    for step in steps:
        assert step["trace_id"] == response.trace_id
        assert step["conversation_id"] == response.conversation_id
        assert step["status"] == "ok" and "latency_ms" in step and "ts" in step


def test_a_failure_is_logged_as_json_with_the_stack_trace(fake_llm, caplog):
    fake_llm.fail = {"knowledge"}
    with caplog.at_level(logging.INFO, logger="getnet"):
        run_chat("What is Pix?", USER)
    failures = [json.loads(tracing.JsonFormatter().format(r)) for r in caplog.records if r.exc_info]
    assert "ConnectionError" in failures[0]["exception"]


def test_tokens_and_cost_are_reported_per_step_and_per_request(fake_llm):
    fake_llm.route = "support"
    fake_llm.tokens = (1000, 100)  # every model call reports 1,000 tokens in and 100 out
    response = run_chat("My card machine won't connect", USER)

    by_agent = {step["agent"]: step for step in response.agent_workflow if "input_tokens" in step}
    assert set(by_agent) == {"router", "support"}  # the guardrail and the unchanged answer cost nothing
    assert by_agent["support"]["input_tokens"] == 1000 and by_agent["support"]["output_tokens"] == 100
    # Three calls: router plans, support answers, router reviews. Opus 5.5: $4 in, $20 out per million tokens.
    assert response.usage == {
        "input_tokens": 3000,
        "output_tokens": 300,
        "llm_calls": 3,
        "estimated_cost_usd": round(3 * (1000 * 4 + 100 * 20) / 1_000_000, 6),
    }


def test_with_tracing_configured_each_step_is_a_span(fake_llm, monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "_tracer", lambda: provider.get_tracer("test"))

    fake_llm.route = "support"
    response = run_chat("My card machine won't connect", USER)

    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == [
        "agent.guardrail", "agent.router", "agent.support", "agent.router", "agent.synthesizer", "agent.verifier", "chat",
    ]
    request_span = spans[-1]
    assert request_span.attributes["trace_id"] == response.trace_id
    assert all(s.parent.span_id == request_span.context.span_id for s in spans[:-1])  # one trace per request


def test_every_account_read_is_in_the_audit_log(fake_llm):
    fake_llm.route = "support"
    fake_llm.tools_to_call = [("get_recent_transactions", {}), ("get_terminal_status", {})]
    response = run_chat("Why was my sale declined?", USER)
    entries = store.audit_entries(USER)
    assert [e["action"] for e in entries] == ["get_recent_transactions", "get_terminal_status"]
    assert {e["actor"] for e in entries} == {USER}
    assert {e["trace_id"] for e in entries} == {response.trace_id}


def test_a_card_number_never_reaches_the_model_or_the_database(fake_llm):
    fake_llm.route = "support"
    response = run_chat("The card 4111 1111 1111 1111 was declined, why?", USER)
    assert response.agent_workflow[0]["detail"] == "passed, card number masked"
    everything = " ".join(fake_llm.seen_messages) + " ".join(m["text"] for m in store.get_messages(response.conversation_id))
    assert "4111" not in everything
    assert "[card number removed]" in fake_llm.seen_messages[0]


def test_requests_are_limited_per_principal(fake_llm, monkeypatch):
    from app import ratelimit

    monkeypatch.setattr(ratelimit, "clock", lambda: 6000.0)  # one minute for the whole test
    body = {"message": "What is Pix?", "user_id": USER}
    headers = auth_header(USER)
    statuses = [client.post("/chat", json=body, headers=headers).status_code for _ in range(settings.rate_limit_per_minute + 1)]
    assert statuses[:-1] == [200] * settings.rate_limit_per_minute
    assert statuses[-1] == 429
    maria = client.post("/chat", json={**body, "user_id": "maria_2020"}, headers=auth_header("maria_2020"))
    assert maria.status_code == 200  # another merchant is not affected
