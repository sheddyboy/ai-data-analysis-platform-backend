"""API endpoints for querying datasets — v2 with streaming and follow-up support."""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db
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


def _build_query_response(query) -> QueryResponse:
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
    )


@router.post(
    "/datasets/{dataset_id}/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query a dataset",
    description="Ask a natural language question about a dataset",
)
async def query_dataset(
    dataset_id: UUID,
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
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
    service = QueryService(db)
    query = await service.execute_query(
        dataset_id=dataset_id,
        question=request.question,
        session_id=request.session_id,
        parent_query_id=request.parent_query_id,
    )
    return _build_query_response(query)


@router.post(
    "/datasets/{dataset_id}/query/stream",
    summary="Query a dataset with streaming",
    description="Same as /query but streams agent progress as SSE events",
)
async def query_dataset_stream(
    dataset_id: UUID,
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
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
    from app.services.dataset_service import DatasetService
    from app.services.metadata_extractor import MetadataExtractor
    from app.agents.relevance_guard import RelevanceGuard
    from app.agents.context import AnalysisContext
    from app.agents.graph import build_graph
    from app.agents.state import AgentState
    from app.services.error_memory import ErrorMemoryService
    from app.models.dataset import Query
    from app.config import settings
    import time

    async def event_stream() -> AsyncGenerator[str, None]:
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        start_time = time.time()

        try:
            dataset_service = DatasetService(db)
            metadata_extractor = MetadataExtractor()
            relevance_guard = RelevanceGuard()
            error_memory = ErrorMemoryService(data_dir=settings.DATA_DIR)

            dataset = await dataset_service.get_dataset(dataset_id)

            await relevance_guard.validate_query(
                question=request.question,
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

            error_hints = error_memory.get_hints(request.question)
            context = AnalysisContext(df=df, metadata=metadata)
            graph = build_graph(context)

            initial_state: AgentState = {
                "question": request.question,
                "dataset_metadata": metadata,
                "error_hints": error_hints,
                "parent_context": None,
                "analysis_plan": None,
                "messages": [],
                "tool_outputs": [],
                "visualizations": [],
                "answer": None,
                "key_findings": [],
                "data_quality_notes": [],
                "confidence": None,
                "follow_up_questions": None,
                "agent_steps": [],
            }

            # Stream graph events
            final_state: AgentState = initial_state
            async for event in graph.astream_events(initial_state, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")

                if kind == "on_chain_start" and name in ("planner", "tool_executor", "synthesizer", "follow_up_gen"):
                    yield sse("node_start", {"node": name})

                elif kind == "on_chain_end" and name == "planner":
                    output = event.get("data", {}).get("output", {})
                    plan = output.get("analysis_plan")
                    if plan:
                        yield sse("plan_ready", {"plan": plan})

                elif kind == "on_chat_model_stream":
                    pass  # skip token-level streaming for now

                elif kind == "on_tool_start":
                    yield sse("tool_call", {
                        "tool": event.get("name", ""),
                        "input": str(event.get("data", {}).get("input", ""))[:200],
                    })

                elif kind == "on_tool_end":
                    yield sse("tool_result", {
                        "tool": event.get("name", ""),
                        "output": str(event.get("data", {}).get("output", ""))[:300],
                    })

                elif kind == "on_chain_end" and name == "LangGraph":
                    # Final state from the top-level graph
                    final_state = event.get("data", {}).get("output", initial_state)

            # Persist result
            execution_time = time.time() - start_time
            query = Query(
                dataset_id=dataset_id,
                question=request.question,
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
                session_id=request.session_id,
                parent_query_id=request.parent_query_id,
            )
            db.add(query)
            await db.commit()
            await db.refresh(query)

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
):
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
):
    service = QueryService(db)
    query = await service.get_query(query_id)
    return _build_query_response(query)
