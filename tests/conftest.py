"""
Pytest configuration and fixtures.
Shared test utilities and mock data.
"""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from data.leave_policies import LEAVE_POLICIES, MOCK_EMPLOYEES


@pytest.fixture
def mock_employee_data():
    """Return mock employee data for testing."""
    return MOCK_EMPLOYEES.copy()


@pytest.fixture
def mock_leave_policies():
    """Return mock leave policies for testing."""
    return LEAVE_POLICIES.copy()


@pytest.fixture
def us_employee():
    """Return US employee for testing."""
    return {
        "employee_id": "E001",
        "name": "John Doe",
        "department": "Engineering",
        "country": "US",
        "leave_balances": {"PTO": 15, "Sick Leave": 8},
    }


@pytest.fixture
def india_employee():
    """Return India employee for testing."""
    return {
        "employee_id": "E002",
        "name": "Priya Sharma",
        "department": "Marketing",
        "country": "India",
        "leave_balances": {"Privilege Leave": 12, "Casual Leave": 10},
    }


@pytest.fixture
def mock_snowflake_session():
    """Mock Snowflake session."""
    session = Mock()
    session.sql = Mock()
    session.table = Mock()
    return session


@pytest.fixture
def test_client():
    """Create FastAPI test client."""
    from src.main import app

    return TestClient(app)
