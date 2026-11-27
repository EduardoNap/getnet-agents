"""Agent 3 Customer Support - resolves questions about the merchant's own account."""
from datetime import date

from app import llm, memory, store
from app.state import make_finding
from app.tools import support_tools

SUPPORT_PROMPT = """You are the customer support specialist of Getnet's assistant, helping one \
merchant with their own account. Today is {today}.

Look at the merchant's data before answering: call the tool that holds the facts instead of \
answering in general terms. The tools already know which merchant you are talking to, and they \
only return that merchant's data. You cannot look up anyone else.

- get_settlement_schedule: payouts already paid or scheduled, with dates, amounts and the settlement terms.
- get_terminal_status: each card machine, whether it is online, its last error.
- get_recent_transactions: latest sales, including declined ones and why.
- escalate_to_human: hands the case to a human agent.
- request_terminal_replacement: asks for one of the merchant's card machines to be replaced. It only \
creates a request that a human agent must approve. Use it when the merchant asks for a replacement, \
then say that the request awaits approval and give the ticket number the tool returns.

Rules:
- State the specific facts you found (dates, amounts, serial numbers, error codes). Give a next step \
only when a tool result states one. Do not add causes, explanations or advice of your own.
- Call escalate_to_human when the merchant asks for a person, or the data shows a problem only a \
human can fix (blocked account, missing payout).
- When the data does not explain what the merchant asks, for example an error code that is not in it, \
say what the data shows and that it does not explain it. Do not hand off for that: the router can ask \
the specialist who reads Getnet's help pages.
- Never invent account data.
- Reply in the language of the merchant's message, in a few short sentences. An English question gets an \
English answer even though the account data has Portuguese names in it."""

_NO_INPUT = {"type": "object", "properties": {}}

SUPPORT_TOOLS = [
    {"name": "get_settlement_schedule", "description": "The merchant's payouts: sale date, net amount, payout date, whether it is paid or scheduled, and the settlement terms.", "input_schema": _NO_INPUT},
    {"name": "get_terminal_status", "description": "The merchant's card machines: model, online or offline, connection type, last error, firmware.", "input_schema": _NO_INPUT},
    {"name": "get_recent_transactions", "description": "The merchant's latest transactions with status and, for declined ones, the decline code and reason.", "input_schema": _NO_INPUT},
    {
        "name": "request_terminal_replacement",
        "description": "Propose replacing one of the merchant's card machines. Creates a request a human agent must approve; nothing is sent before that.",
        "input_schema": {
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Serial number of the merchant's terminal, for example GS-48213."},
                "reason": {"type": "string", "description": "Why it needs replacing, in one sentence."},
            },
            "required": ["terminal_id", "reason"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Hand the conversation to a human support agent. Use when you cannot resolve the issue.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string", "description": "Why a human is needed, in one sentence."}},
            "required": ["reason"],
        },
    },
]


def support_node(state: dict) -> dict:
    user_id = state["user_id"]
    handoff: dict = {}

    def escalate_to_human(tool_input: dict) -> dict:
        handoff["reason"] = tool_input["reason"]
        return {"status": "handoff_requested"}

    def read(tool):
        """Bind an account tool to the authenticated merchant, and record every read in the audit log."""

        def handler(_ignored_model_input: dict) -> dict:
            store.audit(actor=user_id, action=tool.__name__, user_id=user_id, trace_id=state.get("trace_id", ""))
            return tool(user_id)

        return handler

    def request_terminal_replacement(tool_input: dict) -> dict:
        # The merchant and the conversation come from the request. The model supplies only the serial number,
        # and the tool refuses one that is not this merchant's.
        store.audit(actor=user_id, action="request_terminal_replacement", user_id=user_id, trace_id=state.get("trace_id", ""))
        return support_tools.propose_terminal_replacement(
            user_id, str(tool_input.get("terminal_id", "")), str(tool_input.get("reason", "")), state["conversation_id"], state["message"]
        )

    # The user_id comes from the verified token, never from the model
    handlers = {
        "get_settlement_schedule": read(support_tools.get_settlement_schedule),
        "get_terminal_status": read(support_tools.get_terminal_status),
        "get_recent_transactions": read(support_tools.get_recent_transactions),
        "request_terminal_replacement": request_terminal_replacement,
        "escalate_to_human": escalate_to_human,
    }
    result = llm.run_agent(
        system=SUPPORT_PROMPT.format(today=date.today().isoformat()),
        user=memory.request_text(state),
        tools=SUPPORT_TOOLS,
        handlers=handlers,
    )
    finding = make_finding("support", state, result)
    if handoff:  # a request, not a decision: the router reviews it and either escalates or asks another specialist
        finding["handoff"] = handoff["reason"]
    return {"findings": [finding], "step": {"tools": result.tools_used}}
