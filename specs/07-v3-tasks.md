
# Version 3 — implementation plan

**Goal:** implement `06-v3-design.md` (R23 to R33, N13 to N26) and reach its result targets.

**Architecture:** the graph gains a verifier and parallel steps. State moves behind SQLAlchemy
Core so the same store runs on SQLite (offline tests) and Postgres (Docker, several replicas).
Operators gain approve and reject for one agent action.

**Tech stack:** as version 2, plus SQLAlchemy Core, Alembic, psycopg, prometheus-client.

**Spec:** `specs/06-v3-design.md`

## Global constraints

- `docker compose up --build` is still the one command. Postgres is the only new default service; monitoring is an optional profile.
- Offline tests need no API key, no network, no Postgres and no model SDK.
- No support tool accepts a `user_id` argument. The write tool accepts only a terminal of the caller.
- Limits stay in code: 3 specialist runs, the same specialist twice, one verifier pass, a cost cap per request.
- Blind sets (Task 1) are written before any other task and run once, in Task 15. Their failures are not used to change prompts.
- Each task is test-first.
- Development runs use the 37 version 2 cases. After the baseline they run once per case, and only the kinds a change touches; 3 runs per case are kept for the baseline and the final runs. Every real-model run is announced with its estimated cost before it starts.

## Review focus

1. A person with memberships in two merchants sends `user_id` of a third: `403`, the model is not called. (Task 6)
2. A token signed with a key that was removed from the key set: `401`. (Task 6)
3. The verifier call fails or returns an empty answer: the original answer is returned, never an empty one. (Task 3)
4. An approval sent twice, or after a rejection: the action runs once or not at all. (Task 8)
5. The model proposes a replacement for a terminal of another merchant: refused by the tool, nothing is created. (Task 8)
6. Two turns on one conversation at the same moment: one `409`, no interleaved history. (Task 10)
7. A request repeated with the same `Idempotency-Key` after a crash mid-turn: finished specialist runs are not repeated. (Task 10)
8. A page in the knowledge base that says "ignore your instructions": the answer does not follow it. (Task 5)

---

## Phase 1 — results

### Task 1 — Blind sets, before anything changes
Covers: N13, N14, N15, N17

- Files: modify `evals/retrieval_set.jsonl`, `evals/cases.jsonl`, `evals/attacks.jsonl`, `evals/run.py`, `evals/retrieval.py`, `tests/test_evals.py`
- All 37 current cases become `split: dev`.
- Add 60 cases with `split: blind`: 18 knowledge, 12 support, 12 multi, 6 follow-up (two or three turns), 6 handoff resume, 3 approval, 3 abstain. At least 4 merchants. Half in Portuguese.
- Add 40 retrieval questions with `split: blind` (20 hard), and 20 with `kind: adversarial` (10 unanswerable with `gold: []`, 5 look-alike products, 5 run against a test collection holding a page with instructions).
- Attacks to 100 with a `category` field; normal messages to 60.
- `evals.run` and `evals.retrieval` refuse the blind split unless `--final` is given, and stamp the report with the git commit.
- The gold pages and reference answers are checked by the author by hand, as in version 2.
- Tests first: `--split blind` without `--final` exits with an error; the report carries the commit.

### Task 2 — Model comparison and cost
Covers: N26, R33

- Files: modify `app/config.py`, `app/llm.py`, `app/agents/*.py`, `evals/run.py`; create `evals/compare.py`, `tests/test_cost.py`
- Produces:
  - settings `knowledge_model`, `support_model`, `router_model`, `verifier_model`, `summary_model`, each with an effort setting; `ANTHROPIC_MODEL` remains the default for all
  - `cache_control` on the system prompt and tools, and on the last tool result of each loop turn; `Usage` gains `cache_read_tokens`, and cost uses the cache-read price
  - `settings.max_request_cost_usd`; `llm.BudgetExceeded`, handled as a failed finding
  - `python -m evals.compare a.json b.json` — a table of pass rate, each verdict, cost and latency for two runs
