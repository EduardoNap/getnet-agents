
# Version 2 — implementation plan

**Goal:** implement every requirement in `04-v2-design.md` (R12 to R22, N6 to N12).

**Architecture:** the LangGraph flow stays the single place where the whole path is visible. The
Router now runs before and after every specialist, a synthesizer writes the final answer, and
three small modules (identity, store, memory) sit outside the graph.

**Tech stack:** Python 3.12, FastAPI, LangGraph, Anthropic SDK, SQLite (standard library),
PyJWT with `cryptography`, OpenTelemetry SDK (already installed through Chroma), pytest.

**Spec:** `specs/04-v2-design.md`

## Global constraints

- Still one container: no new service in `docker-compose.yml`.
- New dependencies are limited to `pyjwt[crypto]`. Everything else is standard library or already pinned.
- No support tool accepts a `user_id` argument (R6, unchanged).
- Offline tests need no API key and no network (N3, unchanged).
- Limits enforced in code, not in prompts: 3 specialist runs per message, the same specialist at most twice.
- History window: last 6 messages. A summary is written when more than 12 messages are outside it.
- Each task is test-first: write the tests named below, see them fail, then implement.

## Review focus

Inputs the design implies and a person is likely to send. Each has a test in the task that owns the code.

1. A token that is expired, signed with another key, or has no signature: `401`, never a default identity. (Task 2)
2. A `conversation_id` that does not exist or belongs to another merchant: `404` in both cases, same body. (Task 4)
3. A merchant keeps writing while a ticket is open: no second ticket, the messages reach the operator. (Task 6)
4. An operator sends the same reply twice: one resolution, one merchant-facing message. (Task 6)
5. A router that never says `finish`: the loop stops at 3 specialist runs. (Task 5)
6. Long digit strings that are not card numbers (order ids, phone numbers) are left alone. (Task 7)

---

## Task 1 — Store
Covers: R14, R18, R20 (storage only)

- Files: create `app/store.py`, `tests/test_store.py`; modify `app/config.py`, `tests/conftest.py`, `.gitignore`
- Produces:
  - `settings.database_path` (env `DATABASE_PATH`, default `data/state/app.db`)
  - `store.init()`, `store.reset()`
  - `create_conversation(user_id) -> str`
  - `get_conversation(conversation_id, user_id) -> dict` — raises `store.NotFound` when it does not exist **or** belongs to someone else
  - `add_message(conversation_id, role, text, trace_id="")`, `get_messages(conversation_id) -> list[dict]`; roles: `user`, `assistant`, `human_agent`
  - `set_summary(conversation_id, summary, upto_message_id)`
  - `open_ticket(conversation_id, user_id, reason, summary) -> dict` — returns the conversation's unresolved ticket when there is one
  - `unresolved_ticket(conversation_id) -> dict | None`, `get_ticket(ticket_id) -> dict`, `list_tickets(status=None) -> list[dict]`
  - `claim_ticket(ticket_id, operator) -> dict` — raises `store.Conflict` when another operator holds it
  - `resolve_ticket(ticket_id, operator, reply, merchant_message) -> tuple[dict, bool]` — the bool says whether this call changed anything
  - `audit(actor, action, user_id, trace_id)`, `audit_entries(user_id=None) -> list[dict]`
- Ticket states: `open → claimed → resolved`. Transitions are conditional `UPDATE`s.
- `conftest.py` points `DATABASE_PATH` and the key files at a temporary folder before the app is imported, and resets the store before each test.
- Tests first:
  - a conversation is readable by its owner and raises `NotFound` for another user and for an unknown id
  - messages come back oldest first; data is still there after the connection is reopened
  - `open_ticket` twice on one conversation returns the same ticket id; on two conversations, different ids starting with `TCK-`
  - claim by A then A again: same ticket, no error; claim by B: `Conflict`
  - resolve twice: the second call returns `changed == False` and stores one `human_agent` and one `assistant` message
  - resolve without a claim, or by another operator: `Conflict`

## Task 2 — Identity
Covers: R12, R13 · review focus 1

