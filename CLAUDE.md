# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Docker (recommended)
docker-compose up --build

# Local development
pip install -r requirements.txt
uvicorn app.main:app --reload

# Database migrations
alembic upgrade head                          # apply all migrations
alembic revision --autogenerate -m "desc"     # create new migration

# Formatting & linting
black .
ruff check .
ruff check --fix .
```

Requires PostgreSQL 15+, Redis 7+, and an `OPENAI_API_KEY` in `.env` (copy from `.env.example`). No test suite exists yet (`tests/` is empty).

## Architecture

**Python 3.11 / FastAPI async application** that lets users upload datasets (CSV/Excel) and query them with natural language. Queries are processed by a LangChain ReAct agent backed by OpenAI.

### Request Flow

1. **Upload**: `POST /api/v1/datasets/upload` → `DatasetService` saves file, extracts metadata via `MetadataExtractor`, stores in PostgreSQL
2. **Query**: `POST /api/v1/queries/datasets/{id}/query` → `QueryService` orchestrates:
   - Check Redis cache (`CacheService`)
   - `RelevanceGuard` — uses OpenAI directly (not LangChain) to validate query relevance to the dataset columns
   - `DataAnalystAgent` — LangChain ReAct agent with 6 tools, executes analysis
   - Result persisted to `Query` table and cached in Redis

### Key Layers

- **API** (`app/api/v1/endpoints/`): FastAPI routers for `datasets` and `queries`, all under `/api/v1` prefix
- **Services** (`app/services/`): Business logic — `DatasetService`, `QueryService`, `MetadataExtractor`, `CacheService` (singleton `cache_service`)
- **Agents** (`app/agents/`): `RelevanceGuard` (OpenAI direct) and `DataAnalystAgent` (LangChain ReAct)
- **Tools** (`app/tools/`): LangChain tools used by the agent — `load_dataset`, `analyze_data`, `get_statistics`, `filter_data`, `create_visualization`, `generate_insights`. Tools use module-level context objects (`dataset_context`, `viz_storage`, `insight_storage`) for state sharing
- **Models** (`app/models/dataset.py`): SQLAlchemy models — `Dataset` and `Query` with UUID primary keys, JSON columns for metadata
- **Config** (`app/config.py`): Pydantic `BaseSettings` loading from `.env`, accessed via global `settings` singleton

### Database

- Async SQLAlchemy 2.0 with `asyncpg` driver (`postgresql+asyncpg://` URLs)
- Alembic for migrations (async-configured in `alembic/env.py`, reads DB URL from `settings`)
- `get_db()` dependency yields `AsyncSession`

### Error Handling

Custom exceptions in `app/utils/error_handlers.py` registered as FastAPI exception handlers: `IrrelevantQuestionError` (400), `DatasetNotFoundError` (404), `FileProcessingError` (400), `AgentExecutionError` (500).

## Conventions

- All database operations are async (use `await` with SQLAlchemy)
- Services are instantiated per-request with `db: AsyncSession` injected
- The `CacheService` is a singleton (`cache_service`) connected during app lifespan
- Agent tools share state through module-level storage objects, not return values
- Uploaded files go to the `uploads/` directory (configurable via `UPLOAD_DIR`)