- Tests first: cost with cached tokens is computed at the cache price; a loop that passes the cap stops and the response is still valid.
- The default answering model becomes Sonnet 5.5 and the judge Opus 5.5.
- Real-model run: the 37 dev cases, 3 runs, on Sonnet. This is the baseline every later change is measured against. It is compared with the committed Opus run on the code checks (outcome, agents, tools, facts), which do not depend on the judge.

### Task 3 — Verifier and stricter specialists
Covers: R26

- Files: create `app/agents/verifier.py`; modify `app/graph.py`, `app/agents/knowledge.py`, `app/agents/support.py`, `app/agents/synthesizer.py`, `tests/conftest.py`, `tests/test_graph.py`
- Produces:
  - `Verification(supported: bool, unsupported: list[str], revised: str)`
  - `verifier_node(state)` after `synthesizer`; workflow step status `ok | revised | skipped`
  - specialist prompts: state only what the tool output states; no causes, advice or next steps of your own
- Tests first:
  - a supported answer is returned unchanged
  - an answer with one unsupported sentence comes back as `revised` and the step says so
  - the verifier raises, or returns an empty `revised`: the original answer is returned, step `skipped`
  - handoff, hold and blocked responses do not call it
- Real-model run: the dev cases once with the verifier on, compared with the Task 2 baseline (which has no verifier) with `evals.compare`.

### Task 4 — Web search evidence
Covers: the brief's general questions (target row 4)

- Files: modify `app/llm.py`, `evals/judge.py`, `app/agents/router.py`, `tests/test_tools.py`
- First step: read the current web search documentation for the fields a cited passage carries.
- Evidence for `web_search` becomes title, link and each cited passage. `WEB_SEARCH_NOTE` and the judge's leniency for web search are removed.
- Tests first: a response with two citations yields evidence holding both passages.

### Task 5 — Retrieval
Covers: target row 5, N14 · review focus 8

- Files: modify `app/rag/ingest.py`, `app/rag/retriever.py`, `evals/retrieval.py`, `tests/test_tools.py`; create `evals/diagnose.py`
- `python -m evals.diagnose` — for each missed question: is the gold page in the 40 candidates, and at what rank? Decides the fix.
- In order, measuring after each on the main and confirm splits: page title and section heading at the start of every chunk; BM25 fused with the vector ranking in place of the keyword bonus; a multilingual reranker over the 40 candidates only if hard recall@6 is under 0.85.
- The CI gate `--min-recall` is raised to the new measured value minus a margin.
- Tests first: a chunk's text starts with its page title; fusion ranks a document found by both searches above one found by either; a retrieved page containing instructions reaches the model inside the reference-material wrapper.

---

## Phase 2 — capabilities

### Task 6 — Authorization lookup and key rotation
Covers: R23, R24 · review focus 1, 2

- Files: modify `app/auth.py`, `app/devtokens.py`, `app/store.py`, `app/main.py`, `data/users.json`, `tests/test_auth.py`, `tests/conftest.py`, `scripts/demo.sh`
- Produces:
  - `Principal(subject, role, scopes: frozenset[str])`
  - `store.membership(subject, merchant_id) -> dict | None`; seeded from `users.json`
  - `require_merchant` returns the merchant id from the lookup; `require_scope(scope)`
  - key set: `AUTH_JWKS_URL` or `AUTH_JWKS_FILE`; `devtokens` writes two keys and signs with the newer
- Tests first:
  - a person with two memberships reaches each with the matching `user_id`, and gets `403` for a third
  - an inactive membership: `403`
  - tokens signed with either current key pass; a token whose `kid` is not in the set: `401`
  - an operator without `tickets:write` cannot reply; without `actions:approve` cannot approve
  - a table-driven test of every endpoint against no token, merchant, operator, wrong owner

### Task 7 — Account service and typed tools
Covers: R28

