"""The database schema, as numbered steps.

Each step runs once, in order, inside a transaction, and is recorded in `schema_migrations`. The
service applies the missing ones when it starts; `python -m app.migrations` does the same from the
command line and prints what is applied.

"""
import sqlite3
from datetime import datetime, timezone


def _version_2(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            summarized_upto INTEGER NOT NULL DEFAULT 0,  -- id of the last message folded into the summary
            created_at TEXT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            role TEXT NOT NULL,  -- user | assistant | human_agent
            text TEXT NOT NULL,
            trace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            user_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            summary TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',  -- open -> claimed -> resolved
            operator TEXT,
            reply TEXT,
            merchant_message TEXT,
            created_at TEXT NOT NULL,
            claimed_at TEXT,
            resolved_at TEXT
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            user_id TEXT NOT NULL,  -- the merchant whose data was read
            trace_id TEXT NOT NULL DEFAULT ''
        )"""
    )


def _version_3(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(tickets)")}
    for name, definition in (
        ("kind", "TEXT NOT NULL DEFAULT 'question'"),  # question: a human answers | approval: a human decides an action
        ("priority", "TEXT NOT NULL DEFAULT 'normal'"),  # high | normal
        ("due_at", "TEXT"),
    ):
        if name not in columns:
            db.execute(f"ALTER TABLE tickets ADD COLUMN {name} {definition}")
    # A conversation has at most one question a human still owes an answer to. Approvals do not count.
    db.execute("DROP INDEX IF EXISTS one_unresolved_ticket")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS one_unresolved_question ON tickets(conversation_id) "
        "WHERE status != 'resolved' AND kind = 'question'"
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS actions (
            action_id TEXT PRIMARY KEY,
            ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,  -- terminal_replacement
            target TEXT NOT NULL,  -- the terminal's serial number
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',  -- pending -> approved -> executed, or pending -> rejected
            decided_by TEXT,
            decision_reason TEXT,
            result TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT
        )"""
    )
    # The same action is not proposed twice while it waits for a decision.
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_pending_action ON actions(user_id, kind, target) WHERE status = 'pending'")


def _memberships(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE IF NOT EXISTS memberships (
            subject     TEXT NOT NULL,  -- the person in the token
            merchant_id TEXT NOT NULL,  -- a merchant that person may act for
            status      TEXT NOT NULL DEFAULT 'active',
            PRIMARY KEY (subject, merchant_id)
        )"""
    )


def _turns_and_rate_limits(db: sqlite3.Connection) -> None:
    db.execute(
        """CREATE TABLE turns (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES conversations(id),
            idempotency_key TEXT,            -- from the request; null when the client sent none
            request_hash TEXT NOT NULL,      -- so a key cannot be reused for a different message
            status TEXT NOT NULL DEFAULT 'running',  -- running -> done; interrupted when the run stopped part-way
            checkpoint TEXT,                 -- JSON: what the agents had found after the last finished step
            result TEXT,                     -- JSON: the response, returned again when the key is repeated
            lease_until TEXT,                -- while running, the conversation is busy until this time
            created_at TEXT NOT NULL,
            finished_at TEXT
        )"""
    )
    db.execute("CREATE UNIQUE INDEX one_turn_per_key ON turns(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL")
    db.execute("CREATE INDEX turns_by_conversation ON turns(conversation_id, status)")
    db.execute(
        """CREATE TABLE rate_limits (
            key TEXT NOT NULL,        -- the principal
            window INTEGER NOT NULL,  -- the minute, counted from 1970
            count INTEGER NOT NULL,
            PRIMARY KEY (key, window)
        )"""
    )


MIGRATIONS = [
    (1, "version 2: conversations, messages, tickets, audit log", _version_2),
    (2, "version 3: ticket kind, priority and due time; actions awaiting approval", _version_3),
    (3, "memberships: which merchants a person may act for", _memberships),
    (4, "turns (checkpoints and idempotency keys) and shared rate limits", _turns_and_rate_limits),
]


def apply(db: sqlite3.Connection) -> list[int]:
    """Run every step this database has not had. Returns the versions applied now."""
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    db.commit()
    done = {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
    applied = []
    for version, name, step in MIGRATIONS:
        if version in done:
            continue
        db.execute("BEGIN IMMEDIATE")  # one writer at a time: two processes starting together do not both run a step
        try:
            if db.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone() is None:
                step(db)
                db.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
                applied.append(version)
            db.commit()
        except BaseException:
            db.rollback()  # a failed step leaves no half-made tables and no record
            raise
    return applied


if __name__ == "__main__":
    from app import store

    store.init()
    for row in store.applied_migrations():
        print(f"{row['version']:>3}  {row['applied_at']}  {row['name']}")
