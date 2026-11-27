
# Version 3 — requirements and design

Version 2 (specs 04 and 05) answered each finding of the review at a first level. This version
does two things: it closes what is still open in the review's own lists, and it improves the
measured results, because a capability that scores 78% is not finished. Tasks are in
`07-v3-tasks.md`.

## Intent

- Every item the review lists as "not found" is built, or is named below as partial with the reason.
- The numbers in `evals/reports/` reach the targets below, on questions nobody tuned against.
- A reviewer can reproduce the evidence without trusting this README.

## Result targets

| Measure | Version 2 | Target | Measured on |
|---------|-----------|--------|-------------|
| Answer runs passing every check | 68/87 (78%) | ≥ 90% | new blind set, 3 runs each |
| Grounded answers | 63/78 (81%) | ≥ 95% | new blind set |
| Correct answers | 72/78 (92%) | ≥ 95% | new blind set |
| The brief's 10 example questions | 1 fails grounding | 10/10 on 3 runs | `scripts/scenarios.jsonl` |
| Retrieval recall@6, all / hard questions | 0.891 / 0.650 | ≥ 0.95 / ≥ 0.85 | new blind retrieval split |
| Judge agreement with human labels (kappa, grounded) | 0.583 on 20 labels | ≥ 0.70 on 60 labels | `evals/agreement.py` |
| Attacks stopped / normal messages blocked | 30/30, 1/20 | ≥ 98%, ≤ 2% | 100 attacks, 60 normal |
| Cost per request | $0.114 | ≤ $0.06 | same set, same quality |
| Latency, median / 95th percentile | 12.5 s / 26.9 s | ≤ 9 s / ≤ 20 s | same set |

If a target is missed, the report says so. No target is met by editing the set.

## Audit of the review

Every item the review names, and where it stands. "v2" means built and tested in version 2.

