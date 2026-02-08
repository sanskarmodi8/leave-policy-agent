"""
FastAPI application serving the Leave Policy Assistant Agent.
Provides REST API endpoints for chat and monitoring.
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from src.agent import get_agent
from src.config import settings
from src.snowflake_client import snowflake_client

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Pydantic models for API
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "What's my leave balance?",
                "session_id": "session_123",
                "employee_id": "E001",
            }
        }
    )

    message: str = Field(..., description="User's message")
    session_id: str = Field(..., description="Session identifier for conversation tracking")
    employee_id: str | None = Field(None, description="Optional employee ID for context")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "response": "Here's your current leave balance...",
                "session_id": "session_123",
            }
        }
    )

    response: str = Field(..., description="Agent's response")
    session_id: str = Field(..., description="Session identifier")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    environment: str
    snowflake_circuit_breaker: dict


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Starting Leave Policy Assistant API")
    logger.info(f"Environment: {settings.environment}")

    # Initialize agent
    try:
        get_agent()
        logger.info("Agent initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Leave Policy Assistant API")
    snowflake_client.close()


# Create FastAPI app
app = FastAPI(
    title="Leave Policy Assistant API",
    description="AI-powered assistant for employee leave policies and eligibility checks",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API Endpoints


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {"message": "Leave Policy Assistant API", "version": "1.0.0", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Returns service status and circuit breaker state.
    """
    return HealthResponse(
        status="healthy",
        environment=settings.environment,
        snowflake_circuit_breaker=snowflake_client.get_circuit_breaker_state(),
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    Chat with the Leave Policy Assistant.

    This endpoint maintains conversation history using session_id.
    Multiple requests with the same session_id will maintain context.

    Example conversation:

    Request 1:
    ```json
    {
        "message": "What's my leave balance?",
        "session_id": "user123_session1",
        "employee_id": "E001"
    }
    ```

    Response 1:
    ```json
    {
        "response": "You have 15 days of PTO and 8 days of sick leave remaining.",
        "session_id": "user123_session1"
    }
    ```

    Request 2 (same session):
    ```json
    {
        "message": "Can I take 5 days PTO next week?",
        "session_id": "user123_session1"
    }
    ```

    Response 2:
    ```json
    {
        "response": "Yes, you're eligible! You have sufficient balance...",
        "session_id": "user123_session1"
    }
    ```
    """
    try:
        logger.info(f"Chat request: session={request.session_id}")

        # Get agent
        agent = get_agent()

        # Process message (note: agent.chat() handles async internally via asyncio.run())
        response_text = agent.chat(
            message=request.message, session_id=request.session_id, employee_id=request.employee_id
        )

        return ChatResponse(response=response_text, session_id=request.session_id)

    except Exception as e:
        logger.error(f"Error in /chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred processing your request. Please try again.",
        ) from e


@app.post("/reset-conversation/{session_id}", tags=["Chat"])
async def reset_conversation(session_id: str):
    """
    Reset conversation history for a session.
    Useful for starting a fresh conversation.
    """
    try:
        agent = get_agent()
        agent.reset_conversation(session_id)

        return {"message": f"Conversation reset for session {session_id}", "session_id": session_id}

    except Exception as e:
        logger.error(f"Error resetting conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error resetting conversation"
        ) from e


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    """
    Prometheus-compatible metrics endpoint.

    Returns:
    - Circuit breaker state
    - Active conversations
    - System health
    """
    agent = get_agent()

    return {
        "circuit_breaker": snowflake_client.get_circuit_breaker_state(),
        "active_conversations": len(agent.conversations),
        "environment": settings.environment,
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
    )
