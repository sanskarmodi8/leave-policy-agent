"""
Tests for agent tools (get_leave_policy, check_leave_eligibility, etc.)
Target: 95% coverage
"""

from datetime import datetime, timedelta

from src.tools import check_leave_eligibility, get_employee_leave_summary, get_leave_policy


class TestGetLeavePolicy:
    """Test the get_leave_policy tool."""

    def test_get_us_pto_policy(self):
        """Test retrieving US PTO policy."""
        result = get_leave_policy("US", "PTO")

        assert result["success"] is True
        assert result["country"] == "US"
        assert result["leave_type"] == "PTO"
        assert result["policy"]["annual_allowance"] == 20
        assert result["policy"]["carryover_limit"] == 5
        assert result["policy"]["min_notice_days"] == 3

    def test_get_all_us_policies(self):
        """Test retrieving all policies for US."""
        result = get_leave_policy("US")

        assert result["success"] is True
        assert result["country"] == "US"
        assert result["leave_type"] == "all"
        assert "PTO" in result["policy"]
        assert "Sick Leave" in result["policy"]
        assert "Parental Leave" in result["policy"]

    def test_get_india_privilege_leave(self):
        """Test retrieving India Privilege Leave policy."""
        result = get_leave_policy("India", "Privilege Leave")

        assert result["success"] is True
        assert result["policy"]["annual_allowance"] == 18
        assert result["policy"]["carryover_limit"] == 30
        assert result["policy"]["encashment_allowed"] is True

    def test_invalid_country(self):
        """Test error handling for invalid country."""
        result = get_leave_policy("Canada", "PTO")

        assert "error" in result
        assert "Invalid country" in result["error"]

    def test_invalid_leave_type(self):
        """Test error handling for invalid leave type."""
        result = get_leave_policy("US", "Vacation")

        assert "error" in result
        assert "not found" in result["error"]


class TestCheckLeaveEligibility:
    """Test the check_leave_eligibility tool."""

    def test_eligible_pto_request(self):
        """Test a valid PTO request that should be approved."""
        # Future date, sufficient balance, meets notice period
        start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        result = check_leave_eligibility(
            employee_id="E001", leave_type="PTO", start_date=start_date, num_days=5
        )

        assert result["eligible"] is True
        assert result["current_balance"] == 15
        assert result["balance_after"] == 10
        assert result["requested_days"] == 5

    def test_insufficient_balance(self):
        """Test request with insufficient leave balance."""
        start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        result = check_leave_eligibility(
            employee_id="E001",
            leave_type="PTO",
            start_date=start_date,
            num_days=20,  # More than available (15)
        )

        assert result["eligible"] is False
        assert "Insufficient" in result["reason"]
        assert result["shortage"] == 5

    def test_insufficient_notice_period(self):
        """Test request with insufficient notice period."""
        # PTO requires 3 days notice, we're giving 1
        start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        result = check_leave_eligibility(
            employee_id="E001", leave_type="PTO", start_date=start_date, num_days=3
        )

        assert result["eligible"] is False
        assert "notice period" in result["reason"].lower()
        assert result["required_notice_days"] == 3

    def test_exceeds_max_consecutive_days(self):
        """Test request exceeding maximum consecutive days."""
        start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        result = check_leave_eligibility(
            employee_id="E001",
            leave_type="PTO",
            start_date=start_date,
            num_days=15,  # Max is 10
        )

        assert result["eligible"] is False
        assert "maximum" in result["reason"].lower()
        assert result["max_allowed"] == 10

    def test_blackout_period_overlap(self):
        """Test request overlapping with blackout period."""
        result = check_leave_eligibility(
            employee_id="E001",
            leave_type="PTO",
            start_date="2026-12-23",
            num_days=3,
        )

        assert result["eligible"] is False
        assert "blackout" in result["reason"].lower()

    def test_sick_leave_no_notice_required(self):
        """Test sick leave which requires 0 days notice."""
        # Sick leave can be taken immediately
        start_date = datetime.now().strftime("%Y-%m-%d")

        result = check_leave_eligibility(
            employee_id="E001", leave_type="Sick Leave", start_date=start_date, num_days=2
        )

        assert result["eligible"] is True

    def test_invalid_employee_id(self):
        """Test with non-existent employee."""
        result = check_leave_eligibility(
            employee_id="E999", leave_type="PTO", start_date="2024-12-01", num_days=3
        )

        assert result["eligible"] is False
        assert "not found" in result["reason"]

    def test_invalid_date_format(self):
        """Test with invalid date format."""
        result = check_leave_eligibility(
            employee_id="E001",
            leave_type="PTO",
            start_date="12/01/2024",  # Wrong format
            num_days=3,
        )

        assert result["eligible"] is False
        assert "Invalid date format" in result["reason"]

    def test_warnings_for_documentation(self):
        """Test that documentation warning appears for long sick leave."""
        start_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        result = check_leave_eligibility(
            employee_id="E001",
            leave_type="Sick Leave",
            start_date=start_date,
            num_days=5,  # More than 3 days
        )

        assert result["eligible"] is True
        assert any("documentation" in w.lower() for w in result["warnings"])

    def test_warnings_for_low_balance(self):
        """Test low balance warning."""
        start_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        result = check_leave_eligibility(
            employee_id="E001",
            leave_type="PTO",
            start_date=start_date,
            num_days=10,
        )

        assert result["eligible"] is True
        assert any("low balance" in w.lower() for w in result["warnings"])


class TestGetEmployeeLeaveSummary:
    """Test the get_employee_leave_summary tool."""

    def test_get_us_employee_summary(self):
        """Test retrieving US employee summary."""
        result = get_employee_leave_summary("E001")

        assert result["success"] is True
        assert result["employee_id"] == "E001"
        assert result["name"] == "John Doe"
        assert result["country"] == "US"
        assert result["department"] == "Engineering"
        assert "leave_balances" in result
        assert result["leave_balances"]["PTO"] == 15

    def test_get_india_employee_summary(self):
        """Test retrieving India employee summary."""
        result = get_employee_leave_summary("E002")

        assert result["success"] is True
        assert result["country"] == "India"
        assert "Privilege Leave" in result["leave_balances"]

    def test_invalid_employee(self):
        """Test with invalid employee ID."""
        result = get_employee_leave_summary("E999")

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"]
