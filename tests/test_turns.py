"""A turn is saved step by step, an interrupted one continues, and a repeated request runs once."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import store
from app.config import settings
from app.graph import run_turn
from app.main import app
from tests.conftest import ProcessKilled, auth_header

client = TestClient(app)
USER = "cliente1988"
BODY = {"message": "When will my sales be paid out?", "user_id": USER}


def chat(key: str | None = None, **changes):
    headers = auth_header(USER) | ({"Idempotency-Key": key} if key else {})
    return client.post("/chat", json={**BODY, **changes}, headers=headers)


def turns() -> list[dict]:
    db = sqlite3.connect(settings.database_path)
    db.row_factory = sqlite3.Row
    return [dict(row) for row in db.execute("SELECT * FROM turns ORDER BY created_at, rowid")]


# --- the same request sent twice ------------------------------------------------------------


def test_a_request_repeated_with_the_same_key_runs_once(fake_llm):
    fake_llm.route = "support"
    fake_llm.tools_to_call = [("get_settlement_schedule", {})]
    first = chat(key="order-17")
    calls = len(fake_llm.seen_messages)

    again = chat(key="order-17")
    assert again.status_code == 200
    assert again.json() == first.json()  # the same answer, trace and conversation
    assert len(fake_llm.seen_messages) == calls  # no model call the second time
    assert [m["role"] for m in store.get_messages(first.json()["conversation_id"])] == ["user", "assistant"]  # stored once


def test_without_a_key_the_same_message_is_two_turns(fake_llm):
    first, second = chat(), chat()
    assert first.json()["conversation_id"] != second.json()["conversation_id"]
    assert len(turns()) == 2


def test_a_key_cannot_be_reused_for_a_different_message(fake_llm):
    assert chat(key="order-17").status_code == 200
    assert chat(key="order-17", message="Something else entirely").status_code == 409


def test_a_key_belongs_to_one_merchant(fake_llm):
    """Two merchants may pick the same key; neither sees the other's answer."""
    mine = chat(key="k1").json()
    theirs = client.post(
        "/chat", json={**BODY, "user_id": "maria_2020"}, headers=auth_header("maria_2020") | {"Idempotency-Key": "k1"}
    ).json()
    assert theirs["conversation_id"] != mine["conversation_id"]


# --- a turn that stops half-way ---------------------------------------------------------------


def test_an_interrupted_turn_continues_from_its_last_saved_step(fake_llm):
    fake_llm.script = ["support", "knowledge", "finish"]
    fake_llm.tools_to_call = [("get_settlement_schedule", {})]
    fake_llm.kill = {"knowledge"}  # the process dies after the first specialist finished, while the second is working
    with pytest.raises(ProcessKilled):
        run_turn(BODY["message"], USER, idempotency_key="order-18")
    saved = turns()[0]
    assert saved["status"] == "interrupted" and "get_settlement_schedule" in saved["checkpoint"]
    assert store.get_messages(saved["conversation_id"]) == []  # nothing was told to the merchant yet

    fake_llm.kill = set()
    fake_llm.continue_with(["knowledge", "finish"])  # the router sees support's saved result and sends the other step again
    final = run_turn(BODY["message"], USER, idempotency_key="order-18")
    assert "Step 1: support" in fake_llm.router_inputs[-2]  # it was shown what had already been found
    assert fake_llm.agent_calls.count("support") == 1  # the specialist that had finished is not called again
    assert fake_llm.agent_calls.count("knowledge") == 2  # the one that was cut off runs again
    assert final["response"] and final["conversation_id"] == saved["conversation_id"]
    assert [step["agent"] for step in final["steps"]].count("support") == 1  # the earlier step is still in the record
    assert final["trace_id"] and all(m["trace_id"] == final["trace_id"] for m in store.get_messages(final["conversation_id"]))
    done = turns()[0]
    assert done["status"] == "done" and done["checkpoint"] is None  # the working state is not kept once the turn is done


def test_a_turn_that_died_without_a_trace_is_taken_over_when_its_lease_ends(fake_llm, monkeypatch):
    """A killed process cannot mark its turn interrupted. The turn stays `running` until its lease runs out."""
    turn = store.begin_turn(USER, None, BODY["message"], "order-19")
    store.save_step(turn["id"], {"findings": [], "steps": [{"agent": "guardrail", "status": "ok"}]})

    with pytest.raises(store.Conflict):  # the lease is still held: it may be running in another process
        run_turn(BODY["message"], USER, idempotency_key="order-19")

    monkeypatch.setattr(store, "LEASE_SECONDS", -1)  # as if the lease time had passed
    store.save_step(turn["id"], {"findings": [], "steps": [{"agent": "guardrail", "status": "ok"}]})
    final = run_turn(BODY["message"], USER, idempotency_key="order-19")
    assert final["response"] and final["conversation_id"] == turn["conversation_id"]


def test_one_turn_at_a_time_in_a_conversation(fake_llm):
    conversation_id = chat().json()["conversation_id"]
    store.begin_turn(USER, conversation_id, "a message still being answered", None)  # another request holds the conversation
    busy = chat(conversation_id=conversation_id)
    assert busy.status_code == 409
    assert len(store.get_messages(conversation_id)) == 2  # only the first turn's messages


def test_a_card_number_is_not_kept_in_the_saved_turn(fake_llm):
    fake_llm.route = "support"
    fake_llm.kill = {"support"}
    with pytest.raises(ProcessKilled):
        run_turn("The card 4111 1111 1111 1111 was declined, why?", USER, idempotency_key="order-20")
    assert "4111" not in str(turns())


def test_someone_elses_conversation_cannot_be_reached_through_a_turn(fake_llm):
    marias = client.post("/chat", json={**BODY, "user_id": "maria_2020"}, headers=auth_header("maria_2020")).json()["conversation_id"]
    assert chat(key="order-21", conversation_id=marias).status_code == 404
    assert len(turns()) == 1  # no turn was started