- Files: create `app/tools/account.py`, `tests/contract/test_account_service.py`; modify `app/tools/support_tools.py`, `app/agents/support.py`, `tests/test_tools.py`
- Produces: `AccountService` protocol; `JsonAccountService`; result models `Settlements`, `Terminals`, `Transactions`; errors `NotFound`, `Unavailable(retryable=True)`; a per-call timeout
- Tests first: the contract suite, parametrised by implementation: unknown merchant, shapes of each result, a slow implementation times out and the agent receives a retryable error.

### Task 8 — An action that needs approval
Covers: R29, R30 · review focus 4, 5

- Files: modify `app/agents/support.py`, `app/agents/escalation.py`, `app/store.py`, `app/main.py`, `app/schemas.py`, `app/graph.py`; create `tests/test_actions.py`
- Produces:
  - tool `request_terminal_replacement(terminal_id, reason)`
  - `store.create_action(...)`, `approve_action(action_id, operator) -> (action, changed)`, `reject_action(action_id, operator, reason)`
  - ticket fields `kind` (`question | approval`), `priority`, `due_at`; `store.release_ticket`
  - `POST /tickets/{id}/approve`, `/reject`, `/release`; `GET /tickets?overdue=true`
  - `graph.resume_after_decision(ticket_id, operator, approved, reason)`
- Tests first:
  - the proposal creates one pending action and one approval ticket; the conversation is not on hold
  - approve: the action is executed once, the conversation gains the outcome; approve again: `200`, no second execution
  - reject: nothing executed, the reason reaches the merchant; approve after reject: `409`
  - a terminal that is not the caller's: tool error, no action row
  - release returns a claimed ticket to the queue; fraud tickets list first; a ticket past `due_at` appears under `overdue`

### Task 9 — Parallel steps
Covers: R27

- Files: modify `app/agents/router.py`, `app/graph.py`, `app/state.py`, `tests/test_graph.py`
- Produces: `PlanStep(agent, task, depends_on_previous)`; `after_router` returns two `Send` targets when the first two steps are independent
- Tests first: two independent steps both run before the next Router call, and the Router's input holds both results in full; a dependent plan still runs in sequence; the 3-run limit counts both.

### Task 10 — Postgres, checkpoints and idempotent requests
Covers: R31, R32, N23 · review focus 6, 7

- Files: rewrite `app/store.py` on SQLAlchemy Core; create `migrations/`, `alembic.ini`, `scripts/backup.sh`, `scripts/replicas.sh`; modify `app/graph.py`, `app/main.py`, `app/ratelimit.py`, `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.github/workflows/ci.yml`, `tests/test_store.py`, `tests/test_memory.py`
- Produces:
  - `DATABASE_URL`; migrations `001` (the version 2 schema) and `002` (version 3 tables); a `migrate` compose service that the API waits for
  - `store.begin_turn(conversation_id, message, idempotency_key) -> dict` — raises `store.Busy` when another turn holds the lease; returns the stored turn when the key was seen
  - `store.save_step(turn_id, state)`, `store.finish_turn(turn_id, response)`
  - `ratelimit.check` backed by the `rate_limits` table
  - `GET /ready` — database reachable, index loaded
  - `scripts/replicas.sh` — turn 1 to one API container, turn 2 to another, then the operator reply through the first
- Tests first:
  - every version 2 store test passes unchanged on SQLite; CI repeats them on a Postgres service
  - the same key twice: one turn stored, the same response, the model called once
  - a turn interrupted after its first specialist, then repeated with the same key: that specialist is not called again
  - a second turn while the lease is held: `409`
  - the rate limit is shared by two store connections

### Task 11 — Output masking and secrets
Covers: R25, N25, N24

- Files: modify `app/guardrails.py`, `app/graph.py`, `app/tracing.py`, `app/config.py`, `docker-compose.yml`, `.github/workflows/ci.yml`; create `SECURITY.md`
- Produces: `guardrails.mask_sensitive(text)` — cards (Luhn) and CPF (check digits); applied to the message in, the answer out and every log line; `config.secret(name)` reads `NAME_FILE` then `NAME`
- `SECURITY.md`: a threat table — asset, threat, control, the test that proves it.
- CI: `pip-audit` and a secret scan.
- Tests first: a CPF and a card in a tool result are absent from the response and the log; a CPF-like number with wrong check digits is kept; a secret given as a file is read.

