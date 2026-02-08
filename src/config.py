"""
Configuration management using Pydantic Settings.
Reads from environment variables.
"""

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    model_config = ConfigDict(env_file=".env", case_sensitive=False)

    # LLM Configuration
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    litellm_model: str = Field(default="gpt-4o-mini", alias="LITELLM_MODEL")

    # Session memory controls
    max_sessions: int = Field(default=1000, alias="MAX_SESSIONS")
    max_history: int = Field(default=20, alias="MAX_HISTORY")
    session_ttl_seconds: int = Field(default=1800, alias="SESSION_TTL_SECONDS")

    # Snowflake Configuration
    snowflake_account: str = Field(default="", alias="SNOWFLAKE_ACCOUNT")
    snowflake_user: str = Field(default="", alias="SNOWFLAKE_USER")
    snowflake_password: str = Field(default="", alias="SNOWFLAKE_PASSWORD")
    snowflake_warehouse: str = Field(default="", alias="SNOWFLAKE_WAREHOUSE")
    snowflake_database: str = Field(default="", alias="SNOWFLAKE_DATABASE")
    snowflake_schema: str = Field(default="", alias="SNOWFLAKE_SCHEMA")

    # Application Configuration
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Circuit Breaker Configuration
    circuit_breaker_failure_threshold: int = Field(
        default=5, alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD"
    )
    circuit_breaker_timeout: int = Field(default=60, alias="CIRCUIT_BREAKER_TIMEOUT")


# Global settings instance
settings = Settings()
