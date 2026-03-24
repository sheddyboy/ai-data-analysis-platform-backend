"""API endpoints for querying datasets — v2 with streaming and follow-up support."""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.limiter import limiter
from loguru import logger
from app.database import get_db
from app.models.dataset import Query
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.dataset_service import DatasetService
from app.services.query_service import QueryService
from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    QueryHistoryResponse,
    QueryHistoryItem,
    VisualizationResponse,
    FollowUpQuestionResponse,
)

router = APIRouter()


def _build_query_response(query: Query) -> QueryResponse:
    """Map a Query ORM object to a QueryResponse schema."""
    visualizations = []
    if query.visualizations:
        for viz in query.visualizations:
            visualizations.append(
                VisualizationResponse(
                    type=viz.get("type", ""),
                    title=viz.get("title", ""),
                    data=viz.get("data", []),
                    layout=viz.get("layout"),
                )
            )

    follow_up_questions = []
    if query.follow_up_questions:
        for fq in query.follow_up_questions:
            follow_up_questions.append(
                FollowUpQuestionResponse(
                    question=fq.get("question", ""),
                    rationale=fq.get("rationale", ""),
                )
            )

    return QueryResponse(
        query_id=query.id,
        dataset_id=query.dataset_id,
        question=query.question,
        answer=query.answer,
        key_findings=query.key_findings or [],
        data_quality_notes=query.data_quality_notes or [],
        confidence=query.confidence,
        analysis_plan=query.analysis_plan,
        follow_up_questions=follow_up_questions,
        visualizations=visualizations,
        insights=None,
        statistics=query.statistics,
        execution_time=query.execution_time,
        cache_hit=query.cache_hit == "true",
        status=query.status,
        created_at=query.created_at,
        session_id=query.session_id,
        parent_query_id=query.parent_query_id,
        token_usage=query.token_usage,
    )


