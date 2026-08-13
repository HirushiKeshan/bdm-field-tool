"""
Phase 1 — priority score that drives beat ranking. Every score comes with
a plain-English reason string built from the same numbers used to compute
it -- never a generic label. See docs/data-notes.md for why the segment
thresholds are what they are.
"""
from dataclasses import dataclass
from typing import Optional

from logic.segmentation import SegmentResult

SEGMENT_URGENCY = {
    "Slipping": 100,
    "Dormant-valuable": 90,
    "New/Never": 45,
    "Dormant-low": 35,
    "Core": 25,
}

MAX_VALUE_POINTS = 50
MAX_COVERAGE_POINTS = 30
COVERAGE_SATURATION_DAYS = 60  # days since last visit at which coverage scoring maxes out


def format_inr(value: Optional[float]) -> str:
    if value is None:
        return "no recorded value"
    if value >= 100_000:
        return f"₹{value / 100_000:.1f}L"
    if value >= 1_000:
        return f"₹{value / 1_000:.0f}k"
    return f"₹{value:.0f}"


@dataclass
class PriorityResult:
    score: float
    reason: str
    confidence_note: Optional[str]  # e.g. "limited history (1 month)" or None


def _coverage_points(days_since_last_visit: Optional[int]) -> float:
    if days_since_last_visit is None:
        return MAX_COVERAGE_POINTS
    return min(MAX_COVERAGE_POINTS, (days_since_last_visit / COVERAGE_SATURATION_DAYS) * MAX_COVERAGE_POINTS)


def _build_reason(seg: SegmentResult, days_since_last_visit: Optional[int], is_possible_duplicate: bool) -> str:
    parts = []
    if seg.segment == "Slipping":
        if seg.months_since_last_bill == 1:
            parts.append(f"Billed {format_inr(seg.latest_value)} last month, nothing this month")
        else:
            parts.append(f"Billed {format_inr(seg.latest_value)} this month, down from a {format_inr(seg.trailing_avg)}/mo average")
    elif seg.segment in ("Dormant-valuable", "Dormant-low"):
        parts.append(f"Quiet {seg.months_since_last_bill} months, used to do {format_inr(seg.avg_positive_value)}/mo")
    elif seg.segment == "Core":
        if seg.limited_history:
            parts.append(f"Billed {format_inr(seg.latest_value)} this month — first month on record, no trend yet")
        else:
            parts.append(f"Steady at {format_inr(seg.trailing_avg)}/mo, billed {format_inr(seg.latest_value)} this month")
    elif seg.segment == "New/Never":
        parts.append("On the books, no billing history yet")

    if days_since_last_visit is None:
        parts.append("never visited")
    elif days_since_last_visit >= 14:
        parts.append(f"not visited in {days_since_last_visit} days")

    if is_possible_duplicate:
        parts.append("possible duplicate outlet — verify before visiting")

    return "; ".join(parts)


def score_outlet(
    seg: SegmentResult,
    days_since_last_visit: Optional[int],
    value_percentile: float,
    is_possible_duplicate: bool = False,
) -> PriorityResult:
    """
    value_percentile: 0..1 rank of this outlet's relevant value (peak for
    dormant/new, trailing-avg-or-latest for core/slipping) among all
    outlets that have ever billed. Computed by the caller (db/queries.py)
    since it needs the full outlet population to rank against.
    """
    urgency = SEGMENT_URGENCY[seg.segment]
    value_points = value_percentile * MAX_VALUE_POINTS
    coverage_points = _coverage_points(days_since_last_visit)
    score = urgency + value_points + coverage_points

    confidence_note = None
    if seg.limited_history:
        months = seg.billed_month_count if seg.billed_month_count else 0
        confidence_note = f"limited history ({months} billed month{'s' if months != 1 else ''})"

    reason = _build_reason(seg, days_since_last_visit, is_possible_duplicate)
    return PriorityResult(score=round(score, 1), reason=reason, confidence_note=confidence_note)
