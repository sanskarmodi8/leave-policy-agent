"""
Tests for FastAPI endpoints.
Target: 90% coverage
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


class TestAPIEndpoints:
    """Test FastAPI REST API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_root_endpoint(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "Leave Policy Assistant API" in data["message"]
        assert "version" in data

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "environment" in data
        assert "snowflake_circuit_breaker" in data

    def test_metrics_endpoint(self, client):
        """Test metrics endpoint."""
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "circuit_breaker" in data
        assert "active_conversations" in data
        assert "environment" in data

    @patch("src.main.get_agent")
    def test_chat_endpoint_success(self, mock_get_agent, client):
        """Test successful chat request."""
        # Mock agent
        mock_agent = Mock()
        mock_agent.chat.return_value = "Test response from agent"
        mock_get_agent.return_value = mock_agent

        request_data = {
            "message": "What's my leave balance?",
            "session_id": "test_session_1",
            "employee_id": "E001",
        }

        response = client.post("/chat", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Test response from agent"
        assert data["session_id"] == "test_session_1"

    @patch("src.main.get_agent")
    def test_chat_endpoint_without_employee_id(self, mock_get_agent, client):
        """Test chat without employee ID."""
        mock_agent = Mock()
        mock_agent.chat.return_value = "Please provide your employee ID"
        mock_get_agent.return_value = mock_agent

        request_data = {"message": "Hello", "session_id": "test_session_2"}

        response = client.post("/chat", json=request_data)
        assert response.status_code == 200

    @patch("src.main.get_agent")
    def test_chat_endpoint_error_handling(self, mock_get_agent, client):
        """Test error handling in chat endpoint."""
        mock_agent = Mock()
        mock_agent.chat.side_effect = Exception("Test error")
        mock_get_agent.return_value = mock_agent

        request_data = {"message": "Test", "session_id": "test_session_3"}

        response = client.post("/chat", json=request_data)
        assert response.status_code == 500

    @patch("src.main.get_agent")
    def test_reset_conversation(self, mock_get_agent, client):
        """Test conversation reset endpoint."""
        mock_agent = Mock()
        mock_get_agent.return_value = mock_agent

        response = client.post("/reset-conversation/test_session")

        assert response.status_code == 200
        data = response.json()
        assert "reset" in data["message"].lower()
        mock_agent.reset_conversation.assert_called_once_with("test_session")

    def test_chat_validation_missing_fields(self, client):
        """Test validation for missing required fields."""
        response = client.post("/chat", json={"message": "test"})
        assert response.status_code == 422  # Validation error

    def test_openapi_docs_available(self, client):
        """Test that OpenAPI docs are accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200

        response = client.get("/docs")
        assert response.status_code == 200
