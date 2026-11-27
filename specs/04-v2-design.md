
## Intent

Close the gaps the review found, without losing what it praised: tools bound to the caller in
code, a small readable graph, graceful degradation, offline tests.

| Review finding | Requirement |
|----------------|-------------|
| The caller chooses `user_id`; no authenticated identity | R12, R13, R14 |
| One specialist per message, no replanning | R15, R16, R17 |
| Single-turn, nothing persists | R18, R19 |
| Handoff ends when the ticket is created | R20, R21 |
| No semantic evaluation; retrieval measured on 12 questions | N6, N7, N8 |
| Guardrail is a phrase list with no benchmark | R22, N8 |
| No token usage, cost or structured logs | N9, N10 |
| No CI; the end-to-end run is reported, not reproducible | N11, N12 |

## Goals, non-goals, anti-goals

- **Goal:** every row above is implemented, tested offline, and shown with evidence in the repo.
- **Goal:** still one container and one `docker compose up --build`.
- **Non-goal:** real infrastructure (Postgres, Redis, a secrets manager, several replicas). The
  design says where each would plug in.
- **Non-goal:** a login service. Tokens are verified here and issued elsewhere.
- **Anti-goal:** capability that nobody can read. Each capability is one small file, and the
  graph stays the place where the whole flow is visible.

## New requirements

| ID | Requirement |
|----|-------------|
| R12 | Every request carries a signed token. The service verifies signature, expiry, issuer and audience, and builds a **Principal** (`subject`, `role`) from it. No token or a bad token: `401`. |
| R13 | The merchant the tools read is the token's subject. `user_id` stays in the body (the brief requires it) but must equal the subject, and the merchant must exist and be active. Otherwise `403`. |
| R14 | Every read of account data is written to an audit log: who, which tool, which merchant, which trace. |
| R15 | The Router Agent plans: it may send a message to more than one specialist, in sequence. |
| R16 | After each specialist the Router reviews the result (is it backed by the tool output, what is still missing) and then finishes, calls another specialist, retries once, or hands off. |
| R17 | The loop is bounded in code: at most 3 specialist runs per message. A final step combines the findings into one answer. |
| R18 | A message may carry a `conversation_id`. Turns are stored and survive a restart. A conversation belongs to one merchant; anyone else gets `404`. |
| R19 | Agents see the recent turns plus a running summary of older ones, never the full history. |
| R20 | Tickets are stored. Operators (role `operator`) can list the queue, claim a ticket and reply to it. |
| R21 | An operator reply resumes the conversation: the agent writes the merchant-facing message from the human's answer, and later turns see it. Claim and reply are idempotent. A conversation has at most one unresolved ticket. |
| R22 | Card numbers in a message are masked before the message is stored, logged or sent to a model. |

| ID | Requirement |
|----|-------------|
| N6 | A held-out retrieval set with a labelled correct page per question reports Recall@1/3/6, MRR, nDCG@6 and context precision, by language, for vector-only and hybrid search. Runs with no API key. |
| N7 | A held-out answer set is run against the real system. Code checks route, tools and required facts; a judge model (not the answering model) scores correctness, groundedness and completeness. Each case runs 3 times. Raw results are committed. |
| N8 | An adversarial set reports the block rate and the false-block rate of the guardrail layers. |
| N9 | Each step and each response reports tokens in, tokens out and an estimated cost. |
| N10 | Logs are one JSON object per line. Spans are exported with OpenTelemetry when an endpoint is configured. |
| N11 | CI runs the offline tests, the retrieval evaluation (with a pass threshold) and the Docker build. |
| N12 | Requests are rate limited per principal. |

## Approaches considered

| Decision | Options | Chosen, and why |
|----------|---------|-----------------|
| Caller identity | Per-merchant API keys; JWT signed with a shared secret; JWT signed with a key pair | **JWT with a key pair (RS256).** The service holds only the public key, which is how a real login service is consumed. One token format carries merchants and operators. API keys would need a key table, and a second one for roles. |
| Persistence | LangGraph checkpointer; plain SQLite tables | **Plain SQLite (standard library).** Three readable tables. The checkpointer stores opaque state, still needs a ticket table for the operator queue, and makes per-turn state harder to reset. Swapping SQLite for Postgres is the path to several replicas. |
| Adaptive orchestration | Separate planner, critic and supervisor agents; one Router that plans and reviews | **One Router, called again after every specialist.** One prompt and one schema cover plan, review and replan, so the loop costs one short call per step and reads as one node in the graph. |
| Evaluation judge | Same model as the answers; a different model | **A different model**, so the system does not grade itself. A different vendor would be stronger and needs a second API key. |

## Architecture

```
START → guardrail → router ⇄ knowledge | support → synthesizer → END
                      │  └──────────→ escalation → END
                      └→ END (blocked)      guardrail → hold → END (ticket already open)
```

The router runs once to plan and once after every specialist to review. Limits are enforced in
`graph.py`, not in a prompt.

## Shared state (additions)

```python
class ChatState(TypedDict, total=False):
    ...                      # v1 fields
    conversation_id: str
    history: str             # summary + recent turns, formatted for prompts
    open_ticket: str         # ticket id when a human already has this conversation
    task: str                # what the current specialist was asked to do
    plan: list[str]          # the router's remaining steps
    findings: Annotated[list[dict], operator.add]   # one per specialist run
```

