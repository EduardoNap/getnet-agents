"""Human handoff end to end: ticket, operator queue, claim, reply, and the conversation resuming."""
from fastapi.testclient import TestClient

from app import store
from app.graph import run_chat
from app.main import app
from tests.conftest import auth_header

USER = "cliente1988"
ANA, BRUNO = auth_header("ana", "operator"), auth_header("bruno", "operator")
client = TestClient(app)


def agents(response):
    return [step["agent"] for step in response.agent_workflow]


def escalate(fake_llm, message="My payout never arrived.") -> tuple[str, str]:
    """A merchant message that ends in a handoff. Returns (conversation_id, ticket_id)."""
    fake_llm.script = ["escalation"]
    response = run_chat(message, USER)
    fake_llm.script = []
    return response.conversation_id, response.handoff["ticket_id"]


def test_asking_for_a_human_twice_opens_one_ticket(fake_llm):
    conversation_id, ticket_id = escalate(fake_llm)
    fake_llm.script = ["escalation"]
    again = run_chat("Hello? I need a person.", USER, conversation_id)
    assert again.handoff["ticket_id"] == ticket_id
    assert len(store.list_tickets()) == 1


def test_while_a_human_has_the_conversation_no_agent_answers(fake_llm):
    conversation_id, ticket_id = escalate(fake_llm)
    calls_before = len(fake_llm.seen_messages)

    response = run_chat("It was R$ 1,265.59, in case that helps.", USER, conversation_id)

    assert agents(response) == ["guardrail", "hold"]
    assert ticket_id in response.response and response.handoff["status"] == "open"
    assert len(fake_llm.seen_messages) == calls_before  # no model call
    seen_by_operator = client.get(f"/tickets/{ticket_id}", headers=ANA).json()["conversation"]
    assert "It was R$ 1,265.59, in case that helps." in [m["text"] for m in seen_by_operator]


def test_an_operator_claims_answers_and_the_conversation_resumes(fake_llm):
    conversation_id, ticket_id = escalate(fake_llm)
    assert [t["ticket_id"] for t in client.get("/tickets", headers=ANA).json()] == [ticket_id]

    claimed = client.post(f"/tickets/{ticket_id}/claim", headers=ANA)
    assert (claimed.status_code, claimed.json()["status"], claimed.json()["operator"]) == (200, "claimed", "ana")

    fake_llm.replies["resume"] = f"A human agent answered ticket {ticket_id}: your payout was reissued and arrives tomorrow."
    resolved = client.post(f"/tickets/{ticket_id}/reply", json={"message": "Payout reissued, arrives tomorrow."}, headers=ANA)
    assert (resolved.status_code, resolved.json()["status"]) == (200, "resolved")
    assert client.get("/tickets", headers=ANA).json() == []  # the queue is empty again

    # The merchant can read both the human's words and the agent's message.
    transcript = client.get(f"/conversations/{conversation_id}", headers=auth_header(USER)).json()
    assert [m["role"] for m in transcript["messages"]][-2:] == ["human_agent", "assistant"]
    assert transcript["messages"][-2]["text"] == "Payout reissued, arrives tomorrow."
    assert transcript["messages"][-1]["text"] == fake_llm.replies["resume"]
    assert transcript["handoff"] is None

    # The agents take over again, and they know what the human said.
    fake_llm.route = "support"
    follow_up = run_chat("Thanks. Which account will it go to?", USER, conversation_id)
    assert agents(follow_up) == ["guardrail", "router", "support", "router", "synthesizer", "verifier"]
    assert "human agent: Payout reissued, arrives tomorrow." in fake_llm.seen_messages[-2]


def test_the_same_reply_sent_twice_answers_once(fake_llm):
    conversation_id, ticket_id = escalate(fake_llm)
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)

    first = client.post(f"/tickets/{ticket_id}/reply", json={"message": "Payout reissued."}, headers=ANA)
    second = client.post(f"/tickets/{ticket_id}/reply", json={"message": "Payout reissued."}, headers=ANA)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert fake_llm.agent_calls.count("resume") == 1
    assert [m["role"] for m in store.get_messages(conversation_id)].count("human_agent") == 1


def test_a_ticket_belongs_to_the_operator_who_claimed_it(fake_llm):
    _, ticket_id = escalate(fake_llm)
    reply = {"message": "Payout reissued."}
    assert client.post(f"/tickets/{ticket_id}/reply", json=reply, headers=ANA).status_code == 409  # not claimed yet
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)
    assert client.post(f"/tickets/{ticket_id}/claim", headers=ANA).status_code == 200  # a repeat is harmless
    assert client.post(f"/tickets/{ticket_id}/claim", headers=BRUNO).status_code == 409
    assert client.post(f"/tickets/{ticket_id}/reply", json=reply, headers=BRUNO).status_code == 409
    assert fake_llm.agent_calls.count("resume") == 0


def test_ticket_endpoints_are_for_operators_only(fake_llm):
    _, ticket_id = escalate(fake_llm)
    merchant = auth_header(USER)
    assert client.get("/tickets", headers=merchant).status_code == 403
    assert client.get(f"/tickets/{ticket_id}", headers=merchant).status_code == 403
    assert client.post(f"/tickets/{ticket_id}/claim", headers=merchant).status_code == 403
    assert client.post(f"/tickets/{ticket_id}/reply", json={"message": "x"}, headers=merchant).status_code == 403
    assert client.get("/tickets").status_code == 401
    assert client.get("/tickets/TCK-NOPE", headers=ANA).status_code == 404


def test_the_humans_answer_is_delivered_even_if_the_model_is_down(fake_llm):
    conversation_id, ticket_id = escalate(fake_llm)
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)
    fake_llm.fail = {"resume"}
    resolved = client.post(f"/tickets/{ticket_id}/reply", json={"message": "Payout reissued."}, headers=ANA)
    assert resolved.status_code == 200
    delivered = store.get_messages(conversation_id)[-1]["text"]
    assert "Payout reissued." in delivered and ticket_id in delivered


def test_an_operator_reading_a_ticket_is_audited(fake_llm):
    _, ticket_id = escalate(fake_llm)
    client.get(f"/tickets/{ticket_id}", headers=ANA)
    entry = store.audit_entries(USER)[-1]
    assert (entry["actor"], entry["action"]) == ("ana", "read_ticket")


def test_the_handoff_message_is_written_in_the_language_the_router_named(fake_llm):
    """Found by the evaluation: a handoff for an English question was worded in Portuguese."""
    fake_llm.script = [{"action": "escalation", "language": "English"}]
    run_chat("I want to talk to a person.", USER)
    assert "Write the message in English." in fake_llm.seen_messages[-1]
