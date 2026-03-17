# AI Data Analysis & Insight Agent Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-blueviolet.svg)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-grade backend that lets users interact with their datasets using natural language. Upload a CSV or Excel file, ask questions in plain English, and get back structured answers, auto-generated charts, key findings, and suggested follow-up questions — all powered by a multi-node LangGraph agent.

## What's new in v4

| Feature | v3 | v4 |
|---------|----|----|
| Authentication | No auth — all data globally accessible | JWT-based auth (`POST /auth/register`, `POST /auth/login`). Every dataset, session, and query is scoped to its owner |
| Data isolation | Any caller could read or delete any dataset/session | All list, get, and delete endpoints enforce user ownership — 403 on unauthorized access |
| Token & cost tracking | No visibility into LLM usage | Prompt/completion tokens and estimated cost accumulated across planner → synthesizer → follow_up nodes, stored on every `Query` as `token_usage: {prompt, completion, total, estimated_cost_usd}` |
| Rate limiting | Unlimited queries per user | `slowapi` enforces 20 queries/minute per IP on all query endpoints — configurable via `RATE_LIMIT_QUERIES_PER_MINUTE` |
| Health endpoint | No observability endpoint | `GET /health` — checks PostgreSQL and Redis connectivity, returns per-service status |
| Admin stats | No stats | `GET /admin/stats` — query count, average execution time, cache hit rate |
| Test suite | Empty `tests/` directory | Integration tests for auth, dataset upload/scoping, session ownership, and health endpoint using `pytest-asyncio` + SQLite in-memory DB |

**Commits:** _(v4 implementation)_

## What's new in v3

| Feature | v2 | v3 |
|---------|----|----|
| Conversation sessions | `session_id` stored on queries but no dedicated model | Persistent `Session` model with full CRUD — queries belong to a session |
| Multi-turn context | Planner received only the immediate parent query answer | `SessionService` builds a rolling conversation history (up to 7 turns) passed to **both** planner and synthesizer — last 2 turns include the full answer, earlier turns include question + key findings only (to control token usage) |
| Follow-up accuracy | Synthesizer answered without prior context, causing wrong answers on follow-ups like "list their names" | Synthesizer receives full conversation history — follow-up questions resolve correctly |
| Session API | No session endpoints | `POST /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/query`, `POST /sessions/{id}/query/stream` |
| Session auto-title | — | Session title is automatically set from the first question if not provided at creation time |
| Streaming in sessions | No streaming support in session queries | `POST /sessions/{id}/query/stream` — full SSE stream within a session, conversation history included |

**Commits:** [`9a692b1`](../../commit/9a692b1) feat(sessions) · [`d5ab861`](../../commit/d5ab861) refactor(state) · [`02a4b61`](../../commit/02a4b61) fix(synthesizer) · [`1998ee7`](../../commit/1998ee7) feat(streaming)

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
| **planner** | gpt-4o | Reads dataset schema + question (plus any prior error hints or parent query context), produces a structured `AnalysisPlan` (ordered steps, complexity, needs_visualization). No tool access — pure reasoning. |
| **tool_executor** | gpt-4o-mini | Drives the tool-calling loop step-by-step. Each turn injects a step-specific `HumanMessage` and enforces the correct tool via OpenAI `tool_choice` — the LLM physically cannot call a different tool. `load_dataset` is always forced first as a pre-step, then each plan step in order, and finally `finish_analysis` once all steps succeed. On tool errors the step index is not advanced, triggering a retry of the same step. |
| **tools** | — | LangGraph `ToolNode` dispatches tool calls and returns `ToolMessage` results. |
| **synthesizer** | gpt-4o | Reads the full tool transcript **and conversation history** (if in a session) and produces a structured `AnalysisResult` (answer, key_findings, confidence). Receiving prior context is what enables correct answers to follow-up questions like "list their names". |
| **follow_up_gen** | gpt-4o | Generates 3–5 `FollowUpQuestion` objects with rationale for each. |

#### tool_executor step lifecycle

```
turn 1:  force load_dataset  → load the dataset into context
turn 2…N: for each plan step → force the tool named in that step (execute_python / create_visualization)
            └─ on error: retry the same step (step index not advanced)
            └─ on success: advance to next step
turn N+1: all steps done → force finish_analysis → route to synthesizer
```

Max iterations are capped per complexity level (`AGENT_MAX_ITERATIONS_SIMPLE/MODERATE/COMPLEX`). If the cap is reached before `finish_analysis`, the graph routes directly to the synthesizer with whatever results are available.

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