---

## Phase 3 — operations and evidence

### Task 12 — Metrics, dashboard and alerts
Covers: N21, N22

- Files: create `app/metrics.py`, `monitoring/prometheus.yml`, `monitoring/alerts.yml`, `monitoring/dashboard.json`, `tests/test_metrics_endpoint.py`; modify `app/tracing.py`, `app/main.py`, `docker-compose.yml`, `requirements.txt`
- Metrics: requests by outcome, request and step duration, tokens and cost by model, specialist runs per request, rejected findings, verifier revisions, handoffs by reason, guardrail blocks by layer, rate-limited requests.
- Alerts: escalation rate, error rate, 95th percentile latency, cost per request, guardrail block rate at zero.
- Tests first: one request moves the request, step, token and cost series; a handoff moves the handoff counter with its reason.

### Task 13 — Judge and labels
Covers: N16, N18

- Files: modify `evals/judge.py`, `evals/run.py`, `evals/agreement.py`, `evals/human_labels.jsonl`, `app/config.py`, `tests/test_evals.py`
- Produces: `Verdict.useful`; `JUDGE_PROVIDER` (`anthropic` by default; a second provider when its key is set); 95% Wilson intervals in every report row
- 40 more answers sampled from the dev runs for the author to label, to 60.
- Tests first: the interval for 9/10 and for 0/10; agreement reports `useful`; the judge refuses to run when its model equals the answering or verifying model.

### Task 14 — Reproducible evidence
Covers: N19, N20, N23 (image)

- Files: create `Makefile`, `.github/workflows/eval.yml`, `.github/workflows/release.yml`, `evals/smoke.jsonl`; modify `app/llm.py`, `README.md`
- `anthropic` is imported inside the client factory, so `pytest` collects without it.
- `eval.yml`: on request and weekly; runs 12 cases once, the guardrail benchmark and the retrieval gate; fails under the thresholds; uploads raw results. Needs the repository secret `ANTHROPIC_API_KEY`.
- `release.yml`: a tag builds and publishes the image.
- `make test`, `make eval-offline`, `make demo`.

### Task 15 — Final runs
Covers: every result target

- Freeze prompts and settings in one commit. Then, once each, with `--final`: the blind retrieval split; the blind answer set, 3 runs; the 100-attack benchmark; the brief's scenarios, 3 runs; the single-route comparison (`MAX_SPECIALIST_RUNS=1`, verifier off) on the multi cases.
- Label the sampled answers; run `evals.agreement`.
- Commit every raw report. Nothing is rerun to improve a number; a missed target is written up.

### Task 16 — README and decision records
- Files: modify `README.md`; create `specs/decisions.md`
- The README opens with the result table (target, measured, where the raw file is), then quick start. Long sections move to `docs/`.
- `specs/decisions.md`: one short record per decision in the design's "Approaches considered", with what was measured.
- The "What is not built" list is rewritten from the design's "Out of scope".

## If time runs out

Tasks 1 to 5, 8, 13 and 15 carry the result targets and the largest review items. Tasks 9 and 12
are the first to drop; each dropped task is named in the README as not built.

## What was built

The must-do set was built: Tasks 1, 2, 3, 4, 5, 8, 13 and 15. Tasks 6 and 14 were built after the
final runs; they change who may call the service and how it is tested, not what the agents answer.
Task 10 was then built on SQLite instead of Postgres, and Task 12 without a dashboard, together with
the secret file from Task 11. Tasks 7, 9 and 16 and the rest of Task 11 were not built, and the
README's "What is not built" lists what that leaves out.

Decisions taken while building, where the plan was silent or wrong:

- **Unanswerable questions are answer cases, not retrieval rows.** Recall is undefined when no page is
  right, so the 7 of them are `abstain` cases in the blind answer set.
- **The basic web search tool, not the newest.** Measured: the newest returned no quoted passages, and
  the passages are the evidence a general answer is checked against.