| Review section | Item | Status |
|----------------|------|--------|
| Identity | JWT, authenticated principal | v2 |
| Identity | authorization lookup | **R23** (v2 treated the token subject as the merchant) |
| Identity | OIDC, login | **R24** verifies against a JWKS URL, which is the OIDC contract; the login service itself is out of scope |
| Identity | per-merchant API key | not built: one token format covers merchants and operators |
| Orchestration | planner, supervisor, multi-specialist plan, Support→Knowledge, Knowledge→Support, result-based replanning, semantic retry, synthesis | v2 (one Router that plans and reviews) |
| Orchestration | critic, reviewer | v2 reviews each step; **R26** adds a check of the final answer, claim by claim |
| Orchestration | dynamic subtasks | v2 gives each step its own task; **R27** runs independent steps in parallel |
| RAG | held-out set, Recall@K, MRR, nDCG, multilingual breakdown, context precision | v2 |
| RAG | "broad" | **N13** doubles the set with a blind split |
| RAG | adversarial retrieval | **N14** |
| Handoff | operator identity, queue, claim, human response, conversation resume, agent resume | v2 |
| Handoff | approve / reject | **R29, R30** |
| Memory | conversation_id, history, persistent thread, summary, restart recovery, multi-turn follow-up | v2 |
| Memory | checkpoint | **R32** |
| Memory | several replicas (interview question 3) | **R31** |
| Guardrails | broad adversarial benchmark | v2 has 30 attacks; **N15** takes it to 100 in named categories, including injection hidden in tool results |
| Evaluation | correctness, groundedness, completeness, independent judge, human labels, repeated runs | v2 |
| Evaluation | usefulness | **N16** |
| Evaluation | blind holdout | **N17** (the v2 set's failures have been read, so it is now the development set) |
| Evaluation | judge independence, human calibration | **N18** |
| Evaluation | contract tests against real services | **R28** |
| Evidence | raw reproducible report; tests the reviewer can run | v2 commits raw results; **N19** runs them in CI and publishes the artifacts; **N20** makes the offline tests install nothing model-related |
| Observability | JSON logs, token usage, OpenTelemetry | v2 |
| Observability | alerts, routing monitoring, evaluation monitoring, cost drift | **N21, N22** |
| Production | CI, persistent operational state | v2 |
| Production | CD, migrations, shared rate limiting, multi-replica state, backup/recovery | **N23, R31, N24** |
| Production | secrets manager | **N25** reads secrets from mounted files; the manager itself is out of scope |
| Production | production authentication | **R24** |

## New requirements

| ID | Requirement |
|----|-------------|
| R23 | Authorization is a lookup. The token subject is a person. A `memberships` table says which merchants that person may act for. `user_id` in the body selects one of them; any other value is `403`. Operators carry scopes (`tickets:read`, `tickets:write`, `actions:approve`) and an endpoint checks the scope it needs. |
| R24 | Token keys are selected by `kid` from a key set (a JWKS URL or a local file). Two keys can be valid at once, so keys rotate without downtime. A token signed with a removed key is `401`. |
| R25 | Sensitive data is masked on the way out as well as in: card numbers and CPF numbers are removed from answers, stored messages and logs. |
| R26 | Before an answer is returned, a verifier compares it with the tool output it was built from and removes every claim that output does not support. The step is bounded (one pass) and reported in the workflow. |
| R27 | When the Router's plan has steps that do not depend on each other, they run at the same time. The limits of R17 still hold. |
| R28 | Account data is read through one interface with typed results. The demo implementation reads a file; a contract test suite defines what any implementation must do, including timeouts and "not found". |
| R29 | The Support Agent has one tool that changes something: `request_terminal_replacement`. The model can only propose it. It is created as a pending action bound to the caller's own terminal. |
| R30 | An operator with `actions:approve` approves or rejects a pending action. Approval executes it exactly once; a repeated approval returns the stored result. Either way the agent writes the outcome into the conversation. Tickets can also be released, carry a priority, and are listed as overdue after a set time. |
| R31 | State lives in Postgres, so several replicas share conversations, tickets, the audit log and the rate limit. Two requests for the same conversation at the same time: the second gets `409`. |
| R32 | Each finished step of a turn is saved. A request repeated with the same `Idempotency-Key` returns the stored response if the turn finished, and continues from the saved steps if it did not. |
| R33 | A request stops calling the model once it has spent a set cost; it answers with what it has or hands off. |

| ID | Requirement |
|----|-------------|
| N13 | The retrieval set gains a blind split of 40 questions, written before any retrieval change and run once at the end. |
| N14 | An adversarial retrieval set: questions the knowledge base cannot answer (the right result is to abstain), look-alike products, and pages carrying instructions. |
| N15 | The attack set grows to 100 attacks in categories (direct injection, hidden in tool results, role play, data of another merchant, obfuscated, Portuguese and Spanish) and 60 normal messages, with off-topic and sensitive requests reported separately. |
| N16 | The judge gives a fourth verdict, `useful`: the answer deals with what was asked and tells the merchant the next step when the evidence gives one. |
| N17 | A blind answer set of 60 cases (knowledge, support, multi, follow-up, handoff resume, approval), written before the changes, run once after prompts are frozen. Reports give a 95% interval for every rate. |
| N18 | 60 human labels. The judge is not the model that answers or verifies; with a second provider's key it is from another vendor. |
| N19 | A CI job runs a 12-case sample of the answer evaluation against the real model on request and weekly, fails below thresholds, and publishes the raw results. |
| N20 | The offline tests do not import the model SDK. `make test` is the one command. |
| N21 | `GET /metrics` exposes request, step, token, cost, routing, verifier, handoff and guardrail counters. |
| N22 | An optional compose profile starts tracing, metrics, a provisioned dashboard and alert rules. |
| N23 | Schema changes are versioned migrations, applied by a one-shot job before the API starts. A tagged commit publishes the image. A script backs up and restores the database. |
| N24 | CI scans dependencies for known vulnerabilities and the repository for secrets. |
| N25 | Any secret can be given as `NAME_FILE`, a path to a mounted file. |
| N26 | The model used by each agent is a setting, and the choice is backed by a measured comparison of quality, cost and latency. |

## Approaches considered

| Decision | Options | Chosen, and why |
|----------|---------|-----------------|
| Ungrounded advice in answers | Stricter prompts only; retry the specialist; a verifier on the final answer | **Prompts plus a verifier.** Prompts lower the rate; only a check after writing bounds it. A retry costs a whole specialist run and can add new advice. |
| Shared state | Keep SQLite; Postgres with hand-written SQL for two dialects; SQLAlchemy Core with Alembic | **SQLAlchemy Core and Alembic.** One code path runs on SQLite in the offline tests and Postgres in Docker. Alembic is the standard answer to "where are your migrations". |
| Checkpoint and approval | LangGraph checkpointer with `interrupt()`; own tables | **Own tables.** The Router already decides from the list of findings, so resuming is starting the loop with the saved findings. Pending actions need a table the operator queue can list anyway. |
| Hard retrieval questions | Cross-encoder reranker; BM25 fused with vectors; titles inside chunks | **Diagnose first** (is the right page among the 40 candidates?). Then titles in chunks and BM25 fusion; a reranker only if hard recall is still under 0.85, because it adds a model to the image. |
| Which model answers | Opus everywhere; Sonnet everywhere; mixed | **Sonnet 5.5 answers, Opus 5.5 judges.** Sonnet costs half of Opus per token. Its first run on the development set is compared with the committed Opus run on the checks done by code, which do not depend on the judge. If it is clearly worse on one agent, that agent alone goes back to Opus (N26). |
| Shared rate limit | Redis; a Postgres table | **Postgres table.** No third service. |
| Metrics | OpenTelemetry metrics; Prometheus client | **Prometheus client.** One endpoint, readable in a browser. |

## Architecture

```
START → guardrail → router ⇄ knowledge | support   (independent steps in parallel)
                      │            │
                      │            └→ pending action → operator approves / rejects → resume
                      ├→ synthesizer → verifier → END
                      ├→ escalation → END
                      └→ END (blocked)          guardrail → hold → END (a human has the conversation)

api ×N ── Postgres (conversations, messages, turns, tickets, actions, memberships, audit, rate limit)
```

## Components

### Authorization — `app/auth.py`, `app/store.py` (R23, R24)
`Principal(subject, role, scopes)`. `require_merchant` resolves `(subject, body.user_id)` through
`store.membership(subject, merchant_id)`; the returned merchant id is the only value passed to the
graph. `require_scope("actions:approve")` guards operator endpoints. Keys come from
`AUTH_JWKS_URL` or `AUTH_JWKS_FILE`, cached, selected by the token's `kid`. `app/devtokens.py`
writes a key set with two keys so rotation is shown, not described.

### Verifier — `app/agents/verifier.py` (R26)
One structured call after the synthesizer: the answer plus the evidence of the findings it used.
Output `{supported, unsupported: [quoted sentences], revised}`. When `supported` is false the
answer becomes `revised`. Not run for handoff, hold or blocked responses. If the call fails the
answer is returned as written and the step is marked `skipped`. Exempt by rule: the support
line, and arithmetic on tool figures.

### Parallel steps — `app/graph.py`, `app/agents/router.py` (R27)
`Decision.plan` items gain `depends_on_previous: bool`. When the first two planned steps are for
different specialists and neither depends on the other, the graph sends both at once and the
Router reviews both findings in one call.

### Account service — `app/tools/account.py` (R28)
`AccountService` protocol: `status`, `settlements`, `terminals`, `transactions`,
`request_replacement`. Results are pydantic models. `JsonAccountService` is the demo.
`tests/contract/` runs the same tests against every implementation.

### Actions and approval — `app/agents/support.py`, `app/store.py`, `app/main.py` (R29, R30)
`request_terminal_replacement(terminal_id, reason)`: `terminal_id` must be one of the caller's
terminals. It writes an `actions` row (`pending → approved → executed`, or `rejected`) and a
ticket of kind `approval`. Approval tickets do not put the conversation on hold.
`POST /tickets/{id}/approve`, `/reject`, `/release`. Each transition is a conditional `UPDATE`.

### Store — `app/store.py`, `migrations/` (R31, R32, N23)
Same functions as v2, on SQLAlchemy Core. `DATABASE_URL` defaults to the SQLite file. New
tables: `memberships`, `turns` (message, status, saved state, idempotency key), `actions`,
`rate_limits`. `conversations.busy_until` is a lease taken at the start of a turn.

### Cost — `app/llm.py`, `app/config.py` (R33, N26)
Prompt caching on the system prompt, tools and the growing tool loop. `MAX_REQUEST_COST_USD`.
`KNOWLEDGE_MODEL`, `SUPPORT_MODEL`, `ROUTER_MODEL`, `VERIFIER_MODEL`, each with an explicit effort.

### Web search evidence — `app/llm.py`
The passages the search tool cites are kept as evidence, so the Router, the verifier and the
judge can check a general answer against text, not titles.

### Metrics and monitoring — `app/metrics.py`, `monitoring/` (N21, N22)
Counters and histograms updated in `traced()` and `run_chat`. `docker compose --profile
monitoring up` adds Prometheus, Grafana and a trace viewer, with `monitoring/alerts.yml`.

## Out of scope, by decision

A login service, a secrets manager, a real merchant backend, an operator user interface, and
sampling of live answers by the judge. The code has the seam for each and the README says so.

## Left to the builder

Prompt wording, the exact metric names, the dashboard layout, and the choice between BM25 and a
reranker after the diagnosis.
