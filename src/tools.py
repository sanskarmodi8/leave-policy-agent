"""
Agent tools - functions the agent can call to help users.
Each tool must have:
1. Clear function name
2. Detailed docstring (this is how the agent learns what it does!)
3. Type hints with Annotated descriptions
4. JSON-serializable return type
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any

from dateutil import parser
from dateutil.parser import ParserError

from data.leave_policies import get_leave_policy_data
from src.observability import trace_span
from src.snowflake_client import snowflake_client
from src.utils.request_context import register_tool_call

logger = logging.getLogger(__name__)


def get_leave_policy(
    country: Annotated[str, "Country code (US or India)"],
    leave_type: Annotated[
        str | None,
        "Optional leave type. If omitted returns all leave policies.",
    ] = None,
) -> Annotated[dict[str, Any], "Authoritative leave policy information"]:
    """
    Return official leave policy rules.

    Architectural role
    ------------------
    This function is the single source of truth for policy rules.
    The language model must never invent policy values.

    The agent uses this whenever answering:
    - allowances
    - notice periods
    - blackout dates
    - leave limits

    Guarantees
    ----------
    - deterministic output
    - no hallucinated policy
    - safe to expose to users
    """

    register_tool_call("get_leave_policy")

    with trace_span("get_leave_policy", country=country, leave_type=leave_type or "all"):
        logger.info(f"Getting leave policy: country={country}, leave_type={leave_type}")

        # Validate country
        if country not in ["US", "India"]:
            return {"error": f"Invalid country: {country}. Must be 'US' or 'India'."}

        # Get policy data
        policy = get_leave_policy_data(country, leave_type)

        if policy is None:
            if leave_type:
                return {
                    "error": f"Leave type '{leave_type}' not found for {country}. "
                    f"Please check the leave type name."
                }
            else:
                return {"error": f"No leave policies found for {country}."}

        return {
            "country": country,
            "leave_type": leave_type or "all",
            "policy": policy,
            "success": True,
        }


def check_leave_eligibility(
    employee_id: Annotated[str, "Employee ID (e.g., E001, E002)"],
    leave_type: Annotated[str, "Type of leave (PTO, Sick Leave, Privilege Leave, etc)"],
    start_date: Annotated[str, "Leave start date in YYYY-MM-DD format"],
    num_days: Annotated[int, "Number of days requested"],
) -> Annotated[dict[str, Any], "Eligibility check result with detailed reasoning"]:
    """
    Validate whether a leave request can be approved.

    Architectural role
    ------------------
    This function performs the actual business decision.
    The LLM is never allowed to determine eligibility itself.

    All approval/denial outcomes originate here.

    Guarantees
    ----------
    - deterministic approval rules
    - consistent across conversations
    - resistant to prompt injection

    Args:
        employee_id: Unique employee identifier
        leave_type: Type of leave being requested
        start_date: When the leave should start (YYYY-MM-DD)
        num_days: How many days of leave

    Returns:
        Dictionary with:
        - eligible: bool indicating if request can be approved
        - reason: detailed explanation
        - current_balance: current leave balance
        - balance_after: projected balance after leave
        - warnings: any concerns or requirements

    Example:
        >>> check_leave_eligibility("E001", "PTO", "2024-12-01", 5)
        {
            "eligible": True,
            "reason": "Request approved. Sufficient balance and notice period met.",
            "current_balance": 15,
            "balance_after": 10,
            ...
        }
    """

    register_tool_call("check_leave_eligibility")
    with trace_span("check_leave_eligibility", employee=employee_id):
        logger.info(
            f"Checking eligibility: employee={employee_id}, "
            f"leave_type={leave_type}, start_date={start_date}, days={num_days}"
        )

        # Get employee data
        with trace_span("snowflake_query", employee=employee_id):
            employee = snowflake_client.get_employee_info(employee_id)
        if not employee:
            return {
                "eligible": False,
                "reason": f"Employee {employee_id} not found in system.",
                "error": True,
            }

        country = employee["country"]
        leave_balances = employee.get("leave_balances", {})

        # Get leave policy
        policy = get_leave_policy_data(country, leave_type)
        if not policy:
            return {
                "eligible": False,
                "reason": f"Leave type '{leave_type}' not available for {country} employees.",
                "error": True,
            }

        # Parse start date
        try:
            start_dt = parser.parse(start_date)
        except (ParserError, ValueError):
            return {
                "eligible": False,
                "reason": f"Invalid date format: {start_date}. Please use YYYY-MM-DD.",
                "error": True,
            }

        current_balance = leave_balances.get(leave_type, 0)

        # VALIDATION CHECKS

        # 1. Check sufficient balance
        if current_balance < num_days:
            return {
                "eligible": False,
                "reason": f"Insufficient {leave_type} balance. "
                f"You have {current_balance} days available but requested {num_days} days.",
                "current_balance": current_balance,
                "requested_days": num_days,
                "shortage": num_days - current_balance,
            }

        # 2. Check notice period
        min_notice_days = policy.get("min_notice_days", 0)
        if min_notice_days > 0:
            days_until_leave = (start_dt - datetime.now()).days
            if days_until_leave < min_notice_days:
                return {
                    "eligible": False,
                    "reason": f"Insufficient notice period. {leave_type} requires "
                    f"{min_notice_days} days notice, but leave starts in "
                    f"{days_until_leave} days.",
                    "required_notice_days": min_notice_days,
                    "actual_notice_days": days_until_leave,
                }

        # 3. Check maximum consecutive days
        max_consecutive = policy.get("max_consecutive_days")
        if max_consecutive and num_days > max_consecutive:
            return {
                "eligible": False,
                "reason": f"{leave_type} allows maximum {max_consecutive} consecutive days, "
                f"but you requested {num_days} days.",
                "max_allowed": max_consecutive,
                "requested": num_days,
            }

        # 4. Check blackout periods
        blackout_periods = policy.get("blackout_periods", [])
        for period in blackout_periods:
            if ":" in period:
                # Format: "2024-12-20:2024-12-31"
                period_start, period_end = period.split(":")
                period_start_dt = parser.parse(period_start)
                period_end_dt = parser.parse(period_end)

                # Check if requested leave overlaps with blackout
                leave_end_dt = start_dt + timedelta(days=num_days - 1)

                if not (leave_end_dt < period_start_dt or start_dt > period_end_dt):
                    return {
                        "eligible": False,
                        "reason": f"Requested dates overlap with blackout period "
                        f"({period_start} to {period_end}). "
                        f"Please choose different dates.",
                        "blackout_period": period,
                    }

        # All checks passed!
        balance_after = current_balance - num_days

        # Build warnings list
        warnings = []
        if policy.get("approval_required"):
            warnings.append("Manager approval required")

        if policy.get("documentation_required_after_days"):
            doc_days = policy["documentation_required_after_days"]
            if num_days > doc_days:
                warnings.append(f"Medical documentation required for {num_days} days")

        if balance_after < 5:
            warnings.append(f"Low balance warning: only {balance_after} days will remain")

        return {
            "eligible": True,
            "reason": "Leave request is eligible for approval.",
            "current_balance": current_balance,
            "requested_days": num_days,
            "balance_after": balance_after,
            "start_date": start_date,
            "end_date": (start_dt + timedelta(days=num_days - 1)).strftime("%Y-%m-%d"),
            "warnings": warnings,
            "next_steps": [
                "Submit leave request through HR portal",
                (
                    "Await manager approval"
                    if policy.get("approval_required")
                    else "Request will be auto-approved"
                ),
            ],
        }


def get_employee_leave_summary(
    employee_id: Annotated[str, "Employee ID"],
) -> Annotated[dict[str, Any], "Complete leave balance summary"]:
    """
    Return authoritative leave balances for an employee.

    Architectural role
    ------------------
    This is the only allowed source of balance information.
    The model must never estimate or remember balances.

    Guarantees
    ----------
    - real data only
    - session-bound employee access
    - safe for direct user display
    """

    register_tool_call("get_employee_leave_summary")
    with trace_span("get_employee_leave_summary", employee=employee_id):
        logger.info(f"Getting leave summary for employee {employee_id}")

        with trace_span("snowflake_query", employee=employee_id):
            employee = snowflake_client.get_employee_info(employee_id)

        if not employee:
            return {"error": f"Employee {employee_id} not found.", "success": False}

        return {
            "employee_id": employee["employee_id"],
            "name": employee["name"],
            "department": employee["department"],
            "country": employee["country"],
            "hire_date": employee["hire_date"],
            "leave_balances": employee.get("leave_balances", {}),
            "success": True,
        }


# Export all tools
AGENT_TOOLS = [get_leave_policy, check_leave_eligibility, get_employee_leave_summary]
