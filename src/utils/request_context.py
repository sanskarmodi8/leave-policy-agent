"""
Request-scoped execution context.

This module stores per-request metadata in thread-local storage so that
tools, callbacks, and the agent can share execution state without
passing parameters through every function.

Why this exists:
The LLM must never be trusted to decide business outcomes.
We track whether a tool actually executed during the response generation.
If not — the answer is rejected.
"""

from __future__ import annotations

import threading

_tls = threading.local()


def set_request_context(session_id: str | None, employee_id: str | None) -> None:
    """Initialize request context for a single agent run."""
    _tls.session_id = session_id
    _tls.employee_id = employee_id
    _tls.tools_called: list[str] = []


def register_tool_call(tool_name: str) -> None:
    """Record that a verified backend tool was executed."""
    if not hasattr(_tls, "tools_called"):
        _tls.tools_called = []
    _tls.tools_called.append(tool_name)


def get_tools_called() -> list[str]:
    """Return tools executed in this request."""
    return getattr(_tls, "tools_called", [])


def get_session_employee() -> str | None:
    """Return employee bound to this request."""
    return getattr(_tls, "employee_id", None)


def clear_request_context() -> None:
    """Clean up request context after response."""
    for attr in ("session_id", "employee_id", "tools_called"):
        if hasattr(_tls, attr):
            delattr(_tls, attr)
