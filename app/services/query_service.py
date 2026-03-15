"""Service for processing queries against datasets using the v2 LangGraph agent."""

import time
from uuid import UUID
from typing import Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.dataset import Query
from app.services.dataset_service import DatasetService
from app.services.metadata_extractor import MetadataExtractor
from app.services.cache_service import cache_service
from app.services.error_memory import ErrorMemoryService
from app.agents.relevance_guard import RelevanceGuard
from app.agents.context import AnalysisContext
from app.agents.graph import build_graph
from app.agents.state import AgentState
from app.config import settings


class QueryService:
    """Service for managing query operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dataset_service = DatasetService(db)
        self.metadata_extractor = MetadataExtractor()
        self.relevance_guard = RelevanceGuard()
        self.error_memory = ErrorMemoryService(data_dir=settings.DATA_DIR)

    async def execute_query(
        self,
        dataset_id: UUID,
        question: str,
        session_id: Optional[UUID] = None,
        parent_query_id: Optional[UUID] = None,
    ) -> Query:
        """
        Execute a query against a dataset using the v2 LangGraph agent.

        Raises:
            DatasetNotFoundError: If dataset not found
            IrrelevantQuestionError: If question is not relevant
            AgentExecutionError: If agent execution fails
        """
        from app.utils.error_handlers import AgentExecutionError

        start_time = time.time()

        # Get dataset
        dataset = await self.dataset_service.get_dataset(dataset_id)

        # Check cache (skip for follow-up queries to respect conversation context)
        if not parent_query_id:
            cached_result = await cache_service.get(str(dataset_id), question)
            if cached_result:
                query = Query(
                    dataset_id=dataset_id,
                    question=question,
                    answer=cached_result.get("answer"),
                    visualizations=cached_result.get("visualizations"),
                    insights=cached_result.get("insights"),
                    statistics=cached_result.get("statistics"),
                    key_findings=cached_result.get("key_findings", []),
                    data_quality_notes=cached_result.get("data_quality_notes", []),
                    confidence=cached_result.get("confidence"),
                    analysis_plan=cached_result.get("analysis_plan"),
                    follow_up_questions=cached_result.get("follow_up_questions", []),
                    agent_steps=cached_result.get("agent_steps"),
                    execution_time=time.time() - start_time,
                    status="completed",
                    cache_hit="true",
                    session_id=session_id,
                )
                self.db.add(query)
                await self.db.commit()
                await self.db.refresh(query)
                return query

        # Validate query relevance
        await self.relevance_guard.validate_query(
            question=question,
            column_names=dataset.columns,
            column_types=dataset.column_types,
            sample_data=dataset.sample_data or [],
        )

        # Load dataset
        df = await self.metadata_extractor.load_dataset(dataset.file_path)

        metadata = {
            "columns": dataset.columns,
            "column_types": dataset.column_types,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
            "summary_statistics": dataset.summary_statistics,
        }

        # Resolve parent context for conversation threading
        parent_context: Optional[str] = None
        if parent_query_id:
            parent_query = await self._get_query_or_none(parent_query_id)
            if parent_query and parent_query.answer:
                parent_context = (
                    f"Previous question: {parent_query.question}\n"
                    f"Previous answer summary: {parent_query.answer[:400]}"
                )

        # Build error hints
        error_hints = self.error_memory.get_hints(question)

        # Build request-scoped context and graph
        context = AnalysisContext(df=df, metadata=metadata)
        graph = build_graph(context)

        # Build initial state
        initial_state: AgentState = {
            "question": question,
            "dataset_metadata": metadata,
            "error_hints": error_hints,
            "parent_context": parent_context,
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

        try:
            final_state = cast(AgentState, await graph.ainvoke(initial_state))
        except Exception as e:
            raise AgentExecutionError(f"Agent execution failed: {str(e)}")

        # Auto-record error patterns from tool steps
        tool_steps = [
            s for s in final_state.get("agent_steps", [])
            if s.get("node") == "tool_executor"
        ]
        self.error_memory.scan_steps_and_record(tool_steps)

        execution_time = time.time() - start_time

        # Persist result
        query = Query(
            dataset_id=dataset_id,
            question=question,
            answer=final_state.get("answer"),
            visualizations=final_state.get("visualizations") or [],
            insights=None,  # v2 uses key_findings instead of legacy insights object
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
        )

        self.db.add(query)
        await self.db.commit()
        await self.db.refresh(query)

        # Cache (only non-follow-up queries)
        if not parent_query_id:
            cache_data = {
                "answer": query.answer,
                "visualizations": query.visualizations,
                "insights": query.insights,
                "statistics": query.statistics,
                "key_findings": query.key_findings,
                "data_quality_notes": query.data_quality_notes,
                "confidence": query.confidence,
                "analysis_plan": query.analysis_plan,
                "follow_up_questions": query.follow_up_questions,
                "agent_steps": query.agent_steps,
            }
            await cache_service.set(str(dataset_id), question, cache_data)

        return query

    async def get_query(self, query_id: UUID) -> Query:
        result = await self.db.execute(select(Query).where(Query.id == query_id))
        query = result.scalar_one_or_none()
        if not query:
            from app.utils.error_handlers import DatasetNotFoundError
            raise DatasetNotFoundError(str(query_id))
        return query

    async def get_dataset_queries(
        self, dataset_id: UUID, skip: int = 0, limit: int = 50
    ) -> tuple[list[Query], int]:
        from sqlalchemy import func

        count_result = await self.db.execute(
            select(func.count(Query.id)).where(Query.dataset_id == dataset_id)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(Query)
            .where(Query.dataset_id == dataset_id)
            .order_by(Query.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        queries = result.scalars().all()
        return list(queries), total

    async def _get_query_or_none(self, query_id: UUID) -> Optional[Query]:
        result = await self.db.execute(select(Query).where(Query.id == query_id))
        return result.scalar_one_or_none()
