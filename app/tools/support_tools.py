"""Customer support tools over mock account data."""
import json
import re
from datetime import date, timedelta
from functools import lru_cache

from app import store
from app.config import settings

USER_NOT_FOUND = {"error": "user_not_found"}


@lru_cache
def _users() -> dict:
    return json.loads((settings.data_dir / "users.json").read_text(encoding="utf-8"))


def _day(offset: int) -> str:
    """Mock data stores day offsets"""
    return (date.today() + timedelta(days=offset)).isoformat()


def account_status(user_id: str) -> str | None:
    """"active", another status, or None when there is no such merchant. Used for authorization."""
    user = _users().get(user_id)
    return user["status"] if user else None


def get_settlement_schedule(user_id: str) -> dict:
    user = _users().get(user_id)
    if not user:
        return USER_NOT_FOUND
    settlements = [
        {
            "sale_date": _day(-s["sale_days_ago"]),
            "method": s["method"],
            "gross": s["gross"],
            "fees": s["fees"],
            "net": s["net"],
            "payout_date": _day(s["payout_in_days"]),
            "status": s["status"],
        }
        for s in user["settlements"]
    ]
    return {
        "today": _day(0),
        "currency": "BRL",
        "bank_account": user["bank_account"],
        "settlement_terms": user["settlement_terms"],
        "settlements": settlements,
    }


def get_terminal_status(user_id: str) -> dict:
    user = _users().get(user_id)
    if not user:
        return USER_NOT_FOUND
    return {"terminals": user["terminals"]}


def get_recent_transactions(user_id: str) -> dict:
    user = _users().get(user_id)
    if not user:
        return USER_NOT_FOUND
    transactions = [
        {"date": _day(-t["days_ago"]), **{k: v for k, v in t.items() if k != "days_ago"}}
        for t in user["transactions"]
    ]
    return {"currency": "BRL", "transactions": transactions}


URGENT = re.compile(r"fraud|stolen|roub|clon|chargeback|complain|reclama|unauthori[sz]ed|não reconhe", re.IGNORECASE)


def create_support_ticket(user_id: str, reason: str, summary: str, conversation_id: str) -> dict:
    """Open a ticket for a human agent. A conversation that already has one open gets that one back.
    Fraud and complaints go to the front of the queue."""
    priority = "high" if URGENT.search(f"{reason} {summary}") else "normal"
    return store.open_ticket(conversation_id, user_id, reason, summary, priority=priority)


def propose_terminal_replacement(user_id: str, terminal_id: str, reason: str, conversation_id: str, request: str = "") -> dict:
    """Ask for one of this merchant's terminals to be replaced. Nothing is sent until a human approves."""
    serials = {terminal["serial"] for terminal in _users().get(user_id, {}).get("terminals", [])}
    if terminal_id not in serials:
        return {"error": "terminal_not_found", "detail": "No terminal with that serial number belongs to this merchant."}
    action = store.create_action(conversation_id, user_id, "terminal_replacement", terminal_id, reason, request)
    return {
        "status": "pending_approval",
        "terminal": terminal_id,
        "ticket_id": action["ticket_id"],
        "note": "Nothing has been sent yet. A human agent must approve the replacement first.",
    }


def execute_terminal_replacement(action: dict) -> str:
    """Place the replacement order. The action id is the order's key, so placing it twice gives the same order."""
    return f"RPL-{action['action_id'][-8:]}"