- Files: create `app/auth.py`, `app/devtokens.py`, `tests/test_auth.py`; modify `app/main.py`, `app/config.py`, `requirements.txt`, `tests/conftest.py`, `tests/test_graph.py`
- Produces:
  - `Principal(subject: str, role: str)`, roles `merchant` and `operator`
  - `auth.verify_token(token) -> Principal` — raises `auth.AuthError`; RS256 only; requires `exp`, `sub`, `iss == settings.auth_issuer`, `aud == settings.auth_audience`
  - FastAPI dependencies `require_principal` (401), `require_merchant` (403 unless role is `merchant` and the merchant exists and is active), `require_operator` (403)
  - `devtokens.issue_token(subject, role="merchant", ttl_minutes=60) -> str` and `python -m app.devtokens <subject> [--role operator]`. Creates the key pair on first use. This module stands in for the identity provider; the service imports nothing from it.
  - `POST /chat` returns `403` when `request.user_id != principal.subject`
  - test helper `auth_header(subject, role="merchant")` in `conftest.py`
- Tests first:
  - no header, a malformed token, an expired token, a token signed with a different key, an unsigned (`alg: none`) token, a wrong audience: all `401`
  - token for `cliente1988` with body `user_id: "maria_2020"`: `403`, and the model is never called
  - token for a merchant that is not in the data, and for an inactive merchant: `403`
  - an operator token on `/chat`: `403`
  - a valid merchant token: `200`, and the tools read the token's merchant

## Task 3 — Usage, cost and JSON logs
Covers: N9, N10

- Files: modify `app/llm.py`, `app/tracing.py`, `app/schemas.py`, `app/graph.py`, `app/main.py`, `app/config.py`; create `tests/test_tracing.py`
- Produces:
  - `llm.Usage(input_tokens, output_tokens, calls, cost_usd)` and `llm.meter()` — a context manager; every model call made inside it adds to the meter
  - `AgentResult.evidence: list[dict]` — `{"tool", "output"}` for each tool result
  - each step in `agent_workflow` carries `input_tokens`, `output_tokens`, `cost_usd`
  - `ChatResponse.usage = {"input_tokens", "output_tokens", "llm_calls", "estimated_cost_usd"}`
  - `tracing.log_event(event, **fields)` — one JSON object per line
  - `tracing.span(name, **attributes)` — a no-op unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set
  - price table in `config.py`, per model, in USD per million tokens
- Tests first:
  - a step's log line parses as JSON and has `trace_id`, `agent`, `status`, `latency_ms`
  - usage recorded inside a traced step appears in the step and is summed in the response
  - with a test span exporter installed, one request produces one span per step

## Task 4 — Conversation memory
Covers: R18, R19 · review focus 2

- Files: create `app/memory.py`, `tests/test_memory.py`; modify `app/state.py`, `app/graph.py`, `app/schemas.py`, `app/main.py`, `app/agents/knowledge.py`, `app/agents/support.py`
- Produces:
  - `ChatRequest.conversation_id: str | None`, `ChatResponse.conversation_id: str`
  - `graph.run_turn(message, user_id, conversation_id=None) -> dict` (the final state) and `run_chat(...)` built on it
  - `memory.load(conversation) -> str` — the summary plus every message after it (6 to 12); `""` for a new conversation. It takes the row returned by `store.get_conversation`, so memory can only be read through the ownership check.
  - `memory.remember(conversation, user_text, assistant_text, trace_id)`
  - `memory.request_text(state) -> str` — what a specialist receives: context, the merchant's message, its task
  - `GET /conversations/{id}` for the owner
- Blocked turns are not stored, so an injection attempt cannot come back through the history.
- Tests first:
  - second turn with the same `conversation_id`: the model receives the first turn's text
  - no `conversation_id`: a new one is returned, and the two conversations do not share history
  - unknown id and another merchant's id: both `404` with the same body
  - after `store` is re-initialised from the same file, the history is still loaded (restart)
  - with 14 stored messages, a summary is written and the prompt holds the summary plus the last 6 messages
  - a summary call that raises leaves the turn successful
  - a blocked message is absent from the stored conversation

