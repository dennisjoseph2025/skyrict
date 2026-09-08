"""Skip-reason taxonomy + deterministic classifier (HR-AUT-002 §5.3.5).

Every employee who produces no entry in a run, plus every computed employee
who needs review before pay runs, is bucketed into one of these codes so the
post-run analysis can render a reason badge, an optional one-click fix, and a
hard guarantee that no skip is ever silent (unknown text lands in
``unclassified`` and is queued for human review).

Domain decision (signed off in planning): missing bank details are a *risk*
row, NEVER a compute skip - the employee still gets paid; the drawer surfaces
them as an amber "needs attention" group with an edit shortcut.
"""

from __future__ import annotations

import dataclasses
import enum
import uuid


class SkipCategory(enum.StrEnum):
    """Whether a row stopped an entry (``skip``) or only needs attention."""

    SKIP = "skip"  # can block a run from being commit-ready
    RISK = "risk"  # does not block, but HR should act before pay


class SkipReasonCode(enum.StrEnum):
    """Taxonomy of why an employee produced no entry / needs review."""

    NO_COMPENSATION = "no_compensation"
    UNPAID_LEAVE = "unpaid_leave"
    TERMINATED_MID_PERIOD = "terminated_mid_period"
    NOT_ON_ROSTER = "not_on_roster"
    NO_PAYABLE_DAYS = "no_payable_days"
    MISSING_BANK_DETAILS = "missing_bank_details"
    UNCLASSIFIED = "unclassified"

    @property
    def label(self) -> str:
        return {
            SkipReasonCode.NO_COMPENSATION: "No effective compensation",
            SkipReasonCode.UNPAID_LEAVE: "On unpaid leave",
            SkipReasonCode.TERMINATED_MID_PERIOD: "Terminated mid-period",
            SkipReasonCode.NOT_ON_ROSTER: "Not on active roster",
            SkipReasonCode.NO_PAYABLE_DAYS: "No payable days",
            SkipReasonCode.MISSING_BANK_DETAILS: "Missing bank details",
            SkipReasonCode.UNCLASSIFIED: "Unclassified - review",
        }[self]

    @property
    def category(self) -> SkipCategory:
        if self is SkipReasonCode.MISSING_BANK_DETAILS:
            return SkipCategory.RISK
        return SkipCategory.SKIP


def classify_skip_reason(reason: str) -> SkipReasonCode:
    """Buckets a free-text skip reason deterministically.

    Keyword scoring (no LLM): the payroll engine's own reason strings and the
    batch caller's ``"no entry"`` fallback all resolve here; anything the
    taxonomy cannot match lands in ``unclassified`` for the review queue, so
    a skip is never silently dropped.
    """
    lowered = reason.lower()
    if "compensation" in lowered:
        return SkipReasonCode.NO_COMPENSATION
    if "unpaid" in lowered or "leave" in lowered:
        return SkipReasonCode.UNPAID_LEAVE
    if "terminated" in lowered:
        return SkipReasonCode.TERMINATED_MID_PERIOD
    if "roster" in lowered:
        return SkipReasonCode.NOT_ON_ROSTER
    if "payable days" in lowered or "days" in lowered:
        return SkipReasonCode.NO_PAYABLE_DAYS
    if "bank" in lowered:
        return SkipReasonCode.MISSING_BANK_DETAILS
    return SkipReasonCode.UNCLASSIFIED


@dataclasses.dataclass(frozen=True)
class SkipRecord:
    """One structured row in a run's skip/risk analysis.

    ``code`` can be supplied directly when the capture point already knows the
    taxonomy (the compute loop), otherwise it is derived from the reason text
    (the SKY-74 batch seam, which only sees ``compute_single`` strings).
    """

    employee_id: uuid.UUID
    code: SkipReasonCode
    reason: str
    category: SkipCategory

    @classmethod
    def from_text(
        cls,
        employee_id: uuid.UUID,
        reason: str,
        *,
        code: SkipReasonCode | None = None,
    ) -> SkipRecord:
        resolved = code or classify_skip_reason(reason)
        return cls(
            employee_id=employee_id,
            code=resolved,
            reason=reason,
            category=resolved.category,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "employee_id": str(self.employee_id),
            "reason_code": self.code.value,
            "reason": self.reason,
            "category": self.category.value,
        }