A finding is `{agent, task, status, answer, tools, sources, evidence}`. `evidence` is the raw
tool output, kept for the router's review and for the evaluation judge. It never leaves the service.

## Components

### Identity — `app/auth.py` (R12, R13)
`Principal(subject, role)`. `require_principal` is a FastAPI dependency: reads the bearer token,
verifies it with the public key (`AUTH_PUBLIC_KEY_FILE`), checks `exp`, `iss`, `aud`.
`require_merchant` adds authorization: role is `merchant`, the merchant exists and is active.
`require_operator` checks the role. `scripts/issue_token.py` signs demo tokens; the container
creates a throwaway key pair on first start. In production the public key comes from the
identity provider and this service never sees a private key.

### Store — `app/store.py` (R14, R18, R20)
SQLite file at `DATABASE_PATH` (a Docker volume). Tables: `conversations`, `messages`,
`tickets`, `audit_log`. Every function takes and returns plain values. Claim and reply are
conditional `UPDATE`s, so a repeated call changes nothing.

### Memory — `app/memory.py` (R19)
`load(conversation)` returns the summary and every message after it as prompt text.
`remember(...)` appends the turn. When more than 12 messages are outside the summary, one model
call folds all but the last 6 into it. A failed summary is skipped, never an error.

### Router Agent — `app/agents/router.py` (R15, R16, R17)
One structured-output call. Input: the message, the conversation context, the findings so far.
Output: `{action, task, plan, review, grounded, confidence, reason}` with
`action ∈ knowledge | support | escalation | finish | blocked`.

Rules in code (`graph.py`):
- first call: `blocked` ends the request; low confidence goes to a human, as in v1;
- a specialist that raises becomes a failed finding and control returns to the router, which can
  try another path;
- at most 3 specialist runs; the same specialist can be retried once when the review says the
  answer is not backed by its evidence;
- when the limit is reached, finish with what is grounded, or hand off if nothing is.

### Synthesizer — `app/agents/synthesizer.py` (R17)
One finding: its answer is returned unchanged, no model call. Several: one call that writes a
single answer from the findings only.

### Specialists — `knowledge.py`, `support.py`
Unchanged in shape. They now answer `state["task"]`, see the conversation context, and return
their tool outputs as evidence. Support tools write to the audit log.

### Escalation and operators — `escalation.py`, `app/main.py` (R20, R21)
The ticket is created in the store before any model call, as in v1. If the conversation already
has an unresolved ticket, that ticket is reused. While a ticket is unresolved the `hold` node
answers with the ticket number and adds the message to the conversation; no agent runs.

| Endpoint | Role | Behaviour |
|----------|------|-----------|
| `GET /tickets?status=open` | operator | the queue |
| `GET /tickets/{id}` | operator | the ticket and its conversation |
| `POST /tickets/{id}/claim` | operator | `open → claimed`; repeat by the same operator is a no-op; another operator gets `409` |
| `POST /tickets/{id}/reply` | operator | `claimed → resolved`; stores the human's reply, resumes the agent to write the merchant-facing message, reopens the conversation; a repeat returns the stored result |
| `GET /conversations/{id}` | merchant (owner) | the transcript and ticket state |

### Guardrail — `app/guardrails.py` (R22)
Adds `mask_card_numbers(text)`: 13 to 19 digit runs that pass the Luhn check become
`[card number removed]`. The guardrail node replaces the message with the masked one.

### Usage and logs — `app/llm.py`, `app/tracing.py` (N9, N10)
`llm.py` adds the usage of every model call to a per-step meter. `traced()` reads it into the
step. The response gains `usage` and `conversation_id`. Log lines are JSON. When
`OTEL_EXPORTER_OTLP_ENDPOINT` is set, each step is also a span.

### Rate limit — `app/ratelimit.py` (N12)
Sliding window per principal, in memory, `429` when exceeded. Per process: several replicas need
a shared store.

## Evaluation — `evals/` (N6, N7, N8)

| File | What |
|------|------|
| `retrieval_set.jsonl`, `retrieval.py` | N6. No API key. Used as a CI gate. |
| `cases.jsonl`, `run.py`, `judge.py` | N7. Real model. Writes `reports/answers.json` (every response, trace and score) and a summary. |
| `attacks.jsonl`, `guardrails.py` | N8. The phrase layer runs offline; the router layer needs the model. |
| `human_labels.jsonl`, `agreement.py` | Human labels for a sample of answers, and the judge's agreement with them. |

Held-out means: the questions are not the brief's examples, and prompts are not edited against
this set. The brief's 12 scenarios stay as the development set.

## API changes

`POST /chat` — header `Authorization: Bearer <token>`; body adds optional `conversation_id`;
response adds `conversation_id` and `usage`. Everything from v1 is still there.

## Testing

| Layer | New coverage |
|-------|--------------|
| Unit | token verification, store transitions, card masking, rate limit, retrieval metrics |
| Integration (fake model) | 401 and 403 paths, conversation ownership, follow-up turn, restart, two-specialist plan, replan after a failure, retry after an ungrounded answer, step limit, ticket claim, reply and resume, idempotent repeats |
| Evaluation (real model) | `evals/run.py`, results committed |

## Left to the builder

Exact prompt wording, the size of the history window, the rate limit numbers and the price table
used for the cost estimate.
