"""Offline test doubles: the LLM layer is replaced, everything else is real."""
import os
import tempfile

# The database and the demo keys go to a throwaway folder. Set before the app is imported.
os.environ["STATE_DIR"] = tempfile.mkdtemp(prefix="getnet-tests-")
for name in ("DATABASE_PATH", "AUTH_JWKS_FILE", "AUTH_JWKS_URL", "OTEL_EXPORTER_OTLP_ENDPOINT"):
    os.environ.pop(name, None)

import pytest  # noqa: E402

from app import devtokens, llm, memory, ratelimit, store  # noqa: E402
from app.agents import escalation, knowledge, router, support, synthesizer, verifier  # noqa: E402

# Which agent a run_agent call belongs to is recognised by its system prompt.
PROMPTS = {
    "knowledge": knowledge.KNOWLEDGE_PROMPT,
    "support": support.SUPPORT_PROMPT,
    "escalation": escalation.ESCALATION_PROMPT,
    "resume": escalation.RESUME_PROMPT,
    "synthesizer": synthesizer.SYNTHESIZER_PROMPT,
    "summary": memory.SUMMARY_PROMPT,
}


def who(system: str) -> str:
    return next(name for name, prompt in PROMPTS.items() if system.startswith(prompt.split("{today}")[0]))


# The person who signs in for each merchant in data/users.json. joao.silva may act for two merchants.
PEOPLE = {"cliente1988": "joao.silva", "mercado_lima": "joao.silva", "maria_2020": "maria.santos", "bistro_nonna": "carla.rossi"}


def auth_header(who: str = "cliente1988", role: str = "merchant", scopes: list[str] | None = None) -> dict:
    """A request header with a valid demo token: for a person who may act for this merchant, or for this operator."""
    subject = PEOPLE.get(who, who) if role == "merchant" else who
    return {"Authorization": f"Bearer {devtokens.issue_token(subject, role, scopes=scopes)}"}


class ProcessKilled(BaseException):
    """The process stopped in the middle of a turn. Not an Exception, so no agent's error handling catches it."""


class FakeLLM:
    """Scripted for app.llm. Tests set what the 'model' decides."""

    def __init__(self):
        self.route = "knowledge"  # the router's first action when no script is given
        self.confidence = "high"
        # The router's actions in order: a name, or a dict of Decision fields. After the script: "finish".
        self.script: list = []
        self.tools_to_call: list[tuple[str, dict]] = []  # (tool name, input) a specialist will call
        self.answers: list[str] = []  # specialists' answers in order; default "answer using [tools]"
        self.replies: dict[str, str] = {}  # text of the other agents, by name
        self.fail: set[str] = set()  # agents whose model call raises: "router", "knowledge", "summary", ...
        self.fail_agent = False  # shorthand: both specialists raise, as if the provider were down
        self.kill: set[str] = set()  # agents during whose model call the process dies (see ProcessKilled)
        self.tokens: tuple[int, int] | None = None  # (input, output) reported by every call
        self.seen_messages: list[str] = []  # every input any model call received
        self.router_inputs: list[str] = []
        self.verification = {"supported": True, "unsupported": [], "revised": ""}  # what the verifier returns
        self.verifier_inputs: list[str] = []
        self.agent_calls: list[str] = []  # which agent each run_agent call was
        self.tool_outputs: list = []
        self._call_in_turn = 0

    def continue_with(self, script: list) -> None:
        """What the router decides from here on, for a turn that is picked up again part-way."""
        self.script, self._call_in_turn = script, 0

    def _meter(self):
        if self.tokens:
            llm.record_usage("claude-opus-5-5", *self.tokens)

    def classify(self, system, user, schema, model=None, effort="low"):
        if schema is verifier.Verification:
            self.verifier_inputs.append(user)
            if "verifier" in self.fail:
                raise ConnectionError("provider down")
            self._meter()
            return verifier.Verification(**self.verification)
        assert schema is router.Decision
        self.seen_messages.append(user)
        self.router_inputs.append(user)
        if "router" in self.fail:
            raise ConnectionError("provider down")
        self._meter()
        if "No steps taken yet." in user:  # a new message: the script starts again
            self._call_in_turn = 0
        script = self.script or [self.route]
        entry = script[self._call_in_turn] if self._call_in_turn < len(script) else "finish"
        self._call_in_turn += 1
        fields = {"action": entry} if isinstance(entry, str) else entry
        defaults = {"task": "", "plan": [], "review": "", "grounded": True, "confidence": self.confidence, "reason": "scripted"}
        return router.Decision(**{**defaults, **fields})

    def run_agent(self, system, user, tools, handlers, max_turns=6):
        agent = who(system)
        self.agent_calls.append(agent)
        self.seen_messages.append(user)
        if agent in self.kill:
            raise ProcessKilled(agent)
        if agent in self.fail or (self.fail_agent and agent in ("knowledge", "support")):
            raise ConnectionError("provider down")
        self._meter()
        if agent not in ("knowledge", "support"):
            return llm.AgentResult(text=self.replies.get(agent, f"{agent} text"))
        used, evidence = [], []
        for name, tool_input in self.tools_to_call:
            if name in handlers:
                output = handlers[name](tool_input)
                self.tool_outputs.append(output)
                used.append(name)
                evidence.append({"tool": name, "output": str(output)})
        answer = self.answers.pop(0) if self.answers else f"answer using {used}"
        return llm.AgentResult(text=answer, tools_used=used, evidence=evidence)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "classify", fake.classify)
    monkeypatch.setattr(llm, "run_agent", fake.run_agent)
    return fake


@pytest.fixture(autouse=True)
def clean_state():
    store.reset()
    ratelimit.reset()
