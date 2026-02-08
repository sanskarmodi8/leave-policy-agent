"""
Deterministic conversation state tracker.

Why:
LLMs are probabilistic. HR workflows are not.
We track required fields for eligibility checks and guide the user.
"""

from dataclasses import dataclass


@dataclass
class LeaveRequestState:
    leave_type: str | None = None
    start_date: str | None = None
    num_days: int | None = None

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.leave_type:
            missing.append("leave_type")
        if not self.start_date:
            missing.append("start_date")
        if not self.num_days:
            missing.append("num_days")
        return missing

    def is_complete(self) -> bool:
        return len(self.missing_fields()) == 0
