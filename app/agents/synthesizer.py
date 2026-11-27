"""Synthesizer - turns what the specialists found into the one reply the merchant reads."""
import logging

from app import llm, memory
from app.state import usable_findings

logger = logging.getLogger("getnet")

SYNTHESIZER_PROMPT = """You write the final reply of Getnet's customer assistant. Specialists have each \
answered part of the merchant's message. Combine their answers into one reply.

- Use only what the specialists' answers say. Add no facts, numbers or advice of your own.
- Keep every specific fact: dates, amounts, serial numbers, error codes, steps.
- Answer the parts in the order the merchant asked them. Do not mention specialists, steps or tools.
- If one answer gives a fact and another says it could not see that fact, keep the fact.
- Reply in the language of the merchant's message, whatever language the specialists' answers are in, in a \
few short sentences or a short list."""


def synthesizer_node(state: dict) -> dict:
    findings = usable_findings(state)
    sources = list(dict.fromkeys(source for finding in findings for source in finding["sources"]))
    if len(findings) == 1:  # nothing to combine: the specialist's answer goes out as written
        return {"response": findings[0]["answer"], "sources": sources, "step": {"detail": "one finding, returned unchanged"}}

    answers = "\n\n".join(
        f"Answer {number} ({finding['agent']}, asked to: {finding['task']}):\n{finding['answer']}"
        for number, finding in enumerate(findings, 1)
    )
    detail = f"combined {len(findings)} findings"
    try:
        text = llm.run_agent(
            system=SYNTHESIZER_PROMPT,
            user=f"Merchant's message: {state['message']}\n\n{answers}\n\n{memory.language_rule(state)}".rstrip(),
            tools=[],
            handlers={},
        ).text
    except Exception:  # the findings are already good answers, send them as they are
        logger.warning("could not combine the findings, sending them one after another")
        text = ""
    if not text:
        text = "\n\n".join(finding["answer"] for finding in findings)
        detail += " (joined without the model)"
    return {"response": text, "sources": sources, "step": {"detail": detail}}
