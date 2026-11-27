
**Global constraints**

- Python 3.12. Dependencies pinned in `requirements.txt`.
- No support tool accepts a `user_id` argument (R6).
- Message limit: 2,000 characters (R9).

---

## 1. Project skeleton, schemas, state
Covers: R1, R10

- Files: `requirements.txt`, `pytest.ini`, `.env.example`, `.gitignore`, `app/config.py`, `app/schemas.py`, `app/state.py`
- Produces:
  - `ChatRequest(message: str 1..2000, user_id: str)`
  - `ChatResponse(response, agent_workflow: list[dict], sources: list[str], handoff: dict | None, trace_id)`
  - `ChatState` as defined in the design
  - `settings.model`, `settings.router_model`, `settings.data_dir`, `settings.chroma_dir`


## 2. Guardrail
Covers: R9 · scenario 12

- Files: `app/guardrails.py`, `tests/test_tools.py`
- Produces: `check_input(message: str) -> str | None` — the reason a message is blocked, or `None`
- Tests first: an injection phrase in English and in Portuguese returns `"prompt_injection"`; a normal product question returns `None`.


## Task 3 — Mock user data and support tools
Covers: R5, R6 · scenarios 3, 5, 8, 13

- Files: `data/users.json`, `app/tools/support_tools.py`, `tests/test_tools.py`
- Produces: `get_settlement_schedule(user_id)`, `get_terminal_status(user_id)`, `get_recent_transactions(user_id)`, `create_support_ticket(user_id, reason, summary) -> dict`; each returns a JSON-serialisable dict, and `{"error": "user_not_found"}` for unknown users.
- Data: `cliente1988` has one offline terminal, one declined transaction and a pending payout; `maria_2020` exists so isolation can be tested. Dates are stored as day offsets so "yesterday" is always yesterday.
- Tests first: each tool returns the seeded values for `cliente1988`; an unknown user returns the error dict; ticket ids are unique and start with `TCK-`.


## Task 4 — RAG: ingest and retrieve
Covers: R3, N2

- Files: `app/rag/ingest.py`, `app/rag/retriever.py`, `data/kb_pages/*.md`
- Produces:
  - `fetch_pages() -> int` — product pages plus help-centre URLs from the sitemap, cleaned and saved
  - `build_index() -> int` — chunks (LangChain splitter, 900/150), embeds and stores; `python -m app.rag.ingest [--fetch]`
  - `search(query: str, k: int = 6) -> list[dict]` with keys `text`, `source`, `title`, `score`


## Task 5 — LLM layer
Covers: design § LLM layer

- Files: `app/llm.py`
- Produces:
  - `classify(system: str, user: str, schema: type[BaseModel], model: str | None = None) -> BaseModel`
  - `run_agent(system: str, user: str, tools: list[dict], handlers: dict[str, Callable[[dict], Any]], max_turns: int = 6) -> AgentResult(text, tools_used, sources)`
- Behaviour: handles `tool_use`, `pause_turn` and `refusal` stop reasons; a handler that raises becomes an error result for the model.


## Task 6 — Agents and tracing
Covers: R2–R8, R11, N4

- Files: `app/agents/router.py`, `knowledge.py`, `support.py`, `escalation.py`, `app/tracing.py`
- Produces: one function per agent, `(state: ChatState) -> dict`; `guardrail_node`; `traced(agent: str, node) -> node`
- Prompts live at the top of each agent file as a module constant.


## Task 7 — Graph and integration tests
Covers: R2, R8, N5 · scenarios 11, 12, 13

- Files: `app/graph.py`, `tests/conftest.py`, `tests/test_graph.py`
- Produces: `build_graph()` and `run_chat(message: str, user_id: str) -> ChatResponse`
- Tests first (LLM layer replaced by a fake in `conftest.py`):
  - router says `knowledge` → workflow is guardrail, router, knowledge
  - router says `support` → support runs with tools bound to the request user
  - support tools called for `cliente1988` never return `maria_2020` data (R6)
  - support calls `escalate_to_human` → escalation runs, ticket id in the response
  - router says `escalation` → ticket opened
  - router confidence `low` → escalation
  - injection message → only guardrail in the workflow, model never called
  - knowledge agent raises → escalation, valid response (N5)


## Task 8 — API and Docker
Covers: R1, N1

- Files: `app/main.py`, `tests/test_graph.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- Test first: `POST /chat` returns 200 with all five response fields.


## Task 9 — End-to-end run and README
Covers: definition of done

- Files: `scripts/scenarios.jsonl`, `scripts/demo.sh`, `README.md`
- `demo.sh` sends each scenario to the running service and prints the expected and the actual path.


---


