"""API v1 package."""

from fastapi import APIRouter
from app.api.v1.endpoints import datasets, queries

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(queries.router, prefix="/queries", tags=["queries"])
