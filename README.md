# AI Data Analysis & Insight Agent Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-blueviolet.svg)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-grade backend that lets users interact with their datasets using natural language. Upload a CSV or Excel file, ask questions in plain English, and get back structured answers, auto-generated charts, key findings, and suggested follow-up questions — all powered by a multi-node LangGraph agent.

## What's new in v2

| Feature | v1 | v2 |
|---------|----|----|
| Agent framework | LangChain `AgentExecutor` (ReAct string parsing) | LangGraph `StateGraph` with explicit nodes |
| Planning | None — agent decides on the fly | Dedicated **planner node** creates a step-by-step `AnalysisPlan` before any tools run |
| Output format | Plain text, manually parsed | Fully typed Pydantic models (`AnalysisResult`, `FollowUpQuestions`) |
| Follow-up questions | Not supported | 3–5 contextual follow-ups generated after every analysis |
| Conversation threading | Not supported | `session_id` + `parent_query_id` link related queries |
| Streaming | Not supported | SSE streaming endpoint (`/query/stream`) emits `node_start`, `plan_ready`, `tool_call`, `complete` events |
| Concurrency safety | Module-level global singletons | Per-request `AnalysisContext` — no shared mutable state |
| Tool inputs | Raw JSON strings, brittle parsing | Typed function signatures, schema inferred by LangChain |
| Multi-model | Single model for everything | `gpt-4o` for planning/synthesis, `gpt-4o-mini` for tool loop |

## Architecture

```
POST /query
    │
    ▼
RelevanceGuard          ← validates question relevance (structured output)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph StateGraph                    │
│                                                          │
│  [START] ──► planner ──► tool_executor ◄──┐             │
│                               │            │             │
│                               ▼            │             │
│                            tools ──────────┘             │
│                               │                          │
│                               ▼                          │
│                         synthesizer                      │
│                               │                          │
│                               ▼                          │
│                        follow_up_gen ──► [END]           │
└─────────────────────────────────────────────────────────┘
    │
    ▼
PostgreSQL + Redis cache
```

### Node responsibilities

| Node | Model | Role |
|------|-------|------|
| **planner** | gpt-4o | Reads dataset schema + question, produces structured `AnalysisPlan` (steps, complexity, needs_visualization). No tool access — pure reasoning. |
| **tool_executor** | gpt-4o-mini | Drives the tool-calling loop using the plan as context. Calls `load_dataset`, `execute_python`, `create_visualization`. |
| **tools** | — | LangGraph `ToolNode` dispatches tool calls and returns `ToolMessage` results. |
| **synthesizer** | gpt-4o | Reads tool transcript, produces structured `AnalysisResult` (answer, key_findings, confidence). |
| **follow_up_gen** | gpt-4o | Generates 3–5 `FollowUpQuestion` objects with rationale for each. |

## Quick Start

### Docker (recommended)

```bash
cp .env.example .env   # add OPENAI_API_KEY
docker-compose up --build
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### Local

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

createdb ai_platform_db
alembic upgrade head
redis-server &

uvicorn app.main:app --reload
```

## API

### Upload a dataset

```bash
curl -X POST http://localhost:8000/api/v1/datasets/upload \
  -F "file=@sales_data.csv"
```

```json
{
  "dataset_id": "550e8400-...",
  "filename": "sales_data.csv",
  "status": "ready",
  "metadata": { "rows": 1000, "columns": 4, "column_names": ["date", "product", "region", "revenue"] }
}
```

### Query (standard)

```bash
curl -X POST http://localhost:8000/api/v1/queries/datasets/{dataset_id}/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Which region has the highest revenue?"}'
```

```json
{
  "query_id": "7c9e6679-...",
  "answer": "The North region generated the highest revenue at $2,456,789 (35% of total).",
  "key_findings": [
    "North: $2,456,789 (35%)",
    "South: $2,100,234 (30%)",
    "West trails by 15% vs North"
  ],
  "confidence": "high",
  "analysis_plan": {
    "reasoning": "...",
    "steps": [
      { "step_number": 1, "tool_to_use": "load_dataset", "description": "Inspect columns" },
      { "step_number": 2, "tool_to_use": "execute_python", "description": "Group by region, sum revenue" },
      { "step_number": 3, "tool_to_use": "create_visualization", "description": "Bar chart by region" }
    ],
    "estimated_complexity": "simple"
  },
  "follow_up_questions": [
    { "question": "How has North region revenue trended over time?", "rationale": "North leads overall — understanding the trend reveals if this is growing or plateauing." },
    { "question": "Which product drives the most revenue in the North region?", "rationale": "Breaks down the aggregate to find the key contributor." }
  ],
  "visualizations": [{ "type": "bar", "title": "Revenue by Region", "data": {...} }],
  "execution_time": 4.21,
  "cache_hit": false
}
```

### Query with conversation context

Pass `parent_query_id` to continue a previous analysis — the planner receives the prior answer as context:

