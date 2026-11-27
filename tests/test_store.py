"""The store: ownership, ticket state transitions and idempotent repeats."""
import sqlite3

import pytest

from app import store
from app.config import settings

USER, OTHER = "cliente1988", "maria_2020"


def test_a_conversation_is_only_visible_to_its_owner():
    conversation_id = store.create_conversation(USER)
    assert store.get_conversation(conversation_id, USER)["user_id"] == USER
    with pytest.raises(store.NotFound):
        store.get_conversation(conversation_id, OTHER)
    with pytest.raises(store.NotFound):
        store.get_conversation("does-not-exist", USER)


def test_messages_are_on_disk_and_come_back_oldest_first():
    conversation_id = store.create_conversation(USER)
    store.add_message(conversation_id, "user", "first")
    store.add_message(conversation_id, "assistant", "second")
    assert [m["text"] for m in store.get_messages(conversation_id)] == ["first", "second"]
    # A separate connection, as a restarted process would open, sees the same rows.
    rows = sqlite3.connect(settings.database_path).execute("SELECT text FROM messages ORDER BY id").fetchall()
    assert [row[0] for row in rows] == ["first", "second"]


def test_a_conversation_has_one_unresolved_ticket():
    first, second = store.create_conversation(USER), store.create_conversation(USER)
    ticket = store.open_ticket(first, USER, "wants a human", "summary")
    again = store.open_ticket(first, USER, "still wants a human", "summary")
    other = store.open_ticket(second, USER, "wants a human", "summary")
    assert ticket["ticket_id"].startswith("TCK-")
    assert again["ticket_id"] == ticket["ticket_id"]
    assert other["ticket_id"] != ticket["ticket_id"]
    assert [t["ticket_id"] for t in store.list_tickets("open")] == [ticket["ticket_id"], other["ticket_id"]]


def test_claiming_twice_is_harmless_and_a_second_operator_is_refused():
    ticket_id = store.open_ticket(store.create_conversation(USER), USER, "reason", "summary")["ticket_id"]
    assert store.claim_ticket(ticket_id, "ana")["status"] == "claimed"
    assert store.claim_ticket(ticket_id, "ana")["operator"] == "ana"
    with pytest.raises(store.Conflict):
        store.claim_ticket(ticket_id, "bruno")


def test_resolving_twice_answers_once():
    conversation_id = store.create_conversation(USER)
    ticket_id = store.open_ticket(conversation_id, USER, "reason", "summary")["ticket_id"]
    store.claim_ticket(ticket_id, "ana")

    ticket, changed = store.resolve_ticket(ticket_id, "ana", "Payout reissued.", "Your payout was reissued.")
    repeat, changed_again = store.resolve_ticket(ticket_id, "ana", "Payout reissued.", "a different wording")

    assert (changed, changed_again) == (True, False)
    assert repeat["merchant_message"] == ticket["merchant_message"] == "Your payout was reissued."
    assert [m["role"] for m in store.get_messages(conversation_id)] == ["human_agent", "assistant"]
    assert store.unresolved_ticket(conversation_id) is None


def test_a_ticket_cannot_be_resolved_unclaimed_or_by_another_operator():
    ticket_id = store.open_ticket(store.create_conversation(USER), USER, "reason", "summary")["ticket_id"]
    with pytest.raises(store.Conflict):
        store.resolve_ticket(ticket_id, "ana", "reply", "message")
    store.claim_ticket(ticket_id, "ana")
    with pytest.raises(store.Conflict):
        store.resolve_ticket(ticket_id, "bruno", "reply", "message")
    with pytest.raises(store.NotFound):
        store.get_ticket("TCK-NOPE")


def test_after_a_ticket_is_resolved_a_new_one_can_be_opened():
    conversation_id = store.create_conversation(USER)
    first = store.open_ticket(conversation_id, USER, "reason", "summary")["ticket_id"]
    store.claim_ticket(first, "ana")
    store.resolve_ticket(first, "ana", "reply", "message")
    assert store.open_ticket(conversation_id, USER, "another problem", "summary")["ticket_id"] != first


def test_the_audit_log_records_who_read_whose_data():
    store.audit("cliente1988", "get_recent_transactions", "cliente1988", "trace-1")
    store.audit("ana", "read_ticket", "maria_2020", "")
    assert [e["action"] for e in store.audit_entries("cliente1988")] == ["get_recent_transactions"]
    assert len(store.audit_entries()) == 2


def test_concurrent_first_requests_do_not_lock_the_database():
    """Found by the evaluation: parallel requests on a fresh database used to fail with 'database is locked'."""
    from concurrent.futures import ThreadPoolExecutor

    store.reset()  # the next call is the first one again
    with ThreadPoolExecutor(8) as pool:
        ids = list(pool.map(lambda _: store.create_conversation(USER), range(16)))
    assert len(set(ids)) == 16


# --- migrations ------------------------------------------------------------------------------


def use_database(monkeypatch, path):
    """Point the store at another file, as a deployment with its own volume would."""
    import dataclasses

    monkeypatch.setattr(store, "settings", dataclasses.replace(settings, database_path=path))
    monkeypatch.setattr(store, "_ready", False)


