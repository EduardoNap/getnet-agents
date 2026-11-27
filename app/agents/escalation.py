"""Agent 4 Escalation - opens a ticket, hands the conversation to a human, and resumes when the human answers.

This is the safety net, so the ticket is created in plain code first. The model
only words the messages, and fixed templates take over if the model is down.
"""
import logging

from app import llm, memory, store
from app.tools import support_tools

logger = logging.getLogger("getnet")

ESCALATION_PROMPT = """You are the handoff specialist of Getnet's customer assistant. A support \
ticket has just been opened and a human agent will take over.

Write a short message to the merchant, in the language they used:
- say that a human agent will continue the conversation,
- give the ticket number exactly as provided.

Do not promise a resolution or a response time. Do not add phone numbers, links or other contact \
details. Two or three sentences."""

RESUME_PROMPT = """A human agent of Getnet's support team has answered a merchant's ticket. You are the \
handoff specialist of Getnet's customer assistant: write the message that gives the merchant that answer, \
in the language the merchant used.

- Say that the answer comes from a human agent, and give the ticket number exactly as provided.
- Pass on everything the human agent said. Add no facts, promises, contact details or advice of your own.
- Write in the language of the merchant's original message, whatever language the human agent wrote in.
- Two to four sentences. Output only the message itself, with no note about how you wrote it."""

FALLBACK_TEMPLATE = (
    "I've passed your case to a human agent, who will continue from here. Your ticket number is {ticket_id}. "
    "Encaminhei o seu caso para um atendente humano. O número do seu protocolo é {ticket_id}. "
)
HOLD_TEMPLATE = (
    "A human agent is already handling this conversation (ticket {ticket_id}). I've added your message to it.\n"
    "Um atendente humano já está cuidando desta conversa (protocolo {ticket_id}). Adicionei a sua mensagem."
)
RESUME_TEMPLATE = (
    "Answer from our support team on ticket {ticket_id} / "
    "Resposta da nossa equipe de atendimento no protocolo {ticket_id}:\n{reply}"
)


def escalation_node(state: dict) -> dict:
    reason = state.get("escalation_reason") or "The assistant could not resolve the request."
    ticket = support_tools.create_support_ticket(
        user_id=state["user_id"],
        reason=reason,
        summary=state["message"],
        conversation_id=state["conversation_id"],
    )
    ticket_id = ticket["ticket_id"]

    try:
        result = llm.run_agent(
            system=ESCALATION_PROMPT,
            user=f"Merchant message: {state['message']}\nReason for handoff: {reason}\nTicket number: {ticket_id}\n"
            f"{memory.language_rule(state, 'the message')}".rstrip(),
            tools=[],
            handlers={},
        )
        message = result.text
    except Exception:  # provider down or refusing: the handoff still happens
        logger.warning("could not word the handoff message, using the template")
        message = ""
    if ticket_id not in message:
        message = FALLBACK_TEMPLATE.format(ticket_id=ticket_id)

    return {
        "response": message,
        "handoff": {"ticket_id": ticket_id, "reason": reason, "status": ticket["status"]},
        "step": {"tools": ["create_support_ticket"], "detail": reason},
    }


def hold_node(state: dict) -> dict:
    """A human already has this conversation so no agent answers over them. No model call."""
    ticket = store.get_ticket(state["open_ticket"])
    return {
        "response": HOLD_TEMPLATE.format(ticket_id=ticket["ticket_id"]),
        "handoff": {
            "ticket_id": ticket["ticket_id"],
            "reason": "A human agent is already handling this conversation.",
            "status": ticket["status"],
        },
        "step": {"detail": f"waiting for a human on {ticket['ticket_id']}"},
    }


def write_resume_message(ticket: dict, reply: str) -> str:
    """The agent resumes the conversation by wording the human's answer for the merchant. The answer itself is never lost."""
    ticket_id = ticket["ticket_id"]
    try:
        message = llm.run_agent(
            system=RESUME_PROMPT,
            user=f"Merchant's original message: {ticket['summary']}\nTicket number: {ticket_id}\nHuman agent's answer: {reply}",
            tools=[],
            handlers={},
        ).text
    except Exception:
        logger.warning("could not word the human's answer, sending it as written")
        message = ""
    if ticket_id not in message:
        message = RESUME_TEMPLATE.format(ticket_id=ticket_id, reply=reply)
    return message
