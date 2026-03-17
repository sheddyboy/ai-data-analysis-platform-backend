"""API v1 package."""

from fastapi import APIRouter
from app.api.v1.endpoints import datasets, queries, sessions, auth, quota

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(queries.router, prefix="/queries", tags=["queries"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(quota.router, prefix="/quota", tags=["quota"])
