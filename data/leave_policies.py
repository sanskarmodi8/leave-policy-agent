"""
Mock leave policy data for testing.
In production, this would come from a database.
"""

LEAVE_POLICIES = {
    "US": {
        "PTO": {
            "annual_allowance": 20,
            "carryover_limit": 5,
            "min_notice_days": 3,
            "max_consecutive_days": 10,
            "blackout_periods": ["2026-12-20:2026-12-31"],
            "approval_required": True,
            "description": "Paid Time Off for US employees",
        },
        "Sick Leave": {
            "annual_allowance": 10,
            "carryover_limit": 0,
            "min_notice_days": 0,
            "documentation_required_after_days": 3,
            "description": "Sick leave for health-related absences",
        },
        "Parental Leave": {
            "allowance_weeks": 16,
            "eligibility_months": 12,
            "paid": True,
            "description": "Paid parental leave for new parents",
        },
    },
    "India": {
        "Privilege Leave": {
            "annual_allowance": 18,
            "carryover_limit": 30,
            "min_notice_days": 7,
            "encashment_allowed": True,
            "description": "Privilege leave (earned leave) for India employees",
        },
        "Casual Leave": {
            "annual_allowance": 12,
            "carryover_limit": 0,
            "max_consecutive_days": 3,
            "description": "Short-term casual leave",
        },
        "Sick Leave": {
            "annual_allowance": 12,
            "carryover_limit": 0,
            "documentation_required_after_days": 2,
            "description": "Sick leave for health-related absences",
        },
        "Optional Holidays": {
            "annual_allowance": 3,
            "from_list": True,
            "advance_booking_required": True,
            "description": "Optional holidays from a predefined list",
        },
    },
}

# Mock employee database (in production, this is in Snowflake)
MOCK_EMPLOYEES = {
    "E001": {
        "employee_id": "E001",
        "name": "John Doe",
        "email": "john.doe@company.com",
        "department": "Engineering",
        "country": "US",
        "hire_date": "2022-01-15",
        "leave_balances": {"PTO": 15, "Sick Leave": 8, "Parental Leave": 0},
    },
    "E002": {
        "employee_id": "E002",
        "name": "Priya Sharma",
        "email": "priya.sharma@company.com",
        "department": "Marketing",
        "country": "India",
        "hire_date": "2021-06-10",
        "leave_balances": {
            "Privilege Leave": 12,
            "Casual Leave": 10,
            "Sick Leave": 12,
            "Optional Holidays": 2,
        },
    },
}


def get_leave_policy_data(country: str, leave_type: str = None):
    """Get leave policy for a country and optional leave type."""
    if country not in LEAVE_POLICIES:
        return None

    if leave_type:
        return LEAVE_POLICIES[country].get(leave_type)

    return LEAVE_POLICIES[country]


def get_employee_data(employee_id: str):
    """Get employee data by ID."""
    return MOCK_EMPLOYEES.get(employee_id)
