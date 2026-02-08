"""
Circuit breaker pattern for resilient external service calls.
Prevents cascading failures when Snowflake or other services are down.
"""

import logging
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(RuntimeError):
    """Raised when circuit breaker blocks execution."""


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker implementation.

    States:
    - CLOSED: Requests pass through normally
    - OPEN: All requests fail immediately (service is down)
    - HALF_OPEN: Allow one test request to check if service recovered

    Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout seconds
    - HALF_OPEN -> CLOSED: If test request succeeds
    - HALF_OPEN -> OPEN: If test request fails
    """

    def __init__(self, failure_threshold: int = 5, timeout: int = 60, name: str = "CircuitBreaker"):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery
            name: Name for logging
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.name = name

        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = None

        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"threshold={failure_threshold}, timeout={timeout}s"
        )

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args, **kwargs: Arguments to pass to function

        Returns:
            Result from function

        Raises:
            Exception: If circuit is OPEN or function fails
        """
        # Check if we should attempt recovery
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                logger.info(f"CircuitBreaker '{self.name}': OPEN -> HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError(
                    f"CircuitBreaker '{self.name}' is OPEN. Service unavailable."
                )

        try:
            # Execute the function
            result = func(*args, **kwargs)

            # Success - reset if we were testing
            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"CircuitBreaker '{self.name}': HALF_OPEN -> CLOSED")
                self._reset()

            return result

        except Exception as e:
            # Failure - increment counter
            self._record_failure()
            logger.error(
                f"CircuitBreaker '{self.name}' failure "
                f"({self.failure_count}/{self.failure_threshold}): {str(e)}"
            )
            raise e

    def _record_failure(self):
        """Record a failure and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        # Open circuit if threshold exceeded
        if self.failure_count >= self.failure_threshold:
            logger.warning(f"CircuitBreaker '{self.name}': Threshold exceeded. " f"CLOSED -> OPEN")
            self.state = CircuitState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.last_failure_time is None:
            return True

        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.timeout

    def _reset(self):
        """Reset circuit breaker to normal operation."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = None

    def get_state(self) -> dict:
        """Get current circuit breaker state for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
        }


def with_circuit_breaker(circuit_breaker: CircuitBreaker):
    """
    Decorator to wrap functions with circuit breaker.

    Usage:
        @with_circuit_breaker(my_breaker)
        def call_external_service():
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return circuit_breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator
