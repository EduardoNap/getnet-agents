"""Cost: cached tokens are priced as cached, and a request stops spending at its cap."""
import pytest

from app import llm
from app.config import settings
from app.graph import run_chat

USER = "cliente1988"


def agents(response):
    return [step["agent"] for step in response.agent_workflow]


def test_cached_tokens_are_priced_at_the_cache_rates():
    with llm.meter() as usage:
        llm.record_usage("claude-sonnet-5-5", 1000, 100, cache_read_tokens=10_000, cache_write_tokens=2000)
    # Sonnet 5.5 per million tokens: input $2, output $10, cache read $0.10, cache write 1.25 x input.
    assert usage.cost_usd == pytest.approx((1000 * 2 + 100 * 10 + 10_000 * 0.10 + 2000 * 2.5) / 1_000_000)
    assert usage.input_tokens == 13_000  # everything the model read, cached or not
    assert usage.cache_read_tokens == 10_000


def test_spent_adds_up_the_steps_of_the_request():
    with llm.meter():
        llm.record_usage("claude-sonnet-5-5", 1_000_000, 0)
        with llm.meter():
            llm.record_usage("claude-sonnet-5-5", 500_000, 0)
            assert llm.spent() == pytest.approx(3.0)  # this step and the request so far
    assert llm.spent() == 0.0  # outside a request


def test_a_request_over_its_cost_cap_answers_with_what_it_has(fake_llm):
    assert settings.max_request_cost_usd == 0.50
    fake_llm.tokens = (100_000, 1000)  # $0.42 per call at the price the fake reports
    fake_llm.script = ["support", "knowledge", "knowledge"]
    fake_llm.tools_to_call = [("get_terminal_status", {})]

    response = run_chat("Is my machine online, and how do I set up Wi-Fi?", USER)

    assert agents(response) == ["guardrail", "router", "support", "router", "synthesizer", "verifier"]
    assert len(fake_llm.router_inputs) == 1  # the review after the cap did not call the model
    assert "cost cap" in response.agent_workflow[3]["detail"]
    assert response.handoff is None and response.response


def test_over_the_cap_with_nothing_usable_hands_off(fake_llm):
    fake_llm.tokens = (200_000, 1000)  # the plan alone passes the cap
    fake_llm.script = ["support"]
    fake_llm.fail = {"support"}

    response = run_chat("Is my machine online?", USER)

    assert response.handoff and response.handoff["ticket_id"].startswith("TCK-")
    assert len(fake_llm.router_inputs) == 1


def test_two_reports_are_compared_side_by_side():
    from evals.compare import compare

    def report(model, passed, grounded, cost, seconds):
        row = {"runs": 10, "passed": passed, "outcome": "10/10", "agents": "10/10", "tools": "10/10", "facts": "9/10",
               "correct": "9/10", "grounded": grounded, "complete": "9/10"}
        return {"meta": {"model": model}, "summary": {"by_kind": {"all": row}, "cost_usd_per_request": cost,
                                                     "seconds_median": seconds, "seconds_p95": seconds * 2}}

    table = compare(report("opus", "8/10", "8/10", 0.11, 12.0), report("sonnet", "9/10", "10/10", 0.05, 9.0))
    assert "| passed | 8/10 | 9/10 |" in table
    assert "| grounded | 8/10 | 10/10 |" in table
    assert "| cost per request | $0.11 | $0.05 |" in table
    assert "| opus | sonnet |" in table.splitlines()[0]
