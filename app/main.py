"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.api.v1 import api_router
from app.utils.error_handlers import setup_exception_handlers
from app.services.cache_service import cache_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Connect to Redis
    await cache_service.connect()
    print("✓ Connected to Redis")

    yield

    # Shutdown
    print("Shutting down...")
    await cache_service.disconnect()
    print("✓ Disconnected from Redis")


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

# Setup exception handlers
setup_exception_handlers(app)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["health"])
async def root():
    """Root endpoint - health check."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health_check():
    """Detailed health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "cache_enabled": settings.ENABLE_CACHE,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
