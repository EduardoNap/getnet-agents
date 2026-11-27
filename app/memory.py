"""Conversation memory: which earlier turns the agents get to see.

The agents receive a running summary plus the messages after it, never the whole history.
"""
import logging

from app import llm, store
from app.config import settings

logger = logging.getLogger("getnet")

SUMMARY_PROMPT = """You keep the running summary of a support conversation between a merchant and \
Getnet's assistant. Rewrite the summary so that it also covers the new messages.

Keep the facts a later answer may need: what the merchant asked, what was found (dates, amounts, \
serial numbers, error codes, ticket numbers) and what is still open. Leave out greetings and wording.
At most 120 words. Write only the summary."""

SPEAKERS = {"user": "merchant", "assistant": "assistant", "human_agent": "human agent"}


def _format(messages: list[dict]) -> str:
    return "\n".join(f"{SPEAKERS[m['role']]}: {m['text']}" for m in messages)


def _after_summary(conversation: dict) -> list[dict]:
    return [m for m in store.get_messages(conversation["id"]) if m["id"] > conversation["summarized_upto"]]


def load(conversation: dict) -> str:
    """The context for a new turn: the summary, then every message it does not cover. "" when new."""
    parts = []
    if conversation["summary"]:
        parts.append(f"Summary of earlier turns: {conversation['summary']}")
    recent = _after_summary(conversation)
    if recent:
        parts.append(_format(recent))
    return "\n".join(parts)


def summarize_if_long(conversation: dict) -> None:
    """Fold older messages into the summary, keeping the latest ones word for word."""
    outside = _after_summary(conversation)
    if len(outside) <= settings.summarize_after:
        return
    older = outside[: -settings.history_window]
    try:
        result = llm.run_agent(
            system=SUMMARY_PROMPT,
            user=f"Current summary: {conversation['summary'] or '(none yet)'}\n\nNew messages:\n{_format(older)}",
            tools=[],
            handlers={},
        )
        if result.text:
            store.set_summary(conversation["id"], result.text, older[-1]["id"])
    except Exception:  # memory is a convenience: the turn already succeeded
        logger.warning("could not update the conversation summary; the recent messages are kept in full")


def request_text(state: dict) -> str:
    """What a specialist is given: the conversation so far, the merchant's message, and its own task."""
    parts = []
    if state.get("history"):
        parts.append(f"Conversation so far:\n{state['history']}")
    parts.append(f"Merchant's message: {state['message']}")
    task = state.get("task")
    if task and task != state["message"]:
        parts.append(
            f"Your task for this step: {task}\n"
            "Answer only this task. Other parts of the merchant's message are handled separately, "
            "so do not answer them and do not mention them."
        )
    parts.append(language_rule(state))
    return "\n\n".join(part for part in parts if part)


def language_rule(state: dict, what: str = "your answer") -> str:
    """The language is named outright. "Reply in the merchant's language" was not enough: with Portuguese
    data in front of it, the model answered English questions in Portuguese."""
    return f"Write {what} in {state['language']}." if state.get("language") else ""
