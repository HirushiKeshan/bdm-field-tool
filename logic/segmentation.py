"""
Phase 1 — outlet segmentation from billing-monthly.csv.

billing-monthly.csv is a SPARSE fact table: a missing (outlet, month) row
means "no record", a present row with value = 0 means "billed nothing
that month" -- these are different facts (see docs/data-notes.md) and
this module treats them differently: a zero-value row still counts as
"the outlet has a record" (rules out New/Never) but never counts as a
positive bill (rules out Core/Slipping's use of it as a real month).

Every outlet must land in exactly one of five segments. There is no
"unclassified" outcome -- an outlet with zero billing rows lands in
New/Never, not an error.
"""
from dataclasses import dataclass, field
from statistics import mean
from typing import Optional

SEGMENTS = ("Core", "Slipping", "Dormant-valuable", "Dormant-low", "New/Never")

# An outlet that misses its latest window month is "Slipping" for exactly
# one month of grace, then reclassified as Dormant. A latest-month bill
# more than 30% below the outlet's own trailing average also reads as
# Slipping even though it's still billing.
SLIP_DROP_THRESHOLD = 0.30
DORMANT_GRACE_MONTHS = 1


@dataclass
class SegmentResult:
    segment: str
    months_since_last_bill: Optional[int]  # None for New/Never
    billed_month_count: int
    peak_value: Optional[float]
    latest_value: Optional[float]
    trailing_avg: Optional[float]
    limited_history: bool  # fewer than 3 billed months behind the classification
    avg_positive_value: Optional[float] = None  # mean of all positive-value months, for "used to do X/mo" phrasing


def compute_valuable_threshold(all_outlet_rows: dict, window_months: list, percentile: float = 0.75) -> float:
    """
    all_outlet_rows: {outlet_code: [{"month": str, "value": float}, ...]}
    Returns the Nth percentile of each billing outlet's peak positive
    month, used to split Dormant into valuable vs low. Outlets that never
    billed a positive value don't contribute a peak and are excluded.
    """
    peaks = []
    for rows in all_outlet_rows.values():
        positives = [r["value"] for r in rows if r["value"] > 0]
        if positives:
            peaks.append(max(positives))
    if not peaks:
        return 0.0
    peaks.sort()
    idx = min(len(peaks) - 1, int(round(percentile * (len(peaks) - 1))))
    return peaks[idx]


def segment_outlet(rows: list, window_months: list, valuable_threshold: float) -> SegmentResult:
    """
    rows: this outlet's billing rows, sparse, e.g. [{"month": "2026-03", "value": 62000.0}, ...]
    window_months: all months in the reporting window, sorted ascending, e.g.
                    ["2026-02", ..., "2026-07"]
    """
    if not rows:
        return SegmentResult("New/Never", None, 0, None, None, None, limited_history=True)

    positives = [r for r in rows if r["value"] > 0]
    if not positives:
        # Outlet has a record (rows exist) but never a positive bill in
        # the window: it has a relationship, it's just never billed --
        # that's Dormant-low, not New/Never (which means no record at all).
        return SegmentResult("Dormant-low", None, 0, 0.0, None, None, limited_history=True, avg_positive_value=None)

    month_index = {m: i for i, m in enumerate(window_months)}
    positives_sorted = sorted(positives, key=lambda r: month_index[r["month"]])
    last_positive = positives_sorted[-1]
    months_since = (len(window_months) - 1) - month_index[last_positive["month"]]
    billed_count = len(positives_sorted)
    peak_value = max(r["value"] for r in positives_sorted)
    avg_value = mean(r["value"] for r in positives_sorted)
    limited_history = billed_count < 3

    if months_since == 0:
        latest_value = last_positive["value"]
        trailing = positives_sorted[:-1]
        if not trailing:
            # Only one billed month ever, and it's the current one: can't
            # assess a trend, but it IS billing now -- Core, flagged.
            return SegmentResult("Core", 0, billed_count, peak_value, latest_value, None, limited_history=True, avg_positive_value=avg_value)
        trailing_avg = mean(r["value"] for r in trailing)
        if trailing_avg > 0 and latest_value < (1 - SLIP_DROP_THRESHOLD) * trailing_avg:
            segment = "Slipping"
        else:
            segment = "Core"
        return SegmentResult(segment, 0, billed_count, peak_value, latest_value, trailing_avg, limited_history, avg_positive_value=avg_value)

    if months_since <= DORMANT_GRACE_MONTHS:
        return SegmentResult("Slipping", months_since, billed_count, peak_value, last_positive["value"], None, limited_history, avg_positive_value=avg_value)

    segment = "Dormant-valuable" if peak_value >= valuable_threshold else "Dormant-low"
    return SegmentResult(segment, months_since, billed_count, peak_value, last_positive["value"], None, limited_history, avg_positive_value=avg_value)


def segment_all(all_outlet_rows: dict, window_months: list, percentile: float = 0.75) -> dict:
    """
    all_outlet_rows: {outlet_code: [{"month","value"}, ...]} for every
    outlet the app knows about (include outlets with an empty list).
    Returns {outlet_code: SegmentResult}. Every key in the input appears
    exactly once in the output with a valid segment -- asserted in tests.
    """
    threshold = compute_valuable_threshold(all_outlet_rows, window_months, percentile)
    return {
        code: segment_outlet(rows, window_months, threshold)
        for code, rows in all_outlet_rows.items()
    }
