"""Persistent state in one SQLite file: conversations, messages, turns, tickets, actions, memberships,
rate limits and the audit log. The tables are defined in `app/migrations.py`.

Every function opens its own connection, so nothing lives in process memory and a restart
loses nothing. Moving to Postgres for several replicas means changing this file and the migrations.
"""
import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from app import migrations
from app.config import settings

LEASE_SECONDS = 120  # a running turn holds its conversation this long after its last saved step

_ready = False
_setup_lock = threading.Lock()  # concurrent first requests must not set the database up at the same time


class NotFound(LookupError):
    """The record does not exist, or the caller is not allowed to know that it does."""


class Conflict(RuntimeError):
    """The record is not in a state that allows this change."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path, timeout=10)  # waits up to 10 s for another writer
    connection.row_factory = sqlite3.Row
    return connection


def _setup() -> None:
    global _ready
    with _setup_lock:
        if _ready:
            return
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = _connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL")  # readers do not block the writer
            migrations.apply(connection)
            _seed_memberships(connection)
            connection.commit()
        finally:
            connection.close()
        _ready = True


def _seed_memberships(connection: sqlite3.Connection) -> None:
    """The demo's memberships, from users.json. Rows already there are kept, so a change made here survives a restart.
    In production this table is fed by the company's customer directory."""
    users = json.loads((settings.data_dir / "users.json").read_text(encoding="utf-8"))
    connection.executemany(
        "INSERT OR IGNORE INTO memberships (subject, merchant_id, status) VALUES (?, ?, ?)",
        [(member["subject"], merchant_id, member["status"]) for merchant_id, user in users.items() for member in user.get("members", [])],
    )


@contextmanager
def _db():
    if not _ready:
        _setup()
    connection = _connect()
    try:
        with connection:  # commits, or rolls back if the block raises
            yield connection
    finally:
        connection.close()


def init() -> None:
    """Create or upgrade the database. Called when the service starts."""
    with _db():
        pass


def applied_migrations() -> list[dict]:
    with _db() as db:
        return [dict(row) for row in db.execute("SELECT * FROM schema_migrations ORDER BY version")]


def reset() -> None:
    """Empty every table. Used by the tests."""
    global _ready
    with _db() as db:
        for table in ("audit_log", "actions", "tickets", "turns", "messages", "conversations", "memberships", "rate_limits", "schema_migrations"):
            db.execute(f"DROP TABLE IF EXISTS {table}")
    with _setup_lock:
        _ready = False


# --- memberships ---------------------------------------------------------------------------


def membership(subject: str, merchant_id: str) -> dict | None:
    """This person's membership of this merchant, whatever its status, or None when there is none."""
    with _db() as db:
        row = db.execute("SELECT * FROM memberships WHERE subject = ? AND merchant_id = ?", (subject, merchant_id)).fetchone()
    return dict(row) if row else None


def set_membership(subject: str, merchant_id: str, status: str) -> None:
    """Grant, suspend or restore a person's access to a merchant. It applies from the next request."""
    with _db() as db:
        db.execute(
            "INSERT INTO memberships (subject, merchant_id, status) VALUES (?, ?, ?) "
            "ON CONFLICT (subject, merchant_id) DO UPDATE SET status = excluded.status",
            (subject, merchant_id, status),
        )


# --- conversations -------------------------------------------------------------------------


def create_conversation(user_id: str) -> str:
    conversation_id = uuid.uuid4().hex
    with _db() as db:
        db.execute(
            "INSERT INTO conversations (id, user_id, created_at) VALUES (?, ?, ?)", (conversation_id, user_id, _now())
        )
    return conversation_id


def get_conversation(conversation_id: str, user_id: str) -> dict:
    """The conversation, only for its owner. Unknown and someone else's look the same: NotFound."""
    with _db() as db:
        row = db.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
        ).fetchone()
    if row is None:
        raise NotFound("conversation not found")
    return dict(row)


def conversation_owner(conversation_id: str) -> str:
    """The merchant a conversation belongs to. NotFound when there is no such conversation."""
    with _db() as db:
        row = db.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if row is None:
        raise NotFound("conversation not found")
    return row["user_id"]


def add_message(conversation_id: str, role: str, text: str, trace_id: str = "") -> None:
    with _db() as db:
        _insert_message(db, conversation_id, role, text, trace_id)


