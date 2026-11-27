"""Verifier - the last check before the merchant reads the answer.

The specialists are told to answer only from their tools, and the router reviews each step.
The evaluation still found answers carrying advice no tool had given. A rule in a prompt lowers
how often that happens; only a check after the answer is written puts a bound on it.
"""
import logging
from datetime import date

from pydantic import BaseModel

from app import llm, memory
from app.config import settings
from app.state import usable_findings

logger = logging.getLogger("getnet")

VERIFIER_PROMPT = """You check the final reply of Getnet's customer assistant before the merchant sees it. Today is {today}.

You receive the merchant's message, the output of the tools the assistant used, and the reply. Find \
every statement in the reply that the tool output does not support, and return the reply without them.

- Supported: the tool output states it, or it follows from the tool output by simple arithmetic, or \
by writing a date as "today", "yesterday" or "tomorrow". A statement translated from Portuguese or \
worded differently from the tool output is still supported.
- Not supported: a cause, explanation, piece of advice, next step, limit, fee or condition that the \
tool output does not state, however reasonable it sounds.
- Always allowed: greetings and politeness, saying that something could not be found, suggesting \
Getnet's support line (4002-4000), and offering more help.
- [conversation] is the earlier part of this conversation, a human agent's answers included. It \
counts as tool output.
- `unsupported`: each unsupported statement, quoted from the reply. Empty when there is none.
- `revised`: the reply with those statements removed and nothing added, keeping the wording and \
formatting of the rest. Leave it empty when `supported` is true.
- A reply written in a different language from the one named at the end is not `supported`, even when \
every fact is: `revised` is then the same reply in the named language."""

EVIDENCE_CHARS = 40_000


class Verification(BaseModel):
    supported: bool
    unsupported: list[str]
    revised: str


def verifier_node(state: dict) -> dict:
    evidence = [item for finding in usable_findings(state) for item in finding["evidence"]]
    if not evidence:  # answered without a tool
        return {"step": {"status": "skipped", "detail": "no tool output to check against"}}
    if state.get("history"):
        evidence.insert(0, {"tool": "conversation", "output": state["history"]})
    shown = "\n".join(f"[{item['tool']}] {item['output']}" for item in evidence)[:EVIDENCE_CHARS]
    try:
        check: Verification = llm.classify(
            VERIFIER_PROMPT.format(today=date.today().isoformat()),
            f"Merchant's message:\n{state['message']}\n\nTool output:\n{shown}\n\nReply:\n{state['response']}"
            f"\n\n{memory.language_rule(state, 'the reply')}".rstrip(),
            Verification,
            model=settings.verifier_model,
            effort="medium",
        )
    except Exception:  # the reply was already reviewed step by step, send it rather than fail the request
        logger.warning("the verifier could not run, sending the reply as written")
        return {"step": {"status": "skipped", "detail": "the check could not run"}}

    if check.supported:
        return {"step": {"detail": "every statement is backed by the tool output"}}
    if not check.revised.strip():
        return {"step": {"status": "skipped", "detail": "the check returned no reply"}}
    return {
        "response": check.revised.strip(),
        "step": {
            "status": "revised",
            "detail": f"removed {len(check.unsupported)} unsupported statement(s)" if check.unsupported else "rewritten in the merchant's language",
            "removed": check.unsupported,
        },
    }
