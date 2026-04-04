# Financial Data MCP Platform

![Python](https://img.shields.io/badge/python-3.10-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Privacy-first financial intelligence platform with:
- MCP tool server
- Python orchestration API (upload + Q&A via LangGraph)
- Separate Next.js web app

## Architecture

```mermaid
flowchart LR
  user[UserBrowser] --> ui[NextJsUI]
  ui --> api[PythonOrchestratorAPI]
  api --> graph[LangGraphAgent]
  graph --> tools[FinanceTooling]
  tools --> ingest[PDFIngestionAndSanitization]
  tools --> analytics[SummaryAnomalyInsights]
  mcp[MCPServerStdio] --> tools
```

## Why this project exists

Financial statements are hard to use with AI safely. This project turns PDFs into sanitized transactions and lets users ask practical budget questions without persisting raw PII.

## Features

- Privacy-first PDF ingestion (`ingest_financial_documents`)
- Session-scoped in-memory transaction state (no cross-user mixing)
- Composite insights tool (`financial_insights`)
- Budget planner capability for savings targets and max-savings estimation
- Q&A orchestration API for frontend apps
- Currency, crypto, and stock tools

## Core Tools

1. `ingest_financial_documents`
2. `list_transactions`
3. `get_spending_summary`
4. `flag_anomalies`
5. `financial_insights`
6. `convert_currency`
7. `get_crypto_price`
8. `get_stock_quote`

## Budget Planning Capability

The LangGraph orchestrator includes an internal deterministic tool (`plan_savings`) for savings planning.

- It analyzes ingested historical debit transactions by month and category.
- It estimates `max_savings_estimate` with category-specific cut ceilings.
- It evaluates savings target feasibility (`target_met`) when a target is provided.
- It returns category-level recommendations and assumptions in `supporting_data`.

Sample prompts:
- "How can I save 300 this month?"
- "What is the max savings I can do this month?"
- "Plan savings aggressively for a 500 target."

Notes:
- This capability is API/LangGraph only (not directly MCP-exposed yet).
- It requires ingested transaction history first.

## Repository Layout

- `app/main.py` - MCP registration + FastAPI app bootstrap
- `app/api/orchestrator.py` - upload/chat/session API routes
- `app/api/schemas.py` - response/request contracts
- `app/agent/` - LangGraph state, prompts, nodes, graph, and runner
- `app/tools/ingestion.py` - PDF extraction + sanitization
- `app/tools/transactions.py` - analytics over ingested session data
- `app/tools/insights.py` - composite summary + anomaly interpretation
- `ui/` - production Next.js web app
- `tests/` - backend unit/API tests

## Quickstart

### 1) Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
```

Run orchestration API:

```bash
uvicorn app.main:app --reload
```

### 2) Frontend

```bash
cd ui
npm install
npm run dev
```

Frontend default URL: `http://localhost:3000`
Backend default URL: `http://localhost:8000`

## Orchestration API Endpoints

The `POST /api/chat` endpoint now uses a LangGraph workflow:
- session validation
- ingestion guardrails
- Anthropic planning (with deterministic local fallback)
- iterative tool execution
- answer composition
- privacy safety filtering

### `POST /api/session`
Create a new user session.

Response:

```json
{"session_id":"<uuid>"}
```

### `GET /api/session/{session_id}/status`
Inspect whether a session has ingested data.

### `POST /api/documents/ingest?session_id=<uuid>`
Multipart upload endpoint for statement PDFs.

Response:

```json
{
  "session_id":"<uuid>",
  "count":42,
  "sources":2,
  "warnings":[]
}
```

Budget-planning questions return the same response schema and include planner output under:
- `tool_calls`: contains `plan_savings`
- `supporting_data.plan_savings`: deterministic planning payload (estimate, recommendations, warnings)

### `POST /api/chat`

Request:

```json
{
  "session_id":"<uuid>",
  "question":"What are my top spending categories?"
}
```

Response:

```json
{
  "session_id":"<uuid>",
  "answer":"Total spending in the selected data is 1234.56 USD.",
  "tool_calls":["get_spending_summary"],
  "supporting_data":{},
  "warnings":[]
}
```

## Privacy Guarantees

- Raw PDF text is processed ephemerally and never persisted.
- Only sanitized fields are retained: date, amount, merchant, category, currency, direction.
- Sanitization removes long numeric strings, emails, and address-like patterns.
- Logs avoid raw document content.

## Error Contract

```json
{
  "ok": false,
  "error": "No ingested transactions available. Upload PDFs first.",
  "source": "orchestrator"
}
```

## Environment Variables

- `FRONTEND_ORIGINS` (backend CORS, comma-separated)
- `ANTHROPIC_API_KEY` (required for Anthropic-powered planning/composition)
- `LANGGRAPH_ANTHROPIC_MODEL` (optional model override; default `claude-3-5-sonnet-latest`)
- `LANGGRAPH_MAX_STEPS` (optional orchestration step cap; default `4`)
- `NEXT_PUBLIC_ORCHESTRATOR_URL` (frontend API base URL)

## Docker Compose (3 services)

```bash
docker compose up --build
```

Services:
- `orchestrator-api` on `:8000`
- `ui` on `:3000`
- `mcp-server` (stdio MCP process)