## Task 5 — Router loop and synthesizer
Covers: R15, R16, R17 · review focus 5

- Files: modify `app/agents/router.py`, `app/graph.py`, `app/state.py`, `app/tracing.py`, `app/agents/knowledge.py`, `app/agents/support.py`, `tests/conftest.py`, `tests/test_graph.py`; create `app/agents/synthesizer.py`
- Produces:
  - `router.Decision(action, task, plan, review, grounded, confidence, reason)`; `action ∈ knowledge | support | escalation | finish | blocked`
  - state fields `task`, `plan`, `findings`, `rejected`
  - a finding: `{agent, task, status: ok | failed, answer, tools, sources, evidence}`
  - `traced(agent, node, on_error=None)` — a specialist that raises becomes a failed finding and control returns to the router; any other node that raises still hands off
  - `synthesizer_node(state)` — one usable finding is returned unchanged; several are combined in one call; if that call fails the answers are joined
  - `FakeLLM.script: list` — the router's actions in order
- Rules in `router_node`, in code:
  - first call: `blocked` ends the request; `escalation` or low confidence hands off
  - `knowledge` or `support` is refused once 3 runs are used or that specialist already ran twice
  - `grounded == False` adds the last finding to `rejected`
  - `finish` with no usable finding hands off
- Tests first:
  - one specialist: `guardrail, router, support, router, synthesizer`; the specialist's answer is returned unchanged
  - a plan with two specialists: `router, support, router, knowledge, router, synthesizer`; the response is the combined text; sources are merged
  - a specialist raises: the router is called again and can choose the other specialist; the response is valid and has no handoff
  - the review says not grounded: the same specialist runs once more; the rejected finding is not in the final answer
  - a script that never finishes: exactly 3 specialist runs, then an answer
  - every run failed: handoff with a ticket
  - the router itself raises: handoff with a ticket (N5)
  - support calls `escalate_to_human`: handoff without another router call

## Task 6 — Handoff with operators
Covers: R20, R21 · review focus 3, 4

- Files: modify `app/agents/escalation.py`, `app/tools/support_tools.py`, `app/graph.py`, `app/main.py`, `app/schemas.py`, `tests/test_tools.py`; create `tests/test_handoff.py`
- Produces:
  - `create_support_ticket(user_id, reason, summary, conversation_id) -> dict` backed by the store
  - `hold_node(state)` — runs instead of the agents while the conversation has an unresolved ticket
  - `escalation.write_resume_message(ticket, reply) -> str` — the agent words the human's answer for the merchant; falls back to the reply itself
  - `graph.resume_after_human(ticket_id, operator, reply) -> dict`
  - endpoints `GET /tickets`, `GET /tickets/{id}`, `POST /tickets/{id}/claim`, `POST /tickets/{id}/reply`
  - `handoff` in the response gains `status`
- Tests first:
  - asking for a human twice in one conversation: one ticket
  - a message while the ticket is open: workflow is `guardrail, hold`, the model is not called, the operator sees the message in `GET /tickets/{id}`
  - operator flow: list shows the ticket, claim, reply; the conversation then contains the human's reply and the merchant-facing message; the next merchant turn runs the agents again and they receive the human's reply
  - reply sent twice: `200` both times, one resolution, one merchant-facing message, the model called once
  - claim by a second operator: `409`; reply before claim: `409`
  - a merchant token on any ticket endpoint: `403`; unknown ticket: `404`
  - the resume model call fails: the reply is still delivered

## Task 7 — Card masking, audit log, rate limit
Covers: R14, R22, N12 · review focus 6

- Files: modify `app/guardrails.py`, `app/agents/router.py`, `app/agents/support.py`, `app/main.py`, `tests/test_tools.py`; create `app/ratelimit.py`, `tests/test_ratelimit.py`
- Produces:
  - `guardrails.mask_card_numbers(text) -> str` — 13 to 19 digits, optional spaces or dashes, Luhn valid, replaced by `[card number removed]`
  - the guardrail node replaces `state["message"]` with the masked text
  - every support tool call writes `store.audit(actor, tool name, merchant, trace_id)`; operators reading a ticket are audited too
  - `ratelimit.check(key)` raises `ratelimit.RateLimited`; `429` from the API; `settings.rate_limit_per_minute` (env, default 30)
