"""
Main agent implementation using Google ADK with Hybrid Architecture.

ARCHITECTURAL PATTERN: Two-Path Design
--------------------------------------
Fast Path (Deterministic):
  - Simple data lookups (balance, policy)
  - Direct tool execution, bypass LLM
  - <100ms latency, zero LLM cost

Agentic Path (Reasoning):
  - Complex eligibility checks
  - Multi-turn conversations
  - Edge case handling

This pattern optimizes for:
- Reliability (deterministic for critical queries)
- Cost (avoid LLM when not needed)
- Latency (instant response for lookups)
- Intelligence (LLM for complex reasoning)

Production systems like Intercom, Zendesk use this pattern.
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
from src.tools import (
    AGENT_TOOLS,
    get_employee_leave_summary,
    get_leave_policy,
)
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
    Production-grade AI agent with hybrid routing architecture.

    Two execution paths:
    1. Fast Path: Deterministic queries → direct tool calls
    2. Agentic Path: Complex reasoning → LLM agent

    Design goals:
    - Reliability over intelligence for simple queries
    - Cost optimization (avoid LLM when unnecessary)
    - Sub-100ms response for common lookups
    - Intelligent handling of edge cases
    """

    def __init__(self):
        """Initialize the agent."""
        logger.info("Initializing LeaveAssistantAgent with hybrid architecture")

        # Initialize LiteLLM model
        if settings.openai_api_key:
            self.model = LiteLlm(model=settings.litellm_model, api_key=settings.openai_api_key)
        else:
            logger.warning("Running in DEMO MODE — LLM disabled")
            self.model = LiteLlm(model="gpt-4o-mini", api_key="demo")

        # Create agent
        self.agent = Agent(
            name="leave_policy_assistant",
            model=self.model,
            description="HR Leave Policy Assistant for employee leave questions",
            instruction=AGENT_INSTRUCTION,
            tools=AGENT_TOOLS,
            before_model_callback=before_model_callback,
            after_model_callback=after_model_callback,
        )

        # Create runner with app name
        self.app_name = "leave_policy_assistant"
        self.runner = InMemoryRunner(agent=self.agent, app_name=self.app_name)

        self.session_state: dict[str, LeaveRequestState] = {}
        self.conversations: OrderedDict[str, dict[str, Any]] = OrderedDict()
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
        """Enforce memory safety guarantees."""
        now = time.time()

        # Remove expired
        expired = [
            sid
            for sid, meta in self.conversations.items()
            if now - meta["ts"] > settings.session_ttl_seconds
        ]
        for sid in expired:
            del self.conversations[sid]
            self.created_sessions.discard(sid)

        # Remove oldest if over capacity
        while len(self.conversations) > settings.max_sessions:
            oldest_sid, _ = self.conversations.popitem(last=False)
            self.created_sessions.discard(oldest_sid)

        for sid in list(self.session_state.keys()):
            if sid not in self.conversations:
                del self.session_state[sid]

    def _extract_employee_id_from_message(self, message: str) -> str | None:
        """Extract any employee id mentioned in the user message."""
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

        Updated to be less aggressive - only flag true eligibility/approval decisions.
        """
        message = message.lower()

        # Only these require strict tool enforcement
        strict_patterns = [
            r"\bcan i take\b.*\bleave\b",
            r"\bam i (eligible|allowed)\b",
            r"\bapprove\b.*\bleave\b",
            r"\bbook\b.*\bleave\b",
        ]

        return any(re.search(p, message) for p in strict_patterns)

    async def _ensure_session_created(self, session_id: str, user_id: str) -> None:
        """Ensure session exists in runner's session service."""
        if session_id not in self.created_sessions:
            await self.runner.session_service.create_session(
                app_name=self.app_name, user_id=user_id, session_id=session_id
            )
            self.created_sessions.add(session_id)
            logger.info(f"Created session: {session_id} for user: {user_id}")

    async def _run_agent_async(self, message: str, session_id: str, employee_id: str = None) -> str:
        """Run agent asynchronously using Google ADK Runner pattern."""
        user_id = employee_id or "anonymous"

        await self._ensure_session_created(session_id, user_id)

        content = types.Content(role="user", parts=[types.Part(text=message)])

        final_response_text = None

        try:
            async for event in self.runner.run_async(
                user_id=user_id, session_id=session_id, new_message=content
            ):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        final_response_text = event.content.parts[0].text
                    break

        except Exception as e:
            logger.error(f"Error in async agent run: {str(e)}", exc_info=True)
            raise

        return final_response_text or ""

    async def chat_async(self, message: str, session_id: str, employee_id: str = None) -> str:
        """
        Async chat with hybrid routing architecture.

        FAST PATH: Deterministic queries → direct tool execution
        AGENTIC PATH: Complex reasoning → LLM agent

        This ensures reliability while showcasing agent capabilities.
        """
        logger.info(f"Processing message for session {session_id}")

        self._prune_sessions()
        now = time.time()

        if session_id not in self.conversations:
            self.conversations[session_id] = {"ts": now, "messages": []}

        self.conversations[session_id]["ts"] = now

        # ================================================================
        # FAST PATH: Deterministic routing for high-reliability queries
        # ================================================================
        if employee_id:
            lower_msg = message.lower()

            # Pattern 1: Balance check (most common query)
            if any(
                k in lower_msg
                for k in ["balance", "how many leave", "leave left", "remaining", "how much"]
            ):
                logger.info(f"[FAST PATH] Balance query detected for {employee_id}")
                try:
                    result = get_employee_leave_summary(employee_id)
                    if result.get("success"):
                        balances = "\n".join(
                            [f"• {k}: {v} days" for k, v in result["leave_balances"].items()]
                        )
                        return f"Here's your current leave balance:\n\n{balances}"
                except Exception as e:
                    logger.error(f"Fast path error: {e}")
                    # Fall through to agent path

            # Pattern 2: Policy lookup for India
            if "policy" in lower_msg and ("india" in lower_msg or "indian" in lower_msg):
                logger.info("[FAST PATH] India policy query detected")
                try:
                    result = get_leave_policy("India")
                    if result.get("success"):
                        policy_text = "Here are the leave policies for India employees:\n\n"
                        for leave_type, details in result["policy"].items():
                            allowance = details.get("annual_allowance", "N/A")
                            policy_text += f"• **{leave_type}**: {allowance} days/year\n"
                        return policy_text
                except Exception as e:
                    logger.error(f"Fast path error: {e}")

            # Pattern 3: Policy lookup for US
            if "policy" in lower_msg and (
                "us" in lower_msg or "american" in lower_msg or "united states" in lower_msg
            ):
                logger.info("[FAST PATH] US policy query detected")
                try:
                    result = get_leave_policy("US")
                    if result.get("success"):
                        policy_text = "Here are the leave policies for US employees:\n\n"
                        for leave_type, details in result["policy"].items():
                            allowance = details.get(
                                "annual_allowance", details.get("allowance_weeks", "N/A")
                            )
                            unit = "weeks" if "allowance_weeks" in details else "days"
                            policy_text += f"• **{leave_type}**: {allowance} {unit}/year\n"
                        return policy_text
                except Exception as e:
                    logger.error(f"Fast path error: {e}")

        # ================================================================
        # AGENTIC PATH: Complex reasoning, multi-turn, eligibility checks
        # ================================================================
        logger.info("[AGENTIC PATH] Using agent for complex query")

        try:
            # Security check
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
                        response_text = await self._run_agent_async(
                            message, session_id, employee_id
                        )

                except (ValueError, AttributeError, TypeError) as e:
                    logger.error(f"Agent execution failed: {str(e)}", exc_info=True)
                    return "I cannot process that request."

                if not response_text:
                    return "I apologize, but I couldn't generate a response."

                # RELAXED Tool Enforcement - Only block obvious hallucinations
                tools_used = get_tools_called()

                logger.info(f"Tools called: {tools_used}")
                logger.info(f"Response preview: {response_text[:100]}")

                # Only block if this is an eligibility decision without tools
                if self._response_contains_decision(response_text) and not tools_used:
                    logger.warning(
                        "Blocked response: model attempted decision without tool usage "
                        f"(session={session_id})"
                    )
                    return "Let me verify your eligibility using our official policy database."

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

    def chat(self, message: str, session_id: str, employee_id: str = None) -> str:
        """
        Synchronous wrapper for chat_async - used by tests.

        This allows tests to call agent.chat() without async/await.
        FastAPI will use chat_async() directly.
        """

        # Check if we're already in an event loop
        try:
            asyncio.get_running_loop()
            # We're in an event loop - can't use asyncio.run()
            raise RuntimeError("chat() called from async context. Use chat_async() instead.")
        except RuntimeError:
            # No event loop running - safe to use asyncio.run()
            return asyncio.run(self.chat_async(message, session_id, employee_id))

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
