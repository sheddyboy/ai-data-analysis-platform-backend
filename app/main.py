"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.api.v1 import api_router
from app.utils.error_handlers import setup_exception_handlers
from app.services.cache_service import cache_service

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting {} v{}", settings.APP_NAME, settings.APP_VERSION)

    # Connect to Redis
    await cache_service.connect()
    logger.info("Connected to Redis")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await cache_service.disconnect()
    logger.info("Disconnected from Redis")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    AI Data Analysis & Insight Agent Platform
    
    Upload datasets and ask questions in natural language.
    The AI agent will analyze your data, generate visualizations,
    and provide actionable insights.
    
    ## Features
    
    * 📊 **Natural Language Queries**: Ask questions in plain English
    * 🤖 **AI-Powered Analysis**: Intelligent data exploration
    * 📈 **Automatic Visualizations**: Charts generated based on context
    * 💡 **Insights Generation**: Natural language summaries
    * ⚡ **Fast Performance**: Redis-based caching
    * 📁 **Multi-Format Support**: CSV and Excel files
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Setup exception handlers
setup_exception_handlers(app)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["health"])
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health_check():
    """
    Detailed health check — verifies DB and Redis connectivity.
    Returns 200 if all systems are up, 503 if any dependency is down.
    """
    from fastapi import Response
    from sqlalchemy import text
    from app.database import AsyncSessionLocal

    checks: dict = {}

    # Database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Redis
    try:
        pong = await cache_service.redis.ping()  # type: ignore[union-attr]
        checks["redis"] = "ok" if pong else "error: no pong"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "checks": checks,
    }


@app.get("/admin/stats", tags=["admin"])
async def admin_stats():
    """
    Aggregate platform statistics — query counts, avg execution time,
    cache hit rate, and total token spend.
    Requires no auth in v4-alpha; lock this down when user roles are added.
    """
    from sqlalchemy import func, select, cast as sa_cast, Float
    from app.database import AsyncSessionLocal
    from app.models.dataset import Dataset, Query

    async with AsyncSessionLocal() as db:
        dataset_count = (await db.execute(select(func.count(Dataset.id)))).scalar_one()
        query_count = (await db.execute(select(func.count(Query.id)))).scalar_one()

        avg_time_row = await db.execute(
            select(func.avg(Query.execution_time)).where(Query.execution_time.is_not(None))
        )
        avg_time = avg_time_row.scalar_one()

        cache_hits = (
            await db.execute(select(func.count(Query.id)).where(Query.cache_hit == "true"))
        ).scalar_one()

    cache_hit_rate = round(cache_hits / query_count, 4) if query_count else 0.0

    return {
        "datasets": dataset_count,
        "queries": query_count,
        "avg_execution_time_seconds": round(float(avg_time), 3) if avg_time else None,
        "cache_hit_rate": cache_hit_rate,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
