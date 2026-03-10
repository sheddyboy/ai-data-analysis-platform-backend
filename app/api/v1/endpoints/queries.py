"""API endpoints for querying datasets."""

from fastapi import APIRouter, Depends, status
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
    InsightResponse,
)

router = APIRouter()


@router.post(
    "/datasets/{dataset_id}/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query a dataset",
    description="Ask a natural language question about a dataset"
)
async def query_dataset(
    dataset_id: UUID,
    request: QueryRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Query a dataset with a natural language question.
    
    - **dataset_id**: UUID of the dataset to query
    - **question**: Natural language question about the data
    
    The system will:
    1. Validate that the question is relevant to the dataset
    2. Analyze the data using AI agents
    3. Generate visualizations if appropriate
    4. Provide insights and recommendations
    
    Returns the answer, visualizations, and insights.
    """
    service = QueryService(db)
    query = await service.execute_query(
        dataset_id=dataset_id,
        question=request.question
    )
    
    # Build visualizations
    visualizations = []
    if query.visualizations:
        for viz in query.visualizations:
            visualizations.append(
                VisualizationResponse(
                    type=viz.get("type"),
                    title=viz.get("title"),
                    data=viz.get("data"),
                    layout=viz.get("layout"),
                )
            )
    
    # Build insights
    insights = None
    if query.insights:
        insights = InsightResponse(
            summary=query.insights.get("summary", ""),
            key_findings=query.insights.get("key_findings", []),
            recommendations=query.insights.get("recommendations"),
        )
    
    return QueryResponse(
        query_id=query.id,
        dataset_id=query.dataset_id,
        question=query.question,
        answer=query.answer,
        visualizations=visualizations,
        insights=insights,
        statistics=query.statistics,
        execution_time=query.execution_time,
        cache_hit=query.cache_hit == "true",
        status=query.status,
        created_at=query.created_at,
    )


@router.get(
    "/datasets/{dataset_id}/queries",
    response_model=QueryHistoryResponse,
    summary="Get query history",
    description="Retrieve all queries for a dataset"
)
async def get_query_history(
    dataset_id: UUID,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the query history for a dataset.
    
    - **dataset_id**: UUID of the dataset
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records to return (default: 50)
    
    Returns a list of all queries made against this dataset.
    """
    service = QueryService(db)
    queries, total = await service.get_dataset_queries(
        dataset_id=dataset_id,
        skip=skip,
        limit=limit
    )
    
    items = [
        QueryHistoryItem(
            query_id=q.id,
            question=q.question,
            answer=q.answer,
            status=q.status,
            execution_time=q.execution_time,
            created_at=q.created_at,
        )
        for q in queries
    ]
    
    return QueryHistoryResponse(
        queries=items,
        total=total
    )


@router.get(
    "/{query_id}",
    response_model=QueryResponse,
    summary="Get query result",
    description="Retrieve a specific query result by ID"
)
async def get_query_result(
    query_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific query result by ID.
    
    - **query_id**: UUID of the query
    
    Returns the complete query result including answer, visualizations, and insights.
    """
    service = QueryService(db)
    query = await service.get_query(query_id)
    
    # Build visualizations
    visualizations = []
    if query.visualizations:
        for viz in query.visualizations:
            visualizations.append(
                VisualizationResponse(
                    type=viz.get("type"),
                    title=viz.get("title"),
                    data=viz.get("data"),
                    layout=viz.get("layout"),
                )
            )
    
    # Build insights
    insights = None
    if query.insights:
        insights = InsightResponse(
            summary=query.insights.get("summary", ""),
            key_findings=query.insights.get("key_findings", []),
            recommendations=query.insights.get("recommendations"),
        )
    
    return QueryResponse(
        query_id=query.id,
        dataset_id=query.dataset_id,
        question=query.question,
        answer=query.answer,
        visualizations=visualizations,
        insights=insights,
        statistics=query.statistics,
        execution_time=query.execution_time,
        cache_hit=query.cache_hit == "true",
        status=query.status,
        created_at=query.created_at,
    )
