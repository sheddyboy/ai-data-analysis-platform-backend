"""Service for processing queries against datasets."""

import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import Dict, Any

from app.models.dataset import Query
from app.services.dataset_service import DatasetService
from app.services.metadata_extractor import MetadataExtractor
from app.services.cache_service import cache_service
from app.agents.relevance_guard import RelevanceGuard
from app.agents.data_analyst_agent import DataAnalystAgent


class QueryService:
    """Service for managing query operations."""
    
    def __init__(self, db: AsyncSession):
        """
        Initialize query service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.dataset_service = DatasetService(db)
        self.metadata_extractor = MetadataExtractor()
        self.relevance_guard = RelevanceGuard()
        self.agent = DataAnalystAgent()
    
    async def execute_query(
        self,
        dataset_id: UUID,
        question: str
    ) -> Query:
        """
        Execute a query against a dataset.
        
        Args:
            dataset_id: Dataset UUID
            question: User's question
            
        Returns:
            Query model with results
            
        Raises:
            DatasetNotFoundError: If dataset not found
            IrrelevantQuestionError: If question is not relevant
            AgentExecutionError: If agent execution fails
        """
        start_time = time.time()
        
        # Get dataset
        dataset = await self.dataset_service.get_dataset(dataset_id)
        
        # Check cache first
        cached_result = await cache_service.get(str(dataset_id), question)
        
        if cached_result:
            # Return cached result
            query = Query(
                dataset_id=dataset_id,
                question=question,
                answer=cached_result.get("answer"),
                visualizations=cached_result.get("visualizations"),
                insights=cached_result.get("insights"),
                statistics=cached_result.get("statistics"),
                execution_time=time.time() - start_time,
                status="completed",
                cache_hit="true",
                agent_steps=cached_result.get("agent_steps"),
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
            sample_data=dataset.sample_data or []
        )
        
        # Load dataset
        df = await self.metadata_extractor.load_dataset(dataset.file_path)
        
        # Prepare metadata for agent
        metadata = {
            "columns": dataset.columns,
            "column_types": dataset.column_types,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
        }
        
        # Execute agent analysis
        agent_result = await self.agent.analyze(
            question=question,
            df=df,
            metadata=metadata
        )
        
        # Create query record
        query = Query(
            dataset_id=dataset_id,
            question=question,
            answer=agent_result.get("answer"),
            visualizations=agent_result.get("visualizations"),
            insights=agent_result.get("insights"),
            statistics=None,  # Can be populated if needed
            execution_time=time.time() - start_time,
            status="completed",
            cache_hit="false",
            agent_steps=agent_result.get("agent_steps"),
        )
        
        self.db.add(query)
        await self.db.commit()
        await self.db.refresh(query)
        
        # Cache the result
        cache_data = {
            "answer": query.answer,
            "visualizations": query.visualizations,
            "insights": query.insights,
            "statistics": query.statistics,
            "agent_steps": query.agent_steps,
        }
        await cache_service.set(str(dataset_id), question, cache_data)
        
        return query
    
    async def get_query(self, query_id: UUID) -> Query:
        """
        Get a query by ID.
        
        Args:
            query_id: Query UUID
            
        Returns:
            Query model
        """
        result = await self.db.execute(
            select(Query).where(Query.id == query_id)
        )
        query = result.scalar_one_or_none()
        
        if not query:
            from app.utils.error_handlers import DatasetNotFoundError
            raise DatasetNotFoundError(str(query_id))
        
        return query
    
    async def get_dataset_queries(
        self,
        dataset_id: UUID,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[list[Query], int]:
        """
        Get all queries for a dataset.
        
        Args:
            dataset_id: Dataset UUID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            Tuple of (queries list, total count)
        """
        from sqlalchemy import func
        
        # Get total count
        count_result = await self.db.execute(
            select(func.count(Query.id)).where(Query.dataset_id == dataset_id)
        )
        total = count_result.scalar_one()
        
        # Get queries
        result = await self.db.execute(
            select(Query)
            .where(Query.dataset_id == dataset_id)
            .order_by(Query.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        queries = result.scalars().all()
        
        return list(queries), total
