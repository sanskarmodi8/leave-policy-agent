"""
Tests for circuit breaker pattern.
Target: 95% coverage
"""

import time

import pytest

from src.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_closed(self):
        """Circuit breaker should start in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, timeout=5)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_successful_call_in_closed_state(self):
        """Successful calls should work normally in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3)

        def successful_func():
            return "success"

        result = cb.call(successful_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_single_failure_stays_closed(self):
        """Single failure should not open circuit."""
        cb = CircuitBreaker(failure_threshold=3)

        def failing_func():
            raise Exception("Test failure")

        with pytest.raises(Exception):
            cb.call(failing_func)

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1

    def test_threshold_failures_opens_circuit(self):
        """Reaching threshold should open circuit."""
        cb = CircuitBreaker(failure_threshold=3)

        def failing_func():
            raise Exception("Test failure")

        # Fail 3 times
        for _ in range(3):
            with pytest.raises(Exception):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    def test_open_circuit_blocks_calls(self):
        """Open circuit should block all calls."""
        cb = CircuitBreaker(failure_threshold=2)

        def failing_func():
            raise Exception("Test failure")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(failing_func)

        # Now circuit is OPEN
        def any_func():
            return "should not execute"

        with pytest.raises(CircuitBreakerOpenError):
            cb.call(any_func)

    def test_timeout_transitions_to_half_open(self):
        """After timeout, circuit should transition to HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=2, timeout=1)

        def failing_func():
            raise Exception("Test failure")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(1.1)

        # Next call should transition to HALF_OPEN
        def test_func():
            return "testing"

        result = cb.call(test_func)
        assert result == "testing"
        assert cb.state == CircuitState.CLOSED  # Success closes it

    def test_half_open_success_closes_circuit(self):
        """Successful call in HALF_OPEN should close circuit."""
        cb = CircuitBreaker(failure_threshold=2, timeout=1)

        def failing_func():
            raise Exception("Fail")

        # Open circuit
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(failing_func)

        time.sleep(1.1)

        # Success should close
        def success_func():
            return "success"

        result = cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens_circuit(self):
        """Failed call in HALF_OPEN should reopen circuit."""
        cb = CircuitBreaker(failure_threshold=2, timeout=1)

        def failing_func():
            raise Exception("Fail")

        # Open circuit
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(failing_func)

        time.sleep(1.1)

        # Fail in HALF_OPEN
        with pytest.raises(Exception):
            cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

    def test_get_state_returns_dict(self):
        """get_state should return circuit breaker state."""
        cb = CircuitBreaker(failure_threshold=5, name="TestBreaker")

        state = cb.get_state()

        assert isinstance(state, dict)
        assert state["name"] == "TestBreaker"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["failure_threshold"] == 5
