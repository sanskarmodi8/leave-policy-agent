"""
Tests for ensuring tool enforcement - FIXED VERSION
"""

from unittest.mock import patch

from src.agent import LeaveAssistantAgent


def test_sensitive_query_without_tools_is_rejected(monkeypatch):
    """
    The agent must never produce eligibility decisions without calling tools.

    This test simulates the LLM answering directly.
    The system must block the response.
    """

    # Mock the agent's async run to return a response that looks like a decision
    async def mock_run_agent_async(self, message, session_id, employee_id=None):
        return "Yes, you can take 5 days PTO tomorrow. You have sufficient balance."

    monkeypatch.setattr(
        "src.agent.LeaveAssistantAgent._run_agent_async",
        mock_run_agent_async,
    )

    agent = LeaveAssistantAgent()

    # Simulate no tool usage
    with patch("src.utils.request_context.get_tools_called", return_value=[]):
        response = agent.chat(
            "Can I take 5 days PTO tomorrow?", session_id="safety-test", employee_id="E001"
        )

    # Updated to match actual blocking message
    assert "verify" in response.lower() and (
        "eligibility" in response.lower() or "policy" in response.lower()
    )
