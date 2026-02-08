"""
Lightweight observability utilities.

Why this exists
---------------
LLM systems fail in non-obvious ways:
- slow tool calls
- retries hidden inside SDKs
- partial outages
- hallucination caused by timeout fallbacks

Traditional logging cannot reconstruct these failures.

This module provides deterministic execution tracing so that every
critical backend operation produces a structured latency record.

Design goals
------------
- zero external dependencies
- safe in async + threaded environments
- minimal runtime overhead
- readable logs for interview review
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

logger = logging.getLogger("leave_agent.trace")


@contextmanager
def trace_span(name: str, **metadata):
    """
    Measure execution duration of a critical operation.

    This MUST wrap:
    - tool execution
    - database calls
    - eligibility validation
    - agent run boundaries

    The goal is not performance benchmarking — it is failure diagnosis.

    Example log:
    [TRACE] check_leave_eligibility duration_ms=43.21 employee=E001

    Guarantees
    ----------
    - Always logs completion (even if exception occurs)
    - Never suppresses exceptions
    - Produces structured key=value logs
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000

        meta = " ".join(f"{k}={v}" for k, v in metadata.items())
        logger.info("[TRACE] %s duration_ms=%.2f %s", name, duration_ms, meta)
