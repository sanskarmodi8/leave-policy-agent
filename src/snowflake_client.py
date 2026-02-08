"""
Snowflake client with circuit breaker protection.
Handles connection pooling and error recovery.
"""

import logging
from contextlib import contextmanager
from typing import Any

from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException
from snowflake.snowpark.functions import col

from data.leave_policies import get_employee_data  # Mock fallback
from src.circuit_breaker import CircuitBreaker
from src.config import settings

logger = logging.getLogger(__name__)


class SnowflakeClient:
    """
    Snowflake client with circuit breaker pattern.
    Falls back to mock data if Snowflake is unavailable.
    """

    def __init__(self, use_mock: bool = True):
        """
        Initialize Snowflake client.

        Args:
            use_mock: If True, use mock data instead of real Snowflake.
                     Useful for development and testing.
        """
        self.use_mock = use_mock
        self.session: Session | None = None

        # Create circuit breaker for Snowflake calls
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            timeout=settings.circuit_breaker_timeout,
            name="SnowflakeCircuitBreaker",
        )

        if not use_mock:
            self._initialize_session()

    def _initialize_session(self):
        """Initialize Snowflake session with connection pooling."""
        try:
            connection_params = {
                "account": settings.snowflake_account,
                "user": settings.snowflake_user,
                "password": settings.snowflake_password,
                "warehouse": settings.snowflake_warehouse,
                "database": settings.snowflake_database,
                "schema": settings.snowflake_schema,
            }

            self.session = Session.builder.configs(connection_params).create()
            logger.info("Snowflake session initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Snowflake session: {e}")
            logger.warning("Falling back to mock data")
            self.use_mock = True

    @contextmanager
    def get_session(self):
        """Context manager for Snowflake session."""
        if self.use_mock or self.session is None:
            yield None
        else:
            try:
                yield self.session
            except Exception as e:
                logger.error(f"Snowflake session error: {e}")
                raise

    def get_employee_info(self, employee_id: str) -> dict[str, Any] | None:
        """
        Get employee information from Snowflake or mock data.

        Args:
            employee_id: Employee ID

        Returns:
            Employee information dict or None if not found
        """
        # Use mock data if configured
        if self.use_mock:
            logger.info(f"Using mock data for employee {employee_id}")
            return get_employee_data(employee_id)

        # Query Snowflake with circuit breaker protection
        try:
            return self.circuit_breaker.call(self._query_employee_from_snowflake, employee_id)
        except Exception as e:
            logger.error(f"Circuit breaker blocked or query failed: {e}")
            logger.warning("Falling back to mock data")
            return get_employee_data(employee_id)

    def _query_employee_from_snowflake(self, employee_id: str) -> dict[str, Any] | None:
        """
        Secure Snowpark query using DataFrame API.
        Prevents SQL injection by avoiding raw SQL strings entirely.
        """

        with self.get_session() as session:
            if session is None:
                raise Exception("Snowflake session not available")

            try:
                # ---- Employee table query (SAFE) ----
                employee_df = (
                    session.table("employees")
                    .select(
                        "employee_id",
                        "name",
                        "email",
                        "department",
                        "country",
                        "hire_date",
                    )
                    .filter(col("employee_id") == employee_id)
                ).to_pandas()

                if employee_df.empty:
                    logger.warning(f"Employee {employee_id} not found in Snowflake")
                    return None

                employee_data = employee_df.iloc[0].to_dict()

                # ---- Leave balance query (SAFE) ----
                balance_df = (
                    session.table("leave_balances")
                    .select("leave_type", "balance")
                    .filter(col("employee_id") == employee_id)
                ).to_pandas()

                employee_data["leave_balances"] = {
                    row["leave_type"]: row["balance"] for _, row in balance_df.iterrows()
                }

                logger.info(f"Retrieved employee {employee_id} via Snowpark")
                return employee_data

            except SnowparkSQLException as e:
                logger.error(f"Snowflake error: {e}")
                raise

    def get_circuit_breaker_state(self) -> dict:
        """Get circuit breaker state for monitoring."""
        return self.circuit_breaker.get_state()

    def close(self):
        """Close Snowflake session."""
        if self.session:
            self.session.close()
            logger.info("Snowflake session closed")


# Global Snowflake client instance
snowflake_client = SnowflakeClient(use_mock=not bool(settings.snowflake_account))
