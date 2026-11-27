
## Architecture

Any agent that raises an error sets `escalation_reason`, and the graph sends the
request to the escalation agent.

## Stack and why

| Choice | Reason |
|--------|--------|
| Python 3.12 + FastAPI | Typed request/response models, automatic OpenAPI docs. |
| LangGraph `StateGraph` | The orchestration is a graph, so it is written as one: state, nodes, conditional edges. |
| Anthropic SDK, called directly inside the nodes | One small file (`llm.py`) owns every model call. |
| Chroma (persistent, local) | Real vector store with zero infrastructure. |
| LangChain text splitter | Standard, well tested chunking. |
| fastembed, `paraphrase-multilingual-MiniLM-L12-v2` | The knowledge base is in Portuguese and questions arrive in English. Runs on CPU. |
| Anthropic server side web search | No second provider or key for general questions. |

## Shared state

```python
class ChatState(TypedDict, total=False):
    message: str
    user_id: str
    trace_id: str
    route: str              # knowledge | support | escalation | blocked
    confidence: str         # high | medium | low
    response: str
    sources: list[str]
    escalation_reason: str  # set by any node that wants a human handoff
    handoff: dict           # {"ticket_id", "reason"} once a ticket exists
    steps: Annotated[list[dict], operator.add]   # one entry per agent that ran
```

Communication mechanism: direct function calls. Each node is a function
`(state) -> partial state update`; LangGraph merges the update and picks the next node.

## Components

### Guardrail — `app/guardrails.py` (R9)
Plain code, no LLM, runs first. Blocks blank or >2,000-character messages and a short list of
prompt-injection phrases (English and Portuguese). The second, semantic layer is the router's
`blocked` route.

### Router Agent — `app/agents/router.py` (R2, R8)
One LLM call with structured output:
`{route: knowledge|support|escalation|blocked, confidence: high|medium|low, reason: str}`.
`confidence == low` is rewritten to `escalation`. Confidence is categorical because models
are poorly calibrated on numeric scores.

### Knowledge Agent — `app/agents/knowledge.py` (R3, R4, R11)
Tool loop with two tools. The model decides which to call:
- `search_getnet_kb(query)` — retrieves the best 6 chunks from Chroma. The prompt tells the
  model to write the query in Portuguese, because the pages are.
- `web_search` — Anthropic server tool, for anything not about Getnet.

It must answer only from tool results and say so when they do not contain the answer.

### Customer Support Agent — `app/agents/support.py` (R5, R6, R8)
Tool loop over mock data in `data/users.json`:
- `get_settlement_schedule()` — payouts with dates, amounts and the settlement terms
- `get_terminal_status()` — each card machine, connectivity, last error
- `get_recent_transactions()` — last transactions, including decline reasons
- `escalate_to_human(reason)` — sets `escalation_reason`

**No tool takes a `user_id` argument.** The handlers are bound to the request's `user_id`
in code, so a prompt cannot make the model read another customer's data (R6).

### Escalation Agent — `app/agents/escalation.py` (R7, N5)
Calls `create_support_ticket`, then asks the LLM for a short handoff message in the user's
language. If that LLM call fails, it falls back to a fixed template. This is the one agent
that must work when the model provider is down.

### LLM layer — `app/llm.py`
- `classify(system, user, schema)` — structured output via `client.messages.parse`.
- `run_agent(system, user, tools, handlers)` — the tool loop: call the model, run the
  requested tools, send results back, repeat (max 6 turns). Returns text, tools used, sources.
  A tool that raises is reported back to the model as an error result.

Model is set by `ANTHROPIC_MODEL`. `ROUTER_MODEL` can point the router at a smaller model.

## RAG pipeline — `app/rag/` (R3, N2)

| Stage | What happens |
|-------|--------------|
| Ingestion | `ingest.py --fetch` downloads a hand-picked list of product pages plus every help centre page found in the site's sitemap. It strips navigation and scripts, drops lines repeated on more than 30% of pages (menu and footer text), skips duplicate pages, and saves clean text to `data/kb_pages/*.md`. The snapshot is committed. |
| Chunking | LangChain `RecursiveCharacterTextSplitter`: up to 900 characters with 150 overlap, cutting at paragraphs, then lines, then sentences. |
| Storage | Each chunk is embedded together with its page title (fastembed) and stored in a persistent Chroma collection with `source` URL metadata. Built at Docker build time. |
| Retrieval | Hybrid: the query is embedded with the same model and the 40 closest chunks are fetched; a bonus for containing the query's exact words re-orders them and the best 6 are returned. |
| Generation | Chunks are returned to the Knowledge Agent as a tool result with their source URLs; the model answers from them. |

Sources: Getnet Brazil product pages (card machines, Pix, crediário, Payment Link, WhatsApp
payments, Get Tap, checkout, digital account, receivables advance), the help centre
(`/get-ajuda*`: error codes, Wi-Fi setup, Pix, payouts) and `getnet.net/en`.

## API — `app/main.py` (R1, R10)

`POST /chat` response:

```json
{
  "response": "…",
  "agent_workflow": [
    {"agent": "guardrail", "detail": "passed", "latency_ms": 0},
    {"agent": "router", "detail": "support (high): asks about own payout", "latency_ms": 900},
    {"agent": "support", "tools": ["get_settlement_schedule"], "latency_ms": 2100}
  ],
  "sources": [],
  "handoff": null,
  "trace_id": "9f1c…"
}
```

`GET /health` returns `{"status": "ok"}`.

## Tracing — `app/tracing.py` (N4, N5)
`traced(name, node)` wraps every agent when the graph is built. It measures latency, appends
the step to `state.steps`, catches exceptions (turning them into `escalation_reason`), and
writes one log line with the request's `trace_id`.

## Testing (N3)

| Layer | What | Needs API key |
|-------|------|---------------|
| Unit | support tools, guardrail | no |
| Integration | the full graph and the HTTP endpoint with the LLM layer replaced by a fake: every route, handoff, agent failure, data isolation | no |
| End to end | `scripts/demo.sh` sends the scenarios to the running service and prints expected and actual path | yes |