- Tests first:
  - `4111 1111 1111 1111` and `4111-1111-1111-1111` are masked; the stored message and the model input do not contain the number
  - a 16-digit string that fails Luhn, a phone number and a transaction id are unchanged
  - one support tool call produces one audit entry with the trace id of the response
  - request 31 inside a minute returns `429`; another principal is unaffected

## Task 8 — Retrieval evaluation
Covers: N6

- Files: create `evals/__init__.py`, `evals/metrics.py`, `evals/retrieval_set.jsonl`, `evals/retrieval.py`, `tests/test_metrics.py`; modify `app/rag/retriever.py`
- Produces:
  - `search(query, k=6, keyword_weight=KEYWORD_WEIGHT)` — `0` gives vector-only
  - `metrics.recall_at_k`, `metrics.reciprocal_rank`, `metrics.ndcg_at_k`, `metrics.context_precision`
  - `python -m evals.retrieval [--min-recall X]` writes `evals/reports/retrieval.json` and `.md`; exits 1 below the threshold
  - the set: one line per question with `question`, `lang` (`en` or `pt`), `kind` (`plain` or `hard`: typos, no product name, paraphrase) and `gold` (page URLs). Not the brief's examples.
- Tests first: each metric on hand-computed rankings (gold first, gold third, gold absent, two gold pages).

## Task 9 — Answer and guardrail evaluation
Covers: N7, N8

- Files: create `evals/cases.jsonl`, `evals/run.py`, `evals/judge.py`, `evals/attacks.jsonl`, `evals/guardrails.py`, `evals/human_labels.jsonl`, `evals/agreement.py`, `tests/test_evals.py`
- Produces:
  - a case: `id`, `kind` (`knowledge`, `support`, `general`, `multi`, `followup`, `handoff`, `blocked`), `user`, `turns`, `expect_agents`, `expect_tools`, `must_include`, `must_not_include`, `reference`
  - `python -m evals.run [--repeats 3] [--only kind]` — calls `graph.run_turn` in process and writes `evals/reports/answers.json` (every response, workflow, evidence, check and verdict) and `answers.md`
  - `judge.grade(case, answer, evidence) -> Verdict(correct, grounded, complete, reason)`; model from `JUDGE_MODEL`, different from the answering model
  - `python -m evals.guardrails` — block rate on attacks and false-block rate on normal messages, for the phrase layer (offline) and the router layer (model)
  - `python -m evals.agreement` — judge against the human labels
- Tests first (offline): the code checks on a hand-made response; the report writer; the phrase-layer rates on a tiny fixture set.
- A case's `split` is `dev` when its failures were read while building, otherwise `held-out`. `evals.run` reports the held-out cases by default.
- The real-model runs cost API credit and are run once, on request. Their raw output is committed.

## Task 10 — Docker, CI, demo and README
Covers: N11, definition of done

- Files: modify `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `scripts/demo.sh`, `scripts/scenarios.jsonl`, `README.md`; create `.github/workflows/ci.yml`
- A named volume holds the database and the demo keys. `docker compose run --rm api pytest` runs the tests with no local setup.
- CI: offline tests, `python -m evals.retrieval --min-recall <measured value minus a margin>`, Docker build.
- `demo.sh` gets a token from the container and adds a two-specialist scenario and a follow-up turn.

## Found while building

The first live run of four two-specialist cases showed three faults, each now covered by a test in `tests/test_graph.py`:

- specialists answered parts of the message outside their task, so the task is now the only thing they are asked to answer;
- the router reviewed against truncated tool output and rejected good answers, so it now sees all the output of the step under review and only the answers of earlier steps;
- the Knowledge agent searched without limit, so the handler stops at 3 searches per run.
- README: new quick start with tokens, the updated architecture, and a table mapping each review finding to the code and the evidence.