def test_a_new_database_is_built_by_numbered_migrations(tmp_path, monkeypatch):
    from app import migrations

    use_database(monkeypatch, tmp_path / "new.db")
    store.init()
    applied = store.applied_migrations()
    assert [m["version"] for m in applied] == list(range(1, len(migrations.MIGRATIONS) + 1))
    assert all(m["name"] and m["applied_at"] for m in applied)

    store.init()  # starting again applies nothing twice
    monkeypatch.setattr(store, "_ready", False)
    store.init()
    assert store.applied_migrations() == applied


def test_a_version_2_database_is_upgraded_and_keeps_its_data(tmp_path, monkeypatch):
    path = tmp_path / "v2.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
            summarized_upto INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL,
            text TEXT NOT NULL, trace_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE tickets (ticket_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, user_id TEXT NOT NULL,
            reason TEXT NOT NULL, summary TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', operator TEXT, reply TEXT,
            merchant_message TEXT, created_at TEXT NOT NULL, claimed_at TEXT, resolved_at TEXT);
        CREATE UNIQUE INDEX one_unresolved_ticket ON tickets(conversation_id) WHERE status != 'resolved';
        CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
            action TEXT NOT NULL, user_id TEXT NOT NULL, trace_id TEXT NOT NULL DEFAULT '');
        INSERT INTO conversations (id, user_id, created_at) VALUES ('c1', 'cliente1988', '2026-11-01T10:00:00+00:00');
        INSERT INTO messages (conversation_id, role, text, created_at) VALUES ('c1', 'user', 'from version 2', '2026-11-01T10:00:00+00:00');
        INSERT INTO tickets (ticket_id, conversation_id, user_id, reason, summary, created_at)
            VALUES ('TCK-OLD', 'c1', 'cliente1988', 'wants a human', 'summary', '2026-11-01T10:00:00+00:00');
        """
    )
    old.commit()
    old.close()

    use_database(monkeypatch, path)
    store.init()
    assert [m["text"] for m in store.get_messages("c1")] == ["from version 2"]
    ticket = store.get_ticket("TCK-OLD")
    assert (ticket["kind"], ticket["priority"]) == ("question", "normal")  # the new columns, with their defaults
    # Everything version 3 added works on the upgraded database.
    assert store.create_action("c1", "cliente1988", "terminal_replacement", "GS-48213", "broken")["status"] == "pending"
    assert store.membership("joao.silva", "cliente1988")["status"] == "active"
    assert store.applied_migrations()[-1]["version"] >= 4


# --- the rate limit, the backup and the API key ------------------------------------------------


def test_the_rate_limit_is_shared_by_every_process():
    """It used to be counted in each process's memory, so two workers allowed twice the limit."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    from app import ratelimit

    for _ in range(settings.rate_limit_per_minute):
        ratelimit.check("joao.silva", now=6000.0)
    code = (
        "from app import ratelimit\n"
        "try:\n    ratelimit.check('joao.silva', now=6000.0); print('allowed')\n"
        "except ratelimit.RateLimited:\n    print('limited')\n"
        "ratelimit.check('maria.santos', now=6000.0); print('other allowed')"
    )
    other_process = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=Path(__file__).parent.parent, env=dict(os.environ)
    )
    assert other_process.stdout.split("\n")[:2] == ["limited", "other allowed"], other_process.stderr[-400:]


def test_the_rate_limit_starts_again_each_minute():
    from app import ratelimit

    for _ in range(settings.rate_limit_per_minute):
        ratelimit.check("joao.silva", now=6000.0)
    with pytest.raises(ratelimit.RateLimited):
        ratelimit.check("joao.silva", now=6030.0)  # the same minute
    ratelimit.check("joao.silva", now=6060.0)  # the next one
    rows = sqlite3.connect(settings.database_path).execute("SELECT COUNT(*) FROM rate_limits").fetchone()[0]
    assert rows == 1  # the finished minute's count was removed


def test_a_backup_brings_the_database_back(tmp_path):
    from app import backup

    conversation_id = store.create_conversation(USER)
    store.add_message(conversation_id, "user", "before the backup")
    copy = backup.save(tmp_path / "copy.db")

    store.add_message(conversation_id, "user", "after the backup")
    store.open_ticket(conversation_id, USER, "wants a human", "summary")
    backup.restore(copy)
    assert [m["text"] for m in store.get_messages(conversation_id)] == ["before the backup"]
    assert store.list_tickets() == []
    with pytest.raises(FileNotFoundError):
        backup.restore(tmp_path / "missing.db")  # a wrong path must not empty the live database


def test_the_api_key_can_come_from_a_mounted_secret_file(tmp_path, monkeypatch):
    """Docker and Kubernetes hand secrets to a container as files. The key then never sits in the environment."""
    import dataclasses
    import sys
    import types

    from app import llm

    created = {}
    fake_sdk = types.SimpleNamespace(Anthropic=lambda **options: created.update(options) or "client")
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)
    secret = tmp_path / "anthropic_api_key"
    secret.write_text("sk-ant-from-a-file\n")

    monkeypatch.setattr(llm, "settings", dataclasses.replace(settings, anthropic_api_key_file=str(secret)))
    llm._client.cache_clear()
    assert llm._client() == "client" and created["api_key"] == "sk-ant-from-a-file"

    monkeypatch.setattr(llm, "settings", settings)  # no file: the SDK reads ANTHROPIC_API_KEY itself
    llm._client.cache_clear()
    llm._client()
    assert created["api_key"] is None
    llm._client.cache_clear()
