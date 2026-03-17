"""API endpoints for chat sessions — create, list, view history, and query within a session."""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db
from app.models.dataset import Query
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.session_service import SessionService
from app.services.query_service import QueryService
from app.schemas.session import (
    SessionCreateRequest,
    SessionQueryRequest,
    SessionResponse,
    SessionListResponse,
    SessionMessagesResponse,
)
from app.schemas.query import QueryResponse, QueryHistoryItem
from loguru import logger

router = APIRouter()


def _session_response(session, message_count: int) -> SessionResponse:
    return SessionResponse(
        session_id=session.id,
        dataset_id=session.dataset_id,
        title=session.title,
        message_count=message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _build_query_response(query: Query) -> QueryResponse:
    """Map a Query ORM object to a QueryResponse schema."""
    from app.schemas.query import VisualizationResponse, FollowUpQuestionResponse

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


# ── Session CRUD ─────────────────────────────────────────────────────────────


@router.post(
    "/datasets/{dataset_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chat session",
)
async def create_session(
    dataset_id: UUID,
    request: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat session tied to a dataset."""
    service = SessionService(db)
    session = await service.create_session(
        dataset_id=dataset_id, title=request.title, user_id=current_user.id
    )
    return _session_response(session, message_count=0)


@router.get(
    "/datasets/{dataset_id}/sessions",
    response_model=SessionListResponse,
    summary="List sessions for a dataset",
)
async def list_sessions(
    dataset_id: UUID,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all chat sessions for a dataset, most recent first."""
    service = SessionService(db)
    # Verify dataset ownership before listing sessions
    from app.services.dataset_service import DatasetService

    await DatasetService(db).get_dataset(dataset_id, user_id=current_user.id)
    sessions, total = await service.list_sessions(
        dataset_id=dataset_id, skip=skip, limit=limit
    )

    items = []
    for s in sessions:
        count = await service.get_message_count(s.id)
        items.append(_session_response(s, count))

    return SessionListResponse(sessions=items, total=total)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionMessagesResponse,
    summary="Get session with message history",
)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a session and its full message history in chronological order."""
    service = SessionService(db)
    session = await service.get_session(session_id, user_id=current_user.id)
    queries = await service.get_session_queries(session_id)

    messages = [
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

    return SessionMessagesResponse(
        session_id=session.id,
        dataset_id=session.dataset_id,
        title=session.title,
        messages=messages,
        total=len(messages),
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session",
)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a session. Existing queries are preserved but unlinked (session_id set to NULL)."""
    service = SessionService(db)
    await service.get_session(session_id, user_id=current_user.id)  # ownership check
    await service.delete_session(session_id)


# ── Session-scoped query endpoints ───────────────────────────────────────────


@router.post(
    "/sessions/{session_id}/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message in a session",
)
async def session_query(
    session_id: UUID,
    request: SessionQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execute a query within a chat session.

    The agent automatically receives summarized history from prior turns:
    - Last 2 turns: full question + answer
    - Earlier turns (up to 7 total): question + key findings only

    No need to pass parent_query_id — it is resolved automatically.
    """
    session_service = SessionService(db)
    query_service = QueryService(db)

    session = await session_service.get_session(session_id, user_id=current_user.id)
    prior_queries = await session_service.get_session_queries(session_id)

    # Build multi-turn context for the planner
    conversation_history = SessionService.build_conversation_context(prior_queries)
    logger.info(
        "Built conversation history for planner:\n{}",
        conversation_history or "No prior context",
    )

    # Most recent completed query becomes the parent (for lineage tracking)
    parent_query_id = prior_queries[-1].id if prior_queries else None

    query = await query_service.execute_query(
        dataset_id=session.dataset_id,
        question=request.question,
        session_id=session_id,
        parent_query_id=parent_query_id,
        conversation_history=conversation_history,
    )

    # Auto-title session from the first question
    if not prior_queries:
        await session_service.auto_update_title(session, request.question)

    return _build_query_response(query)


@router.post(
    "/sessions/{session_id}/query/stream",
    summary="Stream a message in a session",
    description="Same as /sessions/{id}/query but streams agent progress as SSE events",
)
async def session_query_stream(
    session_id: UUID,
    request: SessionQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stream agent progress as Server-Sent Events within a chat session.

    Events: node_start, plan_ready, tool_call, tool_result, complete, error
    """
    from app.services.metadata_extractor import MetadataExtractor
    from app.agents.relevance_guard import RelevanceGuard
    from app.agents.context import AnalysisContext
    from app.agents.graph import build_graph
    from app.agents.state import AgentState
    from app.services.error_memory import ErrorMemoryService
    from app.config import settings
    import time

    async def event_stream() -> AsyncGenerator[str, None]:
        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        start_time = time.time()

        try:
            session_service = SessionService(db)
            session = await session_service.get_session(
                session_id, user_id=current_user.id
            )
            prior_queries = await session_service.get_session_queries(session_id)

            conversation_history = SessionService.build_conversation_context(
                prior_queries
            )
            parent_query_id = prior_queries[-1].id if prior_queries else None

            from app.services.dataset_service import DatasetService

            dataset_service = DatasetService(db)
            metadata_extractor = MetadataExtractor()
            relevance_guard = RelevanceGuard()
            error_memory = ErrorMemoryService(data_dir=settings.DATA_DIR)

            dataset = await dataset_service.get_dataset(session.dataset_id)

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
                "conversation_history": conversation_history,
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
            query = Query(
                dataset_id=session.dataset_id,
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
                session_id=session_id,
                parent_query_id=parent_query_id,
                token_usage=final_state.get("token_usage"),
            )
            db.add(query)
            await db.commit()
            await db.refresh(query)

            # Auto-title session from the first question
            if not prior_queries:
                await session_service.auto_update_title(session, request.question)

            response = _build_query_response(query)
            yield sse("complete", response.model_dump(mode="json"))

        except Exception as e:
            yield sse("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
