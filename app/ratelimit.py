"""Requests per principal per minute.

The count is kept in the database, so every process that serves requests shares it. Each minute
starts a new count. That allows a short burst across the turn of a minute, which is acceptable here:
the limit exists to stop a runaway client, not to meter usage exactly.
"""
import time

from app import store
from app.config import settings

WINDOW_SECONDS = 60
clock = time.time  # replaced in tests


class RateLimited(Exception):
    """This principal has used its requests for the current minute."""


def check(key: str, now: float | None = None) -> None:
    window = int((clock() if now is None else now) // WINDOW_SECONDS)
    if store.count_request(key, window) > settings.rate_limit_per_minute:
        raise RateLimited(key)


def reset() -> None:
    store.clear_rate_limits()
