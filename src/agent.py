"""
Main agent implementation using Google ADK.
"""

import logging
import re
import time
from collections import OrderedDict
from typing import Any

from google.adk.agents import Agent
from google.adk.llms import LiteLlm

from src.callbacks import after_model_callback, before_model_callback, validate_tool_call
from src.config import settings
from src.tools import AGENT_TOOLS
from src.utils.request_context import (
    clear_request_context,
    get_tools_called,
    set_request_context,
)

logger = logging.getLogger(__name__)


# Agent system instruction
AGENT_INSTRUCTION = """You are a helpful HR Leave Policy Assistant for our company.

Your role is to help employees:
1. Understand leave policies for their country (US or India)
2. Check their current leave balances
3. Determine if they're eligible for specific leave requests
4. Answer questions about notice periods, blackout dates, and requirements

IMPORTANT GUIDELINES:

**Accuracy**: Always use the tools provided to get accurate, up-to-date information. Never guess or make up policy details.

**Tool Usage**: 
- Use get_leave_policy() for policy questions
- Use get_employee_leave_summary() when asked about balances
- Use check_leave_eligibility() when asked about specific leave requests

**Tone**: Be friendly, professional, and helpful. Explain complex policies in simple terms.

**Privacy**: Only provide information about the employee who is asking. Never share other employees' data.

**Clarity**: When eligibility checks fail, clearly explain:
- What the issue is
- What the policy requires
- What the employee's options are

**Examples of Good Responses**:

User: "Can I take 5 days PTO next week?"
Agent: Let me check that for you. I'll need your employee ID to verify your balance and eligibility.

User: "What's the PTO policy?"
Agent: [Uses get_leave_policy tool] In the US, employees receive 20 days of PTO annually...

User: "What's my leave balance?"
Agent: [Uses get_employee_leave_summary] Here's your current leave balance: PTO: 15 days, Sick Leave: 8 days...

**Multi-turn Conversations**: Remember context from previous messages. If a user already told you their employee ID, don't ask again.

**Error Handling**: If something goes wrong or data isn't found, explain the issue clearly and offer alternatives.

**When You Don't Know**: If asked about topics outside leave policies (salary, benefits, etc.), politely redirect: "I specialize in leave policies. For that question, please contact HR directly at hr@company.com"

Your goal is to make the leave request process smooth and transparent for employees.
"""


