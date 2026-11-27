"""The judge: a second model that grades an answer against a reference and the evidence."""
from datetime import date

from pydantic import BaseModel

from app import llm
from app.config import settings

JUDGE_PROMPT = """You grade one answer from a customer support assistant for Getnet merchants. Be strict and literal.

You receive the merchant's message, a reference answer written by a person who knows the correct \
facts, the evidence the assistant's tools returned, and the assistant's answer.

- correct: the answer agrees with the reference on every fact they both state. Extra detail is \
fine when it does not contradict the reference. When the reference says the assistant should say \
it does not know, an answer that says so is correct and an answer that states a specific value is not.
- grounded: every specific fact in the answer (amounts, dates, codes, steps, names, phone numbers) \
appears in the evidence. Politeness, and advice to contact support, need no evidence. The assistant \
is configured with Getnet's support line, 4002-4000, so that number needs no evidence either. Web search \
evidence shows page titles, links and the passages the answer quotes ([web_search_citation]): each \
specific figure in such an answer must appear in those passages or titles. [conversation] is the \
earlier part of the conversation, a human agent's reply included, and counts as evidence.
- complete: the answer covers every part of the merchant's message that the reference covers.
- useful: the answer deals with what the merchant asked and, when the evidence gives a next step, \
tells the merchant what to do, in the language the merchant wrote in. An answer that only says it \
cannot help is useful only when the reference says the assistant should not know. An answer in a \
different language from the merchant's message is not useful.

The reference speaks of "today", "yesterday" and "tomorrow"; the answer may give the dates \
themselves. Language is graded only under `useful`.
Give the reason in one or two sentences, naming the fact that failed, if any."""


class Verdict(BaseModel):
    correct: bool
    grounded: bool
    complete: bool
    useful: bool
    reason: str


def require_independent(judge_model: str, other_models: list[str]) -> None:
    """A model does not grade answers it wrote or checked."""
    if judge_model in other_models:
        raise SystemExit(f"The judge ({judge_model}) is also a model that writes or checks answers. Set JUDGE_MODEL to another one.")


def grade(message: str, reference: str, answer: str, evidence: list[dict]) -> Verdict:
    shown = "\n".join(f"[{item['tool']}] {item['output']}" for item in evidence) or "(the tools returned nothing)"
    return llm.classify(
        JUDGE_PROMPT,
        f"Today is {date.today().isoformat()}.\n\nMerchant's message:\n{message}\n\nReference answer:\n{reference}\n\n"
        f"Evidence from the assistant's tools:\n{shown}\n\nAssistant's answer:\n{answer}",
        Verdict,
        model=settings.judge_model,  # not the model that wrote the answer
        effort="medium",
    )
