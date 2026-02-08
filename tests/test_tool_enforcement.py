"""
Tests for ensuring tool enforcement.
"""

from unittest.mock import patch

from src.agent import LeaveAssistantAgent


def test_sensitive_query_without_tools_is_rejected():
    """
    The agent must never produce eligibility decisions without calling tools.

    This test simulates the LLM answering directly.
    The system must block the response.
    """

    agent = LeaveAssistantAgent()

    # Simulate no tool usage
    with patch("src.utils.request_context.get_tools_called", return_value=[]):
        response = agent.chat(
            "Can I take 5 days PTO tomorrow?", session_id="safety-test", employee_id="E001"
        )

    assert "check official policy data" in response.lower()
