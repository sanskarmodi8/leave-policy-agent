"""
Main agent implementation using Google ADK.
"""

import asyncio
import logging
import re
import time
from collections import OrderedDict
from typing import Any

from google.adk import Agent
from google.adk.models import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from src.callbacks import after_model_callback, before_model_callback
from src.config import settings
from src.conversation_state import LeaveRequestState
from src.observability import trace_span
from src.tools import AGENT_TOOLS
from src.utils.request_context import (
    clear_request_context,
    get_tools_called,
    set_request_context,
)

logger = logging.getLogger(__name__)
EMPLOYEE_ID_PATTERN = re.compile(r"\bE\d{3,}\b")


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
    Deterministic wrapper around a probabilistic language model.

    Responsibilities:
    - enforce tool usage for all authoritative answers
    - bind conversations to a single employee identity
    - prevent memory growth
    - guide incomplete user workflows

    The LLM generates language only.
    All decisions originate from backend tools.
    """

    def __init__(self):
        """Initialize the agent."""
        logger.info("Initializing LeaveAssistantAgent")

        # Initialize LiteLLM model
        self.model = LiteLlm(
            model=settings.litellm_model,
            api_key=settings.openrouter_api_key,
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
        )

        # Create runner with app name
        self.app_name = "leave_policy_assistant"
        self.runner = InMemoryRunner(agent=self.agent, app_name=self.app_name)

        self.session_state: dict[str, LeaveRequestState] = {}

        # Session store.
        # OrderedDict used so oldest sessions can be evicted deterministically.
        # Each session contains:
        #    ts: last access timestamp
        #    messages: bounded conversation history
        self.conversations: OrderedDict[str, dict[str, Any]] = OrderedDict()

        # Track which sessions we've created in the runner's session service
        self.created_sessions: set[str] = set()

        logger.info("LeaveAssistantAgent initialized successfully")

    def _extract_structured_info(self, message: str, state: LeaveRequestState):
        """Extract deterministic info from message without trusting LLM."""
        import re

        # days
        m = re.search(r"(\d+)\s*(day|days)", message.lower())
        if m:
            state.num_days = int(m.group(1))

        # leave types
        for lt in ["pto", "sick leave", "privilege leave", "casual leave"]:
            if lt in message.lower():
                state.leave_type = lt.title()

        # date naive detection
        if "tomorrow" in message.lower():
            from datetime import datetime, timedelta

            state.start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

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
            # Also remove from created_sessions tracking
            self.created_sessions.discard(sid)

        # Remove oldest if over capacity
        while len(self.conversations) > settings.max_sessions:
            oldest_sid, _ = self.conversations.popitem(last=False)
            self.created_sessions.discard(oldest_sid)

        for sid in list(self.session_state.keys()):
            if sid not in self.conversations:
                del self.session_state[sid]

    def _extract_employee_id_from_message(self, message: str) -> str | None:
        """
        Extract any employee id mentioned in the user message.

        We treat ANY referenced employee id as a potential access attempt.
        """
        match = EMPLOYEE_ID_PATTERN.search(message)
        return match.group(0) if match else None

    def _response_contains_decision(self, text: str) -> bool:
        """Detect if model produced an approval/denial without tool usage."""
        text = text.lower()

        decision_patterns = [
            "approved",
            "not approved",
            "eligible",
            "not eligible",
            "you can take",
            "you cannot take",
            "you may take",
            "request is valid",
        ]

        return any(p in text for p in decision_patterns)

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
            r"\bremaining\b",
            r"\bleft\b",
            r"\bdays available\b",
            r"\bapply leave\b",
            r"\bbook leave\b",
            r"\btake off\b",
            r"\bvacation\b",
            r"\bholiday\b",
        ]

        return any(re.search(p, message) for p in patterns)

    async def _ensure_session_created(self, session_id: str, user_id: str) -> None:
        """
        Ensure session exists in runner's session service.

        Args:
            session_id: Session identifier
            user_id: User identifier
        """
        if session_id not in self.created_sessions:
            # Create session in the runner's session service
            await self.runner.session_service.create_session(
                app_name=self.app_name, user_id=user_id, session_id=session_id
            )
            self.created_sessions.add(session_id)
            logger.info(f"Created session: {session_id} for user: {user_id}")

    async def _run_agent_async(self, message: str, session_id: str, employee_id: str = None) -> str:
        """
        Run agent asynchronously using Google ADK Runner pattern.

        Args:
            message: User's message
            session_id: Session identifier
            employee_id: Optional employee ID

        Returns:
            Agent's response text
        """
        user_id = employee_id or "anonymous"

        # Ensure session exists before running
        await self._ensure_session_created(session_id, user_id)

        # Create user message content
        content = types.Content(role="user", parts=[types.Part(text=message)])

        final_response_text = None

        try:
            # Run agent - session already exists
            async for event in self.runner.run_async(
                user_id=user_id, session_id=session_id, new_message=content
            ):
                # Check if this is the final response
                if event.is_final_response():
                    if event.content and event.content.parts:
                        # Extract text from first part
                        final_response_text = event.content.parts[0].text
                    break

        except Exception as e:
            logger.error(f"Error in async agent run: {str(e)}", exc_info=True)
            raise

        return final_response_text or ""

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
            try:
                state = self.session_state.setdefault(session_id, LeaveRequestState())
                self._extract_structured_info(message, state)

                if self._requires_verified_data(message) and "can i take" in message.lower():
                    missing = state.missing_fields()
                    questions = {
                        "leave_type": "Which type of leave is this (PTO, Sick Leave, etc)?",
                        "start_date": "When should the leave start?",
                        "num_days": "How many days do you want?",
                    }
                    if missing:
                        return questions.get(missing[0], "Could you clarify your request?")

                # Run agent with conversation history using async runner
                try:
                    with trace_span("agent_run", session=session_id):
                        # Execute async code in sync context
                        response_text = asyncio.run(
                            self._run_agent_async(message, session_id, employee_id)
                        )

                except (ValueError, AttributeError, TypeError) as e:
                    logger.error(f"Agent execution failed: {str(e)}", exc_info=True)
                    return "I cannot process that request."

                if not response_text:
                    return "I apologize, but I couldn't generate a response."

                # Tool Enforcement
                tools_used = get_tools_called()
                decision_like = self._response_contains_decision(response_text)

                if (self._requires_verified_data(message) or decision_like) and not tools_used:
                    logger.warning(
                        "Blocked response: model attempted to answer without tool usage "
                        f"(session={session_id})"
                    )

                    safe_response = "Let me verify that for you."

                    return safe_response

                # Update conversation tracking
                self.conversations[session_id]["ts"] = time.time()

                logger.info(f"Agent response generated for session {session_id}")
                return response_text

            finally:
                clear_request_context()

        except Exception as e:
            logger.error(f"Error in agent.chat: {str(e)}", exc_info=True)
            error_msg = (
                "I apologize, but I encountered an error processing your request. "
                "Please try again or contact HR support if the issue persists."
            )
            return error_msg

    def reset_conversation(self, session_id: str):
        """Reset conversation history for a session."""
        if session_id in self.conversations:
            del self.conversations[session_id]
            self.created_sessions.discard(session_id)
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