def _insert_message(db, conversation_id: str, role: str, text: str, trace_id: str = "") -> None:
    db.execute(
        "INSERT INTO messages (conversation_id, role, text, trace_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (conversation_id, role, text, trace_id, _now()),
    )


def get_messages(conversation_id: str) -> list[dict]:
    """Oldest first."""
    with _db() as db:
        rows = db.execute(
            "SELECT id, role, text, trace_id, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_summary(conversation_id: str, summary: str, upto_message_id: int) -> None:
    with _db() as db:
        db.execute(
            "UPDATE conversations SET summary = ?, summarized_upto = ? WHERE id = ?",
            (summary, upto_message_id, conversation_id),
        )


# --- turns ---------------------------------------------------------------------------------
# One row per message being answered. It holds what the agents have found so far (the checkpoint),
# so an interrupted turn continues instead of starting over, and the response, so a request that is
# sent twice with the same Idempotency-Key is answered once.


def _lease() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat(timespec="seconds")


def _turn(row: sqlite3.Row) -> dict:
    turn = dict(row)
    for field in ("checkpoint", "result"):
        turn[field] = json.loads(turn[field]) if turn[field] else None
    return turn


def begin_turn(user_id: str, conversation_id: str | None, message: str, idempotency_key: str | None = None) -> dict:
    """Start answering a message, or pick up the turn this key already started.

    Returns the turn. `status` is "done" when the key was answered before (`result` holds the response),
    otherwise "running", with `checkpoint` set when an earlier attempt was interrupted.
    Raises NotFound when the conversation is not this merchant's, and Conflict when the key was used
    for another message, or when a turn is still running in this conversation.
    """
    now, request_hash = _now(), hashlib.sha256(message.encode()).hexdigest()
    with _db() as db:
        db.execute("BEGIN IMMEDIATE")  # one writer: two copies of the same request cannot both start
        if idempotency_key:
            row = db.execute("SELECT * FROM turns WHERE user_id = ? AND idempotency_key = ?", (user_id, idempotency_key)).fetchone()
            if row is not None:
                if row["request_hash"] != request_hash or conversation_id not in (None, row["conversation_id"]):
                    raise Conflict("this Idempotency-Key was already used for a different request")
                if row["status"] == "done":
                    return _turn(row)
                if row["status"] == "running" and row["lease_until"] > now:
                    raise Conflict("this request is still being processed")
                # Interrupted, or its process died and the lease ran out: this request takes it over.
                db.execute("UPDATE turns SET status = 'running', lease_until = ? WHERE id = ?", (_lease(), row["id"]))
                return _turn(db.execute("SELECT * FROM turns WHERE id = ?", (row["id"],)).fetchone())

        if conversation_id is None:
            conversation_id = uuid.uuid4().hex
            db.execute("INSERT INTO conversations (id, user_id, created_at) VALUES (?, ?, ?)", (conversation_id, user_id, now))
        else:
            owned = db.execute("SELECT 1 FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)).fetchone()
            if owned is None:
                raise NotFound("conversation not found")
            busy = db.execute(
                "SELECT 1 FROM turns WHERE conversation_id = ? AND status = 'running' AND lease_until > ?", (conversation_id, now)
            ).fetchone()
            if busy is not None:
                raise Conflict("another message in this conversation is still being answered")
        turn_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO turns (id, user_id, conversation_id, idempotency_key, request_hash, lease_until, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (turn_id, user_id, conversation_id, idempotency_key, request_hash, _lease(), now),
        )
        return _turn(db.execute("SELECT * FROM turns WHERE id = ?", (turn_id,)).fetchone())


def save_step(turn_id: str, checkpoint: dict) -> None:
    """Keep what the turn has so far, and hold the conversation a little longer."""
    with _db() as db:
        db.execute(
            "UPDATE turns SET checkpoint = ?, lease_until = ? WHERE id = ? AND status = 'running'",
            (json.dumps(checkpoint, ensure_ascii=False, default=str), _lease(), turn_id),
        )


def finish_turn(turn_id: str, result: dict, messages: list[tuple[str, str]], trace_id: str = "") -> None:
    """The turn is answered: its messages and its response are stored together, or not at all."""
    with _db() as db:
        conversation_id = db.execute("SELECT conversation_id FROM turns WHERE id = ?", (turn_id,)).fetchone()["conversation_id"]
        for role, text in messages:
            _insert_message(db, conversation_id, role, text, trace_id)
        db.execute(
            "UPDATE turns SET status = 'done', result = ?, checkpoint = NULL, lease_until = NULL, finished_at = ? WHERE id = ?",
            (json.dumps(result, ensure_ascii=False, default=str), _now(), turn_id),
        )


def update_turn_result(turn_id: str, result: dict) -> None:
    with _db() as db:
        db.execute("UPDATE turns SET result = ? WHERE id = ?", (json.dumps(result, ensure_ascii=False, default=str), turn_id))


def interrupt_turn(turn_id: str) -> None:
    """The run stopped part-way. The conversation is free again, and the same key continues from the checkpoint."""
    with _db() as db:
        db.execute("UPDATE turns SET status = 'interrupted', lease_until = NULL WHERE id = ? AND status = 'running'", (turn_id,))


# --- tickets -------------------------------------------------------------------------------


def open_ticket(
    conversation_id: str, user_id: str, reason: str, summary: str, kind: str = "question", priority: str = "normal"
) -> dict:
    """Create a ticket. A conversation that already has an unanswered question gets that ticket back."""
    ticket_id = f"TCK-{uuid.uuid4().hex[:8].upper()}"
    minutes = settings.sla_minutes_high if priority == "high" else settings.sla_minutes_normal
    due_at = (datetime.fromisoformat(_now()) + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    try:
        with _db() as db:
            db.execute(
                "INSERT INTO tickets (ticket_id, conversation_id, user_id, reason, summary, kind, priority, due_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ticket_id, conversation_id, user_id, reason, summary, kind, priority, due_at, _now()),
            )
    except sqlite3.IntegrityError:  # the unique index: an unanswered question already exists
        return unresolved_ticket(conversation_id)
    return get_ticket(ticket_id)


def unresolved_ticket(conversation_id: str) -> dict | None:
    """The question a human still owes this conversation an answer to. While it exists, no agent answers."""
    with _db() as db:
        row = db.execute(
            "SELECT * FROM tickets WHERE conversation_id = ? AND status != 'resolved' AND kind = 'question'", (conversation_id,)
        ).fetchone()
    return dict(row) if row else None


def get_ticket(ticket_id: str) -> dict:
    with _db() as db:
        row = db.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise NotFound("ticket not found")
    return dict(row)


def list_tickets(status: str | None = None, overdue: bool = False) -> list[dict]:
    """The operator queue: high priority first, then oldest first. `overdue` lists unresolved tickets past their due time."""
    query, values = "SELECT * FROM tickets", ()
    if overdue:
        query, values = query + " WHERE status != 'resolved' AND due_at < ?", (_now(),)
    elif status:
        query, values = query + " WHERE status = ?", (status,)
    with _db() as db:
        rows = db.execute(query + " ORDER BY priority = 'high' DESC, rowid", values).fetchall()
    return [dict(row) for row in rows]


def claim_ticket(ticket_id: str, operator: str) -> dict:
    """open -> claimed. Repeating the claim is harmless; another operator's claim is a Conflict."""
    with _db() as db:
        db.execute(
            "UPDATE tickets SET status = 'claimed', operator = ?, claimed_at = ? WHERE ticket_id = ? AND status = 'open'",
            (operator, _now(), ticket_id),
        )
    ticket = get_ticket(ticket_id)
    if ticket["operator"] != operator:
        raise Conflict("ticket is held by another operator")
    return ticket


def release_ticket(ticket_id: str, operator: str) -> dict:
    """claimed -> open, by the operator who holds it, so someone else can take it."""
    with _db() as db:
        released = db.execute(
            "UPDATE tickets SET status = 'open', operator = NULL, claimed_at = NULL "
            "WHERE ticket_id = ? AND status = 'claimed' AND operator = ?",
            (ticket_id, operator),
        ).rowcount
    ticket = get_ticket(ticket_id)
    if not released and ticket["status"] != "open":
        raise Conflict("only the operator holding an unresolved ticket can release it")
    return ticket


def resolve_ticket(ticket_id: str, operator: str, reply: str, merchant_message: str) -> tuple[dict, bool]:
    """claimed -> resolved, and put the human's answer into the conversation.

    Returns the ticket and whether this call changed it. A repeat by the same operator changes
    nothing and returns the stored result, so a retried request cannot answer twice.
    """
    with _db() as db:
        changed = (
            db.execute(
                "UPDATE tickets SET status = 'resolved', reply = ?, merchant_message = ?, resolved_at = ? "
                "WHERE ticket_id = ? AND status = 'claimed' AND operator = ?",
                (reply, merchant_message, _now(), ticket_id, operator),
            ).rowcount
            == 1
        )
        if changed:
            conversation_id = db.execute(
                "SELECT conversation_id FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()["conversation_id"]
            _insert_message(db, conversation_id, "human_agent", reply)
            _insert_message(db, conversation_id, "assistant", merchant_message)
    ticket = get_ticket(ticket_id)
    if not changed and not (ticket["status"] == "resolved" and ticket["operator"] == operator):
        raise Conflict("ticket must be claimed by this operator before it can be answered")
    return ticket, changed


# --- actions that need a human's approval ----------------------------------------------------


def create_action(conversation_id: str, user_id: str, kind: str, target: str, reason: str, request: str = "") -> dict:
    """Record a proposed action and put it in the operator queue. Proposing it again returns the pending one."""
    pending = _pending_action(user_id, kind, target)
    if pending:
        return pending
    # The ticket's summary is the merchant's own message: the operator reads it, and the reply is worded from it.
    ticket = open_ticket(conversation_id, user_id, f"Approval needed: {kind} of {target}. {reason}", request or reason, kind="approval")
    action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
    try:
        with _db() as db:
            db.execute(
                "INSERT INTO actions (action_id, ticket_id, user_id, kind, target, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_id, ticket["ticket_id"], user_id, kind, target, reason, _now()),
            )
    except sqlite3.IntegrityError:  # proposed at the same moment by another request
        return _pending_action(user_id, kind, target)
    return action_for_ticket(ticket["ticket_id"])


def _pending_action(user_id: str, kind: str, target: str) -> dict | None:
    with _db() as db:
        row = db.execute(
            "SELECT * FROM actions WHERE user_id = ? AND kind = ? AND target = ? AND status = 'pending'", (user_id, kind, target)
        ).fetchone()
    return dict(row) if row else None


def action_for_ticket(ticket_id: str) -> dict | None:
    with _db() as db:
        row = db.execute("SELECT * FROM actions WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def list_actions(user_id: str) -> list[dict]:
    with _db() as db:
        rows = db.execute("SELECT * FROM actions WHERE user_id = ? ORDER BY rowid", (user_id,)).fetchall()
    return [dict(row) for row in rows]


def decide_action(action_id: str, operator: str, approved: bool, reason: str = "") -> bool:
    """pending -> approved or rejected. True when this call made the decision: only then may the action be executed."""
    with _db() as db:
        return (
            db.execute(
                "UPDATE actions SET status = ?, decided_by = ?, decision_reason = ?, decided_at = ? "
                "WHERE action_id = ? AND status = 'pending'",
                ("approved" if approved else "rejected", operator, reason, _now(), action_id),
            ).rowcount
            == 1
        )


def record_execution(action_id: str, result: str) -> None:
    with _db() as db:
        db.execute("UPDATE actions SET status = 'executed', result = ? WHERE action_id = ? AND status = 'approved'", (result, action_id))


# --- rate limit ------------------------------------------------------------------------------


def count_request(key: str, window: int) -> int:
    """Add one request to this key's count for this minute, and return the count. One statement, so
    two processes counting at the same moment cannot both read the old number."""
    with _db() as db:
        db.execute("DELETE FROM rate_limits WHERE window < ?", (window,))  # minutes that are over
        row = db.execute(
            "INSERT INTO rate_limits (key, window, count) VALUES (?, ?, 1) "
            "ON CONFLICT (key, window) DO UPDATE SET count = count + 1 RETURNING count",
            (key, window),
        ).fetchone()
        return row["count"]


def clear_rate_limits() -> None:
    with _db() as db:
        db.execute("DELETE FROM rate_limits")


# --- audit log -----------------------------------------------------------------------------


def audit(actor: str, action: str, user_id: str, trace_id: str = "") -> None:
    with _db() as db:
        db.execute(
            "INSERT INTO audit_log (at, actor, action, user_id, trace_id) VALUES (?, ?, ?, ?, ?)",
            (_now(), actor, action, user_id, trace_id),
        )


def audit_entries(user_id: str | None = None) -> list[dict]:
    query, values = "SELECT * FROM audit_log", ()
    if user_id:
        query, values = query + " WHERE user_id = ?", (user_id,)
    with _db() as db:
        rows = db.execute(query + " ORDER BY id", values).fetchall()
    return [dict(row) for row in rows]