```bash
curl -X POST http://localhost:8000/api/v1/queries/datasets/{dataset_id}/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How has North region revenue trended over time?",
    "session_id": "abc123-...",
    "parent_query_id": "7c9e6679-..."
  }'
```

### Query with streaming (SSE)

```bash
curl -X POST http://localhost:8000/api/v1/queries/datasets/{dataset_id}/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Top 5 products by revenue"}' \
  --no-buffer
```

Events streamed:
```
event: node_start
data: {"node": "planner"}

event: plan_ready
data: {"plan": {"steps": [...], "estimated_complexity": "moderate"}}

event: node_start
data: {"node": "tool_executor"}

event: tool_call
data: {"tool": "execute_python", "input": "print(df.groupby(...))"}

event: tool_result
data: {"tool": "execute_python", "output": "Product A: 12,340\n..."}

event: complete
data: {"query_id": "...", "answer": "...", "follow_up_questions": [...]}
```

If the client disconnects, the graph runs to completion server-side. Retrieve the result with `GET /api/v1/queries/{query_id}`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async connection URL | Required |
| `REDIS_URL` | Redis connection URL | Required |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | Fallback model (relevance guard) | `gpt-4o-mini` |
| `PLANNER_MODEL` | Model for planner node | `gpt-4o` |
| `EXECUTOR_MODEL` | Model for tool executor loop | `gpt-4o-mini` |
| `SYNTHESIZER_MODEL` | Model for synthesizer + follow-ups | `gpt-4o` |
| `AGENT_MAX_ITERATIONS_SIMPLE` | Max tool iterations for simple queries | `8` |
| `AGENT_MAX_ITERATIONS_MODERATE` | Max tool iterations for moderate queries | `15` |
| `AGENT_MAX_ITERATIONS_COMPLEX` | Max tool iterations for complex queries | `25` |
| `SANDBOX_TIMEOUT` | Max seconds for Python sandbox execution | `30` |
| `SANDBOX_MAX_OUTPUT` | Max chars returned from sandbox | `3000` |
| `CACHE_TTL` | Redis cache TTL in seconds | `3600` |
| `ENABLE_CACHE` | Enable Redis query caching | `True` |
| `UPLOAD_DIR` | Directory for uploaded files | `./uploads` |
| `MAX_UPLOAD_SIZE` | Max upload size in bytes | `104857600` (100MB) |

## Project Structure

```
app/
├── agents/
│   ├── context.py          # Per-request AnalysisContext (replaces module globals)
│   ├── graph.py            # LangGraph StateGraph — build_graph(context)
│   ├── planner.py          # Planner node + prompt
│   ├── synthesizer.py      # Synthesizer + follow-up generator nodes
│   ├── state.py            # AgentState TypedDict
│   └── relevance_guard.py  # Query relevance validation
├── tools/
│   ├── dataset_tools.py    # build_load_dataset_tool(context)
│   ├── sandbox_tool.py     # build_execute_python_tool(context)
│   └── visualization_tools.py  # build_create_visualization_tool(context)
├── schemas/
│   ├── agent.py            # AnalysisPlan, AnalysisResult, FollowUpQuestions
│   └── query.py            # API request/response schemas
├── services/
│   ├── query_service.py    # Orchestrates graph execution + persistence
│   ├── dataset_service.py
│   ├── metadata_extractor.py
│   ├── cache_service.py
│   └── error_memory.py     # Learns from agent errors across sessions
├── models/dataset.py       # SQLAlchemy models (Dataset, Query)
├── api/v1/endpoints/
│   ├── datasets.py
│   └── queries.py          # /query and /query/stream endpoints
└── config.py
alembic/versions/
├── 001_initial.py
└── 002_v2_query_fields.py  # follow_up_questions, session_id, parent_query_id, ...
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web framework | FastAPI 0.109 (async) |
| Agent orchestration | LangGraph 0.2 |
| LLM integration | LangChain 0.3 + langchain-openai 0.2 |
| LLM provider | OpenAI (gpt-4o / gpt-4o-mini) |
| Database | PostgreSQL 15 + SQLAlchemy 2.0 async |
| Cache | Redis 7 |
| Data processing | Pandas 2.1, NumPy 1.26 |
| Visualizations | Plotly 5.18 |
| Migrations | Alembic 1.13 |

## Troubleshooting

**LangGraph import errors** — install dependencies in your virtual environment:
```bash
pip install -r requirements.txt
```

**Database connection error**
```bash
docker-compose logs postgres
docker-compose ps
```

**`alembic upgrade head` fails** — ensure `DATABASE_URL` in `.env` is correct and PostgreSQL is running.

**OpenAI errors** — verify `OPENAI_API_KEY` in `.env` and check your API quota.

## Roadmap

- [ ] Multi-dataset cross-join queries
- [ ] Persistent conversation sessions with full message history
- [ ] Scheduled recurring analyses
- [ ] Export results to PDF/Excel
- [ ] WebSocket endpoint for bidirectional follow-up conversation