class LeaveAssistantAgent:
    """
    Leave Policy Assistant Agent.
    Wraps Google ADK agent with additional functionality.
    """

    def __init__(self):
        """Initialize the agent."""
        logger.info("Initializing LeaveAssistantAgent")

        # Initialize LiteLLM model
        self.model = LiteLlm(
            model_name=settings.litellm_model,
            api_key=settings.openai_api_key,
        )

        # Create agent
        self.agent = Agent(
            name="leave_policy_assistant",
            model=self.model,
            description="HR Leave Policy Assistant for employee leave questions",
            instruction=AGENT_INSTRUCTION,
            tools=AGENT_TOOLS,
            # Add callbacks for security
            before_model_callback=before_model_callback,
            after_model_callback=after_model_callback,
            validate_tool_call=validate_tool_call,
        )

        # Session store.
        # OrderedDict used so oldest sessions can be evicted deterministically.
        # Each session contains:
        #    ts: last access timestamp
        #    messages: bounded conversation history
        self.conversations: OrderedDict[str, dict[str, Any]] = OrderedDict()

        logger.info("LeaveAssistantAgent initialized successfully")

    def _prune_sessions(self) -> None:
        """
        Enforce memory safety guarantees.

        Responsibilities:
        - Remove expired sessions (TTL)
        - Enforce maximum session count
        - Prevent unbounded RAM usage

        This function is called on every request so memory usage is self-healing.
        """
        now = time.time()

        # Remove expired
        expired = [
            sid
            for sid, meta in self.conversations.items()
            if now - meta["ts"] > settings.session_ttl_seconds
        ]
        for sid in expired:
            del self.conversations[sid]

        # Remove oldest if over capacity
        while len(self.conversations) > settings.max_sessions:
            self.conversations.popitem(last=False)

    def _extract_employee_id_from_message(self, message: str) -> str | None:
        """
        Extract any employee id mentioned in the user message.

        We treat ANY referenced employee id as a potential access attempt.
        """
        match = re.search(r"\bE\d{3,}\b", message)
        return match.group(0) if match else None

    def _requires_verified_data(self, message: str) -> bool:
        """
        Determine if the user's question requires authoritative company data.

        We intentionally over-detect. If unsure → force tool usage.
        Prevents the model from making HR decisions without backend verification.
        """
        message = message.lower()

        patterns = [
            r"\bbalance\b",
            r"\bhow many leave",
            r"\bhow much leave",
            r"\bcan i take",
            r"\beligib",
            r"\bpto\b",
            r"\bsick leave",
            r"\bprivilege leave",
            r"\bpolicy",
        ]

        return any(re.search(p, message) for p in patterns)

    def chat(self, message: str, session_id: str, employee_id: str = None) -> str:
        """
        Send a message to the agent and get a response.

        Args:
            message: User's message
            session_id: Session identifier for conversation history
            employee_id: Optional employee ID for context

        Returns:
            Agent's response as string
        """
        logger.info(f"Processing message for session {session_id}")

        self._prune_sessions()
        now = time.time()

        if session_id not in self.conversations:
            self.conversations[session_id] = {"ts": now, "messages": []}

        self.conversations[session_id]["ts"] = now
        messages = self.conversations[session_id]["messages"]

        messages.append({"role": "user", "content": message})

        # Trim history
        self.conversations[session_id]["messages"] = messages[-settings.max_history :]
        messages = self.conversations[session_id]["messages"]

        try:
            # security check
            mentioned_emp = self._extract_employee_id_from_message(message)

            if employee_id and mentioned_emp and mentioned_emp != employee_id:
                logger.warning(
                    f"Cross-employee access attempt blocked: "
                    f"session={employee_id}, requested={mentioned_emp}"
                )
                return "Access denied: you can only request your own leave information."

            set_request_context(session_id, employee_id)

            # Run agent with conversation history
            response = self.agent.run(messages=self.conversations[session_id])

            # Extract response content
            if isinstance(response, dict):
                response_text = response.get("content", str(response))
            else:
                response_text = str(response)

            messages.append({"role": "assistant", "content": response_text})
            self.conversations[session_id]["messages"] = messages[-settings.max_history :]

            # Tool Enforcement
            tools_used = get_tools_called()
            if self._requires_verified_data(message) and not tools_used:
                logger.warning(
                    "Blocked response: model attempted to answer without tool usage "
                    f"(session={session_id})"
                )

                safe_response = (
                    "I need to verify this using official company records before answering. "
                    "Please ask again — I will check the policy data."
                )

                return safe_response

            # Add assistant response to history
            self.conversations[session_id].append({"role": "assistant", "content": response_text})

            logger.info(f"Agent response generated for session {session_id}")
            return response_text

        except Exception as e:
            logger.error(f"Error in agent.chat: {str(e)}", exc_info=True)
            error_msg = (
                "I apologize, but I encountered an error processing your request. "
                "Please try again or contact HR support if the issue persists."
            )
            return error_msg

        finally:
            clear_request_context()

    def reset_conversation(self, session_id: str):
        """Reset conversation history for a session."""
        if session_id in self.conversations:
            del self.conversations[session_id]
            logger.info(f"Conversation reset for session {session_id}")

    def get_conversation_history(self, session_id: str) -> list[dict[str, Any]]:
        """Get conversation history for a session."""
        return self.conversations.get(session_id, [])


# Global agent instance
leave_agent = None


def get_agent() -> LeaveAssistantAgent:
    """Get or create global agent instance."""
    global leave_agent
    if leave_agent is None:
        leave_agent = LeaveAssistantAgent()
    return leave_agent