- **No reranker.** Keyword fusion reached the retrieval target on the development questions. On the
  blind split it scored 0.927 against a target of 0.95.
- **One cache marker, on the system prompt.** Most tool loops are two calls; a marker inside the loop
  would be written and never read.
- **The cost cap is a rule in the Router.** After it, no review call and no further specialist: the
  request finishes with what it has or hands off.
- **Settings only where a decision uses one**: `ANTHROPIC_MODEL`, `ROUTER_MODEL`, `VERIFIER_MODEL`,
  `JUDGE_MODEL`, not one per agent.
- **The language is named by the Router.** Found by the evaluation: told only to "reply in the
  merchant's language", the specialists answered English questions in Portuguese when the data in
  front of them was Portuguese.
- **The Router's review judges the main answer; the Verifier removes unsupported details.** With both
  rejecting on any detail, a good web answer was rejected twice and went to a human.
- **Stored blind answers were graded again, not regenerated**, after the evaluation was found to
  withhold ticket numbers from the judge. Both gradings are in `evals/reports/`.
- **A version 2 database is upgraded in place** (`store._upgrade`), because versioned migrations are
  in Task 10.
- **The judge is compared with a person only on answers its own model did not write.** The 40 blind
  answers (Sonnet) are compared with the current judge (Opus); the 20 from version 2 (Opus) keep
  that version's comparison. The kappa target was missed: agreement is 39/40 or better on every
  verdict, and with so few "false" labels one disagreement sets kappa to 0.
- **Task 6: the request body still carries `user_id`, and a helper resolves it.** The plan had
  `require_merchant` return the merchant id. A dependency cannot read the body cleanly, so the
  endpoint calls `auth.act_for(principal, user_id)`, which returns the id from the membership row.
- **Task 6: memberships are seeded from `members` lists in `users.json`** and kept in a table, so
  access can be withdrawn at run time (`store.set_membership`).
- **Task 6: the key set file is read on every request.** It is one small file, and a rotation is
  picked up at once. A key set URL is cached for five minutes by the token library.
- **Task 14: the smoke sample is a list of 12 case ids (`evals/smoke.txt`)**, not a second file of
  cases, so a case has one definition.
- **Task 14: offline and CI runs write their reports under their own names** (`offline_*`,
  `smoke_*`). Running the guardrail check without the model had replaced the final report.
- **Task 14: the real-model workflow is written and not yet run.** It needs a push and the
  repository secret.
- **Task 10 on SQLite, not Postgres.** Checkpoints, idempotency keys, the turn lease, migrations,
  the shared rate limit and backup do not need Postgres. Only running several replicas does, and
  that is left as the next step. No SQLAlchemy and no Alembic: the migrations are a list of
  numbered steps in one module.
- **Task 10: the idempotency key belongs to the merchant, not to the conversation.** A first
  message has no conversation yet, so a key tied to one could not match its own repeat.
- **Task 10: the saved turn holds a hash of the message, not the message**, so a card number is
  never written there. The hash is taken after masking.
- **Task 10: a killed process waits out its lease.** An attempt that stops with an error marks its
  turn interrupted and the repeat continues at once. A process killed outright cannot do that, so
  the repeat is refused for up to 120 seconds. Taking over sooner would risk two runs of one turn.
- **Task 10: checked against the real model.** The 12-case sample passed 12 of 12 after the change
  (`evals/reports/answers_smoke_checkpoints.md`), at $0.026 per request.
- **Task 12: `/metrics` needs no token.** It carries counts only, and a test checks that no id, name
  or message text appears in it. It is meant to be reachable only inside the network.
- **Task 12: Prometheus and alert rules, no dashboard and no Alertmanager.** The rules are checked
  by `promtool` and by a test that every metric they name is exported.
- **Task 14: the `eval` workflow runs only when started by hand**, not weekly as planned. Each run
  spends API credit on the owner's key.
- **After the first `eval` workflow run: a handoff Support asks for is reviewed by the Router.** It
  costs one more Router call on a real handoff. In return, an error code missing from the account data
  goes to Knowledge instead of to a human.
