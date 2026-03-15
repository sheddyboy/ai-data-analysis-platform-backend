"""Application configuration using Pydantic Settings."""

from typing import Annotated
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database Configuration
    DATABASE_URL: Annotated[str, Field(description="PostgreSQL connection URL")]

    # Redis Configuration
    REDIS_URL: Annotated[str, Field(description="Redis connection URL")]

    # OpenAI Configuration
    OPENAI_API_KEY: Annotated[str, Field(description="OpenAI API key")]
    OPENAI_MODEL: Annotated[str, Field(description="OpenAI model name")] = "gpt-4o-mini"

    # Application Settings
    APP_NAME: Annotated[str, Field()] = "AI Data Analysis Platform"
    APP_VERSION: Annotated[str, Field()] = "2.0.0"
    DEBUG: Annotated[bool, Field()] = True
    UPLOAD_DIR: Annotated[str, Field()] = "./uploads"
    DATA_DIR: Annotated[str, Field()] = "./data"
    MAX_UPLOAD_SIZE: Annotated[int, Field(gt=0, description="Max upload size in bytes")] = 104857600

    # Server Configuration
    HOST: Annotated[str, Field()] = "0.0.0.0"
    PORT: Annotated[int, Field(gt=0, lt=65536)] = 8000

    # Cache Configuration
    CACHE_TTL: Annotated[int, Field(gt=0, description="Cache TTL in seconds")] = 3600
    ENABLE_CACHE: Annotated[bool, Field()] = True

    # LLM Configuration
    LLM_TEMPERATURE: Annotated[float, Field(ge=0.0, le=2.0)] = 0.0
    LLM_MAX_TOKENS: Annotated[int, Field(gt=0)] = 2000
    AGENT_MAX_ITERATIONS: Annotated[int, Field(gt=0)] = 15  # legacy fallback
    AGENT_VERBOSE: Annotated[bool, Field()] = True

    # V2: Per-node model configuration (use stronger models for planning/synthesis)
    PLANNER_MODEL: Annotated[str, Field(description="LLM model for the planner node")] = "gpt-4o"
    EXECUTOR_MODEL: Annotated[str, Field(description="LLM model for the tool executor loop")] = "gpt-4o-mini"
    SYNTHESIZER_MODEL: Annotated[str, Field(description="LLM model for synthesizer and follow-up nodes")] = "gpt-4o"

    # V2: Per-complexity iteration limits
    AGENT_MAX_ITERATIONS_SIMPLE: Annotated[int, Field(gt=0)] = 8
    AGENT_MAX_ITERATIONS_MODERATE: Annotated[int, Field(gt=0)] = 15
    AGENT_MAX_ITERATIONS_COMPLEX: Annotated[int, Field(gt=0)] = 25

    # V2: Streaming
    STREAMING_ENABLED: Annotated[bool, Field()] = True

    # Sandbox Configuration
    SANDBOX_TIMEOUT: Annotated[int, Field(gt=0, description="Max seconds for sandbox code execution")] = 30
    SANDBOX_MAX_OUTPUT: Annotated[int, Field(gt=0, description="Max chars of sandbox output returned to agent")] = 3000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


# Global settings instance
settings = Settings()  # type: ignore[call-arg]
