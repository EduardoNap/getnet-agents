"""
Two functions cover every agent:
  classify()  - one call that must return a given schema (the router, the evaluation judge)
  run_agent() - the tool loop (knowledge, support, escalation, synthesizer)

Every call adds its tokens to the active meter, so each step can report what it used.
"""
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from app.config import CACHE_WRITE_FACTOR, PRICES_PER_MTOK, settings

logger = logging.getLogger("getnet")

# The basic search tool, on purpose: it returns the passages an answer quotes (citations), which are the
# evidence the router, the verifier and the judge check a general answer against. The newer variant
# filters results in a sandbox and returns no quoted passages (measured on 2026-11-26).
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}


class LLMRefusal(RuntimeError):
    """The model declined the request for safety reasons."""


@dataclass
class AgentResult:
    text: str
    tools_used: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)  # {"tool", "output"}: what the answer can be checked against


@dataclass
class Usage:
    input_tokens: int = 0  # everything the model read, cached or not
    output_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0
    cache_read_tokens: int = 0
    parent: "Usage | None" = field(default=None, repr=False)


_meter: ContextVar[Usage | None] = ContextVar("usage_meter", default=None)


@contextmanager
def meter():
    """Collect the usage of every model call made inside the block. Meters nest: a step inside a request."""
    parent = _meter.get()
    usage = Usage(parent=parent)
    token = _meter.set(usage)
    try:
        yield usage
    finally:
        _meter.reset(token)
        if parent is not None:
            parent.input_tokens += usage.input_tokens
            parent.output_tokens += usage.output_tokens
            parent.calls += usage.calls
            parent.cost_usd += usage.cost_usd
            parent.cache_read_tokens += usage.cache_read_tokens


def spent() -> float:
    """What the current request has cost so far: this step plus the steps before it."""
    usage, total = _meter.get(), 0.0
    while usage is not None:
        total += usage.cost_usd
        usage = usage.parent
    return total


def record_usage(
    model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0, cache_write_tokens: int = 0
) -> None:
    """`input_tokens` is the part of the prompt that was not cached, as the API reports it."""
    usage = _meter.get()
    if usage is None:
        return
    input_price, output_price, cache_read_price = PRICES_PER_MTOK.get(model, (0.0, 0.0, 0.0))
    usage.input_tokens += input_tokens + cache_read_tokens + cache_write_tokens
    usage.output_tokens += output_tokens
    usage.cache_read_tokens += cache_read_tokens
    usage.calls += 1
    usage.cost_usd += (
        input_tokens * input_price
        + output_tokens * output_price
        + cache_read_tokens * cache_read_price
        + cache_write_tokens * input_price * CACHE_WRITE_FACTOR
    ) / 1_000_000


def _record(model: str, usage) -> None:
    record_usage(
        model,
        usage.input_tokens,
        usage.output_tokens,
        getattr(usage, "cache_read_input_tokens", 0) or 0,
        getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )


def _cached(system: str) -> list[dict]:
    """The system prompt (and the tools, which come before it) is the same on every request, so it is cached."""
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


@lru_cache
def _client():
    import anthropic  # imported here, so the tests and the offline evaluations run without the SDK installed

    # The key comes from a mounted secret file when one is configured. Otherwise the SDK reads ANTHROPIC_API_KEY.
    key_file = settings.anthropic_api_key_file
    api_key = Path(key_file).read_text().strip() if key_file else None
    return anthropic.Anthropic(api_key=api_key, timeout=90.0, max_retries=2)


def classify(
    system: str, user: str, schema: type[BaseModel], model: str | None = None, effort: str = "low"
) -> BaseModel:
    """One model call whose answer is guaranteed to match `schema`."""
    model = model or settings.router_model
    response = _client().messages.parse(
        model=model,
        max_tokens=4000,
        system=_cached(system),
        messages=[{"role": "user", "content": user}],
        output_format=schema,
        output_config={"effort": effort},  # low for routing: favour speed
    )
    _record(model, response.usage)
    if response.stop_reason == "refusal":
        raise LLMRefusal("model refused to classify the message")
    return response.parsed_output


def run_agent(
    system: str,
    user: str,
    tools: list[dict],
    handlers: dict[str, Callable[[dict], Any]],
    max_turns: int = 6,
    model: str | None = None,
) -> AgentResult:
    """The agent loop: ask the model, run the tools it requests, send results back, repeat."""
    model = model or settings.model
    messages: list[dict] = [{"role": "user", "content": user}]
    result = AgentResult(text="")

    for _ in range(max_turns):
        response = _client().messages.create(
            model=model,
            max_tokens=16000,
            system=_cached(system),
            messages=messages,
            output_config={"effort": settings.agent_effort},
            **({"tools": tools} if tools else {}),
        )
        _record(model, response.usage)
        if response.stop_reason == "refusal":
            raise LLMRefusal("model refused the request")

        for block in response.content:
            if block.type == "server_tool_use" and block.name == "web_search":
                result.tools_used.append(block.name)
            elif block.type == "web_search_tool_result" and isinstance(block.content, list):
                result.sources += [item.url for item in block.content]
                found = [{"title": item.title, "url": item.url} for item in block.content]
                result.evidence.append({"tool": "web_search", "output": json.dumps(found, ensure_ascii=False)})
            elif block.type == "text":  # the passages a web answer quotes: the only page text the API shows
                for citation in getattr(block, "citations", None) or []:
                    if citation.type == "web_search_result_location":
                        result.evidence.append({"tool": "web_search_citation", "output": f"{citation.cited_text} ({citation.url})"})

        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "pause_turn":
            continue
        if response.stop_reason != "tool_use":
            result.text = "".join(b.text for b in response.content if b.type == "text").strip()
            return result

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result.tools_used.append(block.name)
                tool_result = _run_tool(block, handlers)
                tool_results.append(tool_result)
                result.evidence.append({"tool": block.name, "output": tool_result["content"]})
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"agent did not finish within {max_turns} turns")


def _run_tool(block, handlers: dict[str, Callable[[dict], Any]]) -> dict:
    """Execute one tool call. Errors go back to the model instead of crashing the request."""
    try:
        output = handlers[block.name](block.input)
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": json.dumps(output, ensure_ascii=False, default=str),
        }
    except Exception as exc:
        logger.warning("tool %s failed: %r", block.name, exc)
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": f"Tool error: {type(exc).__name__}",
            "is_error": True,
        }
