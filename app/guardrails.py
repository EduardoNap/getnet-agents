"""Input guardrail"""
import re

from app.config import settings

CARD_MASK = "[card number removed]"
# 13 to 19 digits, optionally separated by single spaces or dashes.
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")

# Typical attempts to override the assistant's instructions
BLOCKED_PHRASES = [
    "ignore all previous instructions",
    "ignore previous instructions",
    "ignore your instructions",
    "system prompt",
    "ignore as instruções",
    "prompt do sistema",
    "jailbreak",
]


def check_input(message: str) -> str | None:
    """Return why the message is blocked, or None when it may go on to the agents."""
    if not message.strip():
        return "empty_message"
    if len(message) > settings.max_message_chars:
        return "message_too_long"
    lowered = message.lower()
    if any(phrase in lowered for phrase in BLOCKED_PHRASES):
        return "prompt_injection"
    return None


def _passes_luhn(digits: str) -> bool:
    """The checksum every payment card number satisfies. It keeps order ids and phone numbers unmasked."""
    total = 0
    for position, digit in enumerate(reversed(digits)):
        value = int(digit)
        if position % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def mask_card_numbers(text: str) -> str:
    """Replace card numbers so they are never stored, logged or sent to a model."""

    def replace(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        return CARD_MASK if _passes_luhn(digits) else match.group()

    return _CARD_CANDIDATE.sub(replace, text)
