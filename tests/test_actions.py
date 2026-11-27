"""An action the agent can only propose: a human approves or rejects it, and it runs at most once."""
from fastapi.testclient import TestClient

from app import store
from app.graph import run_chat
from app.main import app
from tests.conftest import auth_header

USER, OTHER = "cliente1988", "maria_2020"
ANA, BRUNO = auth_header("ana", "operator"), auth_header("bruno", "operator")
client = TestClient(app)


def propose(fake_llm, terminal="GS-48213", user=USER):
    """The merchant asks for a replacement and the Support Agent proposes it. Returns the chat response."""
    fake_llm.script = ["support", "finish"]
    fake_llm.tools_to_call = [("request_terminal_replacement", {"terminal_id": terminal, "reason": "offline for days"})]
    response = run_chat(f"Please replace my terminal {terminal}.", user)
    fake_llm.script, fake_llm.tools_to_call = [], []
    return response


def approval_ticket() -> dict:
    return next(ticket for ticket in store.list_tickets() if ticket["kind"] == "approval")


def test_the_agent_can_only_propose_a_replacement(fake_llm):
    response = propose(fake_llm)
    actions = store.list_actions(USER)
    assert [(a["kind"], a["target"], a["status"]) for a in actions] == [("terminal_replacement", "GS-48213", "pending")]
    ticket = approval_ticket()
    assert (ticket["status"], ticket["conversation_id"]) == ("open", response.conversation_id)
    assert response.handoff is None  # a pending action is not a handoff
    assert ticket["summary"] == "Please replace my terminal GS-48213."  # the merchant's own words, for the operator and the reply
    seen = client.get(f"/tickets/{ticket['ticket_id']}", headers=ANA).json()  # what the operator decides on
    assert (seen["action"]["kind"], seen["action"]["target"], seen["action"]["reason"]) == ("terminal_replacement", "GS-48213", "offline for days")
    # The conversation is not on hold: the next message is answered by the agents.
    again = run_chat("Thanks. Is my other machine online?", USER, response.conversation_id)
    assert "hold" not in [step["agent"] for step in again.agent_workflow]


def test_a_terminal_of_another_merchant_cannot_be_proposed(fake_llm):
    propose(fake_llm, terminal="GM-77001")  # maria_2020's machine
    assert store.list_actions(USER) == [] and store.list_actions(OTHER) == []
    assert store.list_tickets() == []
    assert "terminal_not_found" in str(fake_llm.tool_outputs[-1])


def test_proposing_the_same_replacement_twice_creates_one_action(fake_llm):
    propose(fake_llm)
    propose(fake_llm)
    assert len(store.list_actions(USER)) == 1


def test_approval_executes_the_action_once_and_tells_the_merchant(fake_llm):
    response = propose(fake_llm)
    ticket_id = approval_ticket()["ticket_id"]
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)

    first = client.post(f"/tickets/{ticket_id}/approve", headers=ANA)
    again = client.post(f"/tickets/{ticket_id}/approve", headers=ANA)

    assert (first.status_code, again.status_code) == (200, 200)
    action = store.list_actions(USER)[0]
    assert (action["status"], action["decided_by"]) == ("executed", "ana")
    assert action["result"].startswith("RPL-") and first.json()["action"]["result"] == again.json()["action"]["result"]
    roles = [m["role"] for m in store.get_messages(response.conversation_id)]
    assert roles.count("human_agent") == 1  # the second approval added nothing
    assert action["result"] in store.get_messages(response.conversation_id)[-1]["text"]


def test_rejection_executes_nothing_and_gives_the_reason(fake_llm):
    response = propose(fake_llm)
    ticket_id = approval_ticket()["ticket_id"]
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)

    rejected = client.post(f"/tickets/{ticket_id}/reject", json={"message": "A technician visit is enough."}, headers=ANA)

    assert rejected.status_code == 200
    action = store.list_actions(USER)[0]
    assert (action["status"], action["result"]) == ("rejected", None)
    assert "A technician visit is enough." in store.get_messages(response.conversation_id)[-1]["text"]
    assert client.post(f"/tickets/{ticket_id}/approve", headers=ANA).status_code == 409  # decided: it cannot be turned around


def test_only_the_operator_who_claimed_the_ticket_decides(fake_llm):
    propose(fake_llm)
    ticket_id = approval_ticket()["ticket_id"]
    assert client.post(f"/tickets/{ticket_id}/approve", headers=ANA).status_code == 409  # not claimed yet
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)
    assert client.post(f"/tickets/{ticket_id}/approve", headers=BRUNO).status_code == 409
    assert client.post(f"/tickets/{ticket_id}/approve", headers=auth_header(USER)).status_code == 403  # a merchant cannot approve
    assert store.list_actions(USER)[0]["status"] == "pending"


def test_a_question_ticket_has_nothing_to_approve(fake_llm):
    fake_llm.script = ["escalation"]
    ticket_id = run_chat("I want a person.", USER).handoff["ticket_id"]
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)
    assert client.post(f"/tickets/{ticket_id}/approve", headers=ANA).status_code == 409


def test_a_claimed_ticket_can_be_released_back_to_the_queue(fake_llm):
    fake_llm.script = ["escalation"]
    ticket_id = run_chat("I want a person.", USER).handoff["ticket_id"]
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)
    assert client.post(f"/tickets/{ticket_id}/release", headers=BRUNO).status_code == 409  # not his
    released = client.post(f"/tickets/{ticket_id}/release", headers=ANA)
    assert (released.status_code, released.json()["status"], released.json()["operator"]) == (200, "open", None)
    assert client.post(f"/tickets/{ticket_id}/claim", headers=BRUNO).json()["operator"] == "bruno"


def test_fraud_goes_to_the_front_of_the_queue_and_late_tickets_are_listed(fake_llm, monkeypatch):
    fake_llm.script = [{"action": "escalation", "reason": "The merchant wants a human."}]
    normal = run_chat("I want a person.", USER).handoff["ticket_id"]
    fake_llm.script = [{"action": "escalation", "reason": "Possible fraud on a sale."}]
    urgent = run_chat("Someone used a stolen card in my shop.", OTHER).handoff["ticket_id"]

    queue = client.get("/tickets", headers=ANA).json()
    assert [t["ticket_id"] for t in queue] == [urgent, normal]
    assert [t["priority"] for t in queue] == ["high", "normal"]
    assert client.get("/tickets?overdue=true", headers=ANA).json() == []

    monkeypatch.setattr(store, "_now", lambda: "2999-01-01T00:00:00+00:00")  # long after both were due
    assert {t["ticket_id"] for t in client.get("/tickets?overdue=true", headers=ANA).json()} == {urgent, normal}


def test_the_decision_is_worded_from_the_merchants_own_message(fake_llm):
    """Found by the blind evaluation: the reply to a Portuguese merchant came back in English, because the
    writer was shown the agent's English reason in place of the merchant's message."""
    propose(fake_llm)
    ticket_id = approval_ticket()["ticket_id"]
    client.post(f"/tickets/{ticket_id}/claim", headers=ANA)
    client.post(f"/tickets/{ticket_id}/reject", json={"message": "A visit is enough."}, headers=ANA)
    assert "Merchant's original message: Please replace my terminal GS-48213." in fake_llm.seen_messages[-1]
