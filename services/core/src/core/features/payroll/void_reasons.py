"""Void reason intelligence (HR-AUT-002 §5.8.3).

Deterministic keyword classifier (no LLM - ownership decision from planning;
the same seam can feed an ai-agent scribe later without changing storage): a
void's free text is bucketed into a small taxonomy. The raw text is ALWAYS
stored on the run; the classification is derived per report. Business rule:
confidence below ``0.75`` keeps the run under ``unclassified`` so HR reviews
the raw text instead of trusting a weak guess.
"""

from __future__ import annotations

import dataclasses
import enum
from decimal import Decimal


class VoidReasonCategory(enum.StrEnum):
    """Denormalized void-cause taxonomy cross-tabulated in the monthly report."""

    DUPLICATE = "duplicate"
    WRONG_PERIOD = "wrong_period"
    CORRECTION_NEEDED = "correction_needed"
    UNCLASSIFIED = "unclassified"

    @property
    def label(self) -> str:
        return {
            VoidReasonCategory.DUPLICATE: "Duplicate",
            VoidReasonCategory.WRONG_PERIOD: "Wrong period",
            VoidReasonCategory.CORRECTION_NEEDED: "Correction needed",
            VoidReasonCategory.UNCLASSIFIED: "Unclassified",
        }[self]


# Confidence floor from the spec: below this the category is too weak to trust.
CONFIDENCE_FLOOR = Decimal("0.75")

# One signal phrase per keyword so "created twice by mistake" is a confident
# Duplicate while a lone "correction needed" stays unclassified for review.
_SIGNALS: dict[VoidReasonCategory, tuple[str, ...]] = {
    VoidReasonCategory.DUPLICATE: (
        "duplicate",
        "created twice",
        "twice",
        "double",
        "accidental",
        "by mistake",
        "mistake",
        "erroneous",
        "already exists",
    ),
    VoidReasonCategory.WRONG_PERIOD: (
        "wrong period",
        "incorrect period",
        "wrong pay period",
        "wrong month",
        "wrong date",
        "should be another",
    ),
    VoidReasonCategory.CORRECTION_NEEDED: (
        "correction",
        "correct",
        "adjust",
        "recompute",
        "recalculate",
        "update",
        "revise",
        "reclass",
    ),
}


@dataclasses.dataclass(frozen=True)
class VoidClassification:
    """Output of :func:`classify_void_reason` - category + match strength."""

    category: VoidReasonCategory
    confidence: Decimal
    text: str


def classify_void_reason(text: str) -> VoidClassification:
    """Classify free-text void reason into a :class:`VoidReasonCategory`.

    One matching signal = weak (0.6, below the floor) -> ``unclassified``;
    two or more matching signals in exactly one category = confident (0.9).
    Ties or no match -> ``unclassified`` with 0 confidence.
    """
    normalized = text.lower()
    matched: dict[VoidReasonCategory, int] = {}
    for category, phrases in _SIGNALS.items():
        matched[category] = sum(1 for phrase in phrases if phrase in normalized)
    top = max(matched.values(), default=0)
    winners = [category for category, count in matched.items() if count == top and top > 0]
    if top == 0 or len(winners) != 1:
        return VoidClassification(VoidReasonCategory.UNCLASSIFIED, Decimal("0"), text)
    winner = winners[0]
    confidence = Decimal("0.9") if top >= 2 else Decimal("0.6")
    if confidence < CONFIDENCE_FLOOR:
        return VoidClassification(VoidReasonCategory.UNCLASSIFIED, confidence, text)
    return VoidClassification(winner, confidence, text)
