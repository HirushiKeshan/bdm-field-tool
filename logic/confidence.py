"""
Phase 3 — visit verification. See README "The Madurai decision" for why
GPS is not the proof mechanism: outlets 3-5m apart (shared walls) sit well
inside typical smartphone GPS error (10-50m), so a coordinate cannot tell
two adjacent counters apart. It is used here only as an anomaly signal
(impossible pace / impossible distance), never as identification.

Confidence levels, strongest signal first:
  Verified   - the owner read out the outlet's own code and it matched,
               and nothing about the visit looks physically impossible.
  Partial    - no code match (or none entered), but something checkable
               was actually recorded: an order, a collection, or a
               specific blocker/outcome -- or the code matched but the
               visit is part of a flagged impossible-pace sequence.
  Unverified - a check-in with no code match and no recorded outcome.
               This is the "did the conversation actually happen" bucket.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConfidenceResult:
    level: str
    reason: str


def compute_confidence(
    code_match: Optional[bool],
    has_outcome_evidence: bool,
    gps_anomaly: Optional[str] = None,
) -> ConfidenceResult:
    if code_match:
        if gps_anomaly:
            return ConfidenceResult(
                "Partial",
                f"Outlet code matched, but flagged: {gps_anomaly} — downgraded pending review",
            )
        return ConfidenceResult("Verified", "Outlet code matched at check-in")

    if has_outcome_evidence:
        note = "Order, collection, or specific outcome recorded" if not gps_anomaly else \
            f"Outcome recorded, but flagged: {gps_anomaly}"
        return ConfidenceResult("Partial", note)

    if gps_anomaly:
        return ConfidenceResult("Unverified", f"No code, no outcome recorded, and flagged: {gps_anomaly}")

    return ConfidenceResult("Unverified", "No outlet code entered and no outcome recorded")


# --- GPS anomaly detection (batch, over a BDM's full visit history) ---
# Thresholds are conservative on purpose: this flags patterns that are
# physically implausible, not merely busy days. See docs/data-notes.md
# for the actual distribution these were picked against (max 26
# visits/day observed; 352 same-day pairs under 10 minutes apart).

MAX_PLAUSIBLE_VISITS_PER_DAY = 15
MIN_MINUTES_BETWEEN_DIFFERENT_OUTLETS = 10


def flag_daily_volume(visit_count: int) -> Optional[str]:
    if visit_count > MAX_PLAUSIBLE_VISITS_PER_DAY:
        return f"{visit_count} visits logged by this BDM on this day (implausible pace)"
    return None


def flag_tight_pacing(gap_minutes: Optional[float], same_outlet: bool) -> Optional[str]:
    if same_outlet or gap_minutes is None:
        return None
    if gap_minutes < MIN_MINUTES_BETWEEN_DIFFERENT_OUTLETS:
        return f"Only {gap_minutes:.0f} min since previous check-in at a different outlet"
    return None


def flag_outside_territory(outlet_territory: Optional[str], bdm_territory: Optional[str]) -> Optional[str]:
    if outlet_territory and bdm_territory and outlet_territory != bdm_territory:
        return f"Outlet is in {outlet_territory}, BDM is assigned to {bdm_territory}"
    return None