@router.post(
    "/datasets/{dataset_id}/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query a dataset",
    description="Ask a natural language question about a dataset",
)
@limiter.limit("20/minute")
async def query_dataset(
    request: Request,
    dataset_id: UUID,
    body: QueryRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Query a dataset with a natural language question.

    The v2 agent:
    1. Creates a structured analysis plan (planner node)
    2. Executes tools (load_dataset, execute_python, create_visualization)
    3. Synthesizes a structured answer with key findings and confidence
    4. Generates 3–5 follow-up questions

    Pass `parent_query_id` to continue a previous conversation with full context.
    """
    from app.services.quota_service import QuotaService

    await DatasetService(db).get_dataset(dataset_id, user_id=current_user.id)
    service = QueryService(db)
    query = await service.execute_query(
        dataset_id=dataset_id,
        question=body.question,
        current_user=current_user,
        session_id=body.session_id,
        parent_query_id=body.parent_query_id,
    )
    result = _build_query_response(query)

    # Add quota headers
    quota_info = await QuotaService(db).get_quota_info(current_user.id)
    response.headers["X-Quota-Remaining"] = str(quota_info.remaining)
    response.headers["X-Quota-Limit"] = str(quota_info.monthly_limit)
    response.headers["X-Quota-Reset"] = quota_info.period_end.isoformat()

    return result


@router.post(
    "/datasets/{dataset_id}/query/stream",
    summary="Query a dataset with streaming",
    description="Same as /query but streams agent progress as SSE events",
)
@limiter.limit("20/minute")
async def query_dataset_stream(
    request: Request,
    dataset_id: UUID,
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream agent progress as Server-Sent Events.

    Events:
    - `node_start`   — a graph node has started
    - `plan_ready`   — planner produced an analysis plan (data: serialized plan)
    - `tool_call`    — the executor called a tool
    - `tool_result`  — a tool returned output
    - `complete`     — analysis finished (data: full QueryResponse JSON)
    - `error`        — an error occurred

    The graph always runs to completion server-side. If the client disconnects,
    retrieve the result later via GET /{query_id}.
    """
    from app.services.metadata_extractor import MetadataExtractor
    from app.agents.relevance_guard import RelevanceGuard
    from app.agents.context import AnalysisContext
    from app.agents.graph import build_graph
    from app.agents.state import AgentState
    from app.services.error_memory import ErrorMemoryService
    from app.services.quota_service import QuotaService
    from app.config import settings
    import time

    # Quota pre-check before starting the SSE stream (allows proper HTTP 429)
    await QuotaService(db).check_quota(current_user.id)

    async def event_stream() -> AsyncGenerator[str, None]:
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        start_time = time.time()

        try:
            dataset_service = DatasetService(db)
            metadata_extractor = MetadataExtractor()
            relevance_guard = RelevanceGuard()
            error_memory = ErrorMemoryService(data_dir=settings.DATA_DIR)

            dataset = await dataset_service.get_dataset(
                dataset_id, user_id=current_user.id
            )

            await relevance_guard.validate_query(
                question=body.question,
                column_names=dataset.columns,
                column_types=dataset.column_types,
                sample_data=dataset.sample_data or [],
            )

            df = await metadata_extractor.load_dataset(dataset.file_path)
            metadata = {
                "columns": dataset.columns,
                "column_types": dataset.column_types,
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "summary_statistics": dataset.summary_statistics,
            }

            error_hints = error_memory.get_hints(body.question)
            context = AnalysisContext(df=df, metadata=metadata)
            graph = build_graph(context)

            initial_state: AgentState = {
                "question": body.question,
                "dataset_metadata": metadata,
                "error_hints": error_hints,
                "conversation_history": None,
                "analysis_plan": None,
                "messages": [],
                "tool_outputs": [],
                "current_step_index": 0,
                "visualizations": [],
                "answer": None,
                "key_findings": [],
                "data_quality_notes": [],
                "confidence": None,
                "follow_up_questions": None,
                "agent_steps": [],
                "token_usage": {},
            }

            # Stream graph events
            final_state: AgentState = initial_state
            _prev_step_idx: int = 0
            _plan_steps: list[dict] = []
            async for event in graph.astream_events(initial_state, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")

                if kind == "on_chain_start" and name in (
                    "planner",
                    "tool_executor",
                    "synthesizer",
                    "follow_up_gen",
                ):
                    yield sse("node_start", {"node": name})

                elif kind == "on_chain_end" and name == "planner":
                    output = event.get("data", {}).get("output", {})
                    plan = output.get("analysis_plan")
                    if plan:
                        _plan_steps = plan.get("steps", [])
                        yield sse("plan_ready", {"plan": plan})

                elif kind == "on_chain_end" and name == "tool_executor":
                    output = event.get("data", {}).get("output", {})
                    new_idx = output.get("current_step_index", _prev_step_idx)
                    if new_idx > _prev_step_idx and _plan_steps:
                        completed_step = _plan_steps[_prev_step_idx]
                        yield sse(
                            "step_complete",
                            {
                                "step_number": completed_step.get("step_number"),
                                "description": completed_step.get("description"),
                                "tool": completed_step.get("tool_to_use"),
                                "steps_completed": new_idx,
                                "total_steps": len(_plan_steps),
                            },
                        )
                    _prev_step_idx = new_idx

                elif kind == "on_chat_model_stream":
                    pass  # skip token-level streaming for now

                elif kind == "on_tool_start":
                    yield sse(
                        "tool_call",
                        {
                            "tool": event.get("name", ""),
                            "input": str(event.get("data", {}).get("input", ""))[:200],
                        },
                    )

                elif kind == "on_tool_end":
                    yield sse(
                        "tool_result",
                        {
                            "tool": event.get("name", ""),
                            "output": str(event.get("data", {}).get("output", ""))[
                                :300
                            ],
                        },
                    )

                elif kind == "on_chain_end" and name == "LangGraph":
                    # Final state from the top-level graph
                    final_state = event.get("data", {}).get("output", initial_state)

            # Flush step_complete for the last step — on_chain_end fires before the
            # tool runs, so the final step is always one invocation behind and missed.
            for i in range(_prev_step_idx, len(_plan_steps)):
                step = _plan_steps[i]
                yield sse(
                    "step_complete",
                    {
                        "step_number": step.get("step_number"),
                        "description": step.get("description"),
                        "tool": step.get("tool_to_use"),
                        "steps_completed": i + 1,
                        "total_steps": len(_plan_steps),
                    },
                )

            # Persist result
            execution_time = time.time() - start_time
            raw_usage = final_state.get("token_usage") or {}
            logger.debug("Final token usage: {}", raw_usage)
            if raw_usage:
                prompt_tokens = raw_usage.get("prompt", 0)
                completion_tokens = raw_usage.get("completion", 0)
                # gpt-4.1-mini: $0.40/1M input, $1.60/1M output
                cost = (prompt_tokens * 0.40 + completion_tokens * 1.60) / 1_000_000
                token_usage = {**raw_usage, "estimated_cost_usd": round(cost, 6)}
            else:
                token_usage = None

            query = Query(
                dataset_id=dataset_id,
                question=body.question,
                answer=final_state.get("answer"),
                visualizations=final_state.get("visualizations") or [],
                insights=None,
                statistics=None,
                key_findings=final_state.get("key_findings") or [],
                data_quality_notes=final_state.get("data_quality_notes") or [],
                confidence=final_state.get("confidence"),
                analysis_plan=final_state.get("analysis_plan"),
                follow_up_questions=final_state.get("follow_up_questions") or [],
                agent_steps=final_state.get("agent_steps"),
                execution_time=execution_time,
                status="completed",
                cache_hit="false",
                session_id=body.session_id,
                parent_query_id=body.parent_query_id,
                token_usage=token_usage,
            )
            db.add(query)
            await db.commit()
            await db.refresh(query)

            # Deduct actual tokens from quota
            if token_usage:
                total_tokens = token_usage.get("total", 0)
                if total_tokens > 0:
                    await QuotaService(db).deduct_tokens(current_user.id, total_tokens)

            # Emit complete event with full response
            response = _build_query_response(query)
            yield sse("complete", response.model_dump(mode="json"))

        except Exception as e:
            yield sse("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/datasets/{dataset_id}/queries",
    response_model=QueryHistoryResponse,
    summary="Get query history",
    description="Retrieve all queries for a dataset",
)
async def get_query_history(
    dataset_id: UUID,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await DatasetService(db).get_dataset(dataset_id, user_id=current_user.id)
    service = QueryService(db)
    queries, total = await service.get_dataset_queries(
        dataset_id=dataset_id, skip=skip, limit=limit
    )

    items = [
        QueryHistoryItem(
            query_id=q.id,
            question=q.question,
            answer=q.answer,
            status=q.status,
            confidence=q.confidence,
            execution_time=q.execution_time,
            created_at=q.created_at,
            session_id=q.session_id,
        )
        for q in queries
    ]

    return QueryHistoryResponse(queries=items, total=total)


@router.get(
    "/{query_id}",
    response_model=QueryResponse,
    summary="Get query result",
    description="Retrieve a specific query result by ID",
)
async def get_query_result(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = QueryService(db)
    query = await service.get_query(query_id, user_id=current_user.id)
    return _build_query_response(query)