### Authentication

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "mypassword"}'
# → {"user_id": "...", "email": "user@example.com", "is_active": true, "created_at": "..."}

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "mypassword"}'
# → {"access_token": "eyJ...", "token_type": "bearer"}
```

Pass the token in the `Authorization` header for all subsequent requests:
```bash
-H "Authorization: Bearer eyJ..."
```

### Upload a dataset

```bash
curl -X POST http://localhost:8000/api/v1/datasets/upload \
  -H "Authorization: Bearer eyJ..." \
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
  "cache_hit": false,
  "token_usage": {
    "prompt": 3820,
    "completion": 512,
    "total": 4332,
    "estimated_cost_usd": 0.014655
  }
}
```

### Sessions (multi-turn conversation)

Create a session, then send queries through it — the full conversation history is automatically passed to both the planner and synthesizer on every turn.

```bash
# 1. Create a session
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"dataset_id": "550e8400-...", "title": "Sales analysis"}'
# → {"session_id": "abc123-...", ...}

# 2. Ask a question
curl -X POST http://localhost:8000/api/v1/sessions/abc123-.../query \
  -H "Content-Type: application/json" \
  -d '{"question": "Top 4 artists in Brazil"}'

# 3. Follow up — the system knows "their" refers to the artists from turn 1
curl -X POST http://localhost:8000/api/v1/sessions/abc123-.../query \
  -H "Content-Type: application/json" \
  -d '{"question": "List their names"}'

# 4. Stream a session query (same SSE events as /query/stream, with full conversation context)
curl -X POST http://localhost:8000/api/v1/sessions/abc123-.../query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Show a chart of their monthly sales"}' \
  --no-buffer
```

> **Auto-title:** If you omit `title` when creating a session, the session is automatically named after the first question asked.

### Query with parent context (legacy)

Pass `parent_query_id` directly on the `/query` endpoint for single-hop context without a session:

```bash
curl -X POST http://localhost:8000/api/v1/queries/datasets/{dataset_id}/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How has North region revenue trended over time?",
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

event: step_complete
data: {"step_number": 2, "description": "Group by product, sum revenue", "tool": "execute_python", "steps_completed": 2, "total_steps": 3}

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
| `JWT_SECRET` | Secret key for signing JWTs | `change-me-in-production` |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `JWT_EXPIRE_MINUTES` | JWT token lifetime in minutes | `10080` (7 days) |
| `RATE_LIMIT_QUERIES_PER_MINUTE` | Max query requests per IP per minute | `20` |

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
│   ├── session_service.py  # Session CRUD + conversation history builder
│   ├── dataset_service.py
│   ├── metadata_extractor.py
│   ├── cache_service.py
│   └── error_memory.py     # Learns from agent errors across sessions
├── models/
│   ├── dataset.py          # SQLAlchemy models (Dataset, Query) — user_id FK + token_usage
│   ├── session.py          # Session model
│   └── user.py             # User model
├── schemas/
│   ├── agent.py            # AnalysisPlan, AnalysisResult, FollowUpQuestions
│   ├── auth.py             # RegisterRequest, LoginRequest, TokenResponse, UserResponse
│   ├── query.py            # API request/response schemas (includes token_usage)
│   └── session.py          # Session request/response schemas
├── services/
│   ├── auth_service.py     # JWT creation, password hashing, get_current_user dependency
│   └── ...
├── core/
│   └── limiter.py          # Shared slowapi Limiter instance
├── api/v1/endpoints/
│   ├── auth.py             # /auth/register, /auth/login, /auth/me
│   ├── datasets.py
│   ├── queries.py          # /query and /query/stream endpoints (rate limited)
│   └── sessions.py         # /sessions CRUD + /sessions/{id}/query
└── config.py
alembic/versions/
├── 001_initial.py
├── 002_v2_query_fields.py  # follow_up_questions, session_id, parent_query_id, ...
├── 003_v3_sessions.py      # sessions table + session FK on queries
├── 004_v4_users.py         # users table + user_id FK on datasets + sessions
└── 005_v4_token_usage.py   # token_usage JSON column on queries
tests/
├── conftest.py             # SQLite in-memory DB fixtures, auth_headers
├── test_auth.py            # register, login, /me, duplicate email
├── test_datasets.py        # upload, list (user-scoped), ownership 403, delete
└── test_sessions.py        # create, list, ownership 403, delete, health
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
| Auth | python-jose 3.3 + passlib[bcrypt] 1.7 |
| Rate limiting | slowapi 0.1.9 |
| Testing | pytest 8.0 + pytest-asyncio 0.23 + httpx 0.26 |

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

- [x] JWT authentication + per-user data isolation
- [x] Token usage + cost tracking per query
- [x] Rate limiting (slowapi)
- [x] Health + admin observability endpoints
- [x] Integration test suite
- [x] Persistent conversation sessions with full message history
- [ ] Multi-dataset cross-join queries
- [ ] Scheduled recurring analyses
- [ ] Export results to PDF/Excel
- [ ] WebSocket endpoint for bidirectional follow-up conversation
