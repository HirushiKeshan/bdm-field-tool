import csv
from pathlib import Path

import pytest

from logic.segmentation import SEGMENTS, compute_valuable_threshold, segment_all, segment_outlet

WINDOW = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
REPO_ROOT = Path(__file__).resolve().parent.parent


def rows(*pairs):
    return [{"month": m, "value": v} for m, v in pairs]


def test_no_rows_is_new_never():
    result = segment_outlet([], WINDOW, valuable_threshold=100_000)
    assert result.segment == "New/Never"


def test_all_zero_rows_is_dormant_low_not_new_never():
    # Has a record every month, just never billed a positive value --
    # a different fact from "no record at all".
    r = rows(("2026-05", 0), ("2026-06", 0), ("2026-07", 0))
    result = segment_outlet(r, WINDOW, valuable_threshold=100_000)
    assert result.segment == "Dormant-low"
    assert result.avg_positive_value is None


def test_stable_six_of_six_is_core():
    r = rows(*[(m, 100_000) for m in WINDOW])
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Core"
    assert result.limited_history is False


def test_latest_month_drop_over_threshold_is_slipping():
    r = rows(("2026-02", 100_000), ("2026-03", 100_000), ("2026-04", 100_000),
              ("2026-05", 100_000), ("2026-06", 100_000), ("2026-07", 50_000))
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Slipping"
    assert result.trailing_avg == 100_000


def test_small_drop_under_threshold_stays_core():
    r = rows(("2026-06", 100_000), ("2026-07", 80_000))  # 20% drop, under the 30% cutoff
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Core"


def test_gap_in_middle_of_history_does_not_break_classification():
    # Missing 2026-04 entirely (no record that month), still billing now.
    r = rows(("2026-02", 100_000), ("2026-03", 100_000), ("2026-05", 100_000),
              ("2026-06", 100_000), ("2026-07", 100_000))
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Core"
    assert result.billed_month_count == 5


def test_single_month_history_current_month_is_core_but_flagged():
    r = rows(("2026-07", 62_000))
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Core"
    assert result.limited_history is True


def test_single_month_history_not_current_is_dormant():
    r = rows(("2026-03", 62_000))
    result = segment_outlet(r, WINDOW, valuable_threshold=50_000)
    assert result.segment == "Dormant-valuable"
    assert result.months_since_last_bill == 4


def test_missed_only_latest_month_is_slipping():
    r = rows(("2026-05", 100_000), ("2026-06", 100_000))
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Slipping"
    assert result.months_since_last_bill == 1


def test_missed_two_months_high_peak_is_dormant_valuable():
    r = rows(("2026-02", 500_000), ("2026-03", 500_000))
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Dormant-valuable"
    assert result.months_since_last_bill == 4


def test_missed_two_months_low_peak_is_dormant_low():
    r = rows(("2026-02", 60_000), ("2026-03", 60_000))
    result = segment_outlet(r, WINDOW, valuable_threshold=200_000)
    assert result.segment == "Dormant-low"


def test_zero_value_row_never_counts_as_the_positive_bill():
    # Billed in Feb, explicit zero in every month since including latest.
    r = rows(("2026-02", 100_000), ("2026-03", 0), ("2026-04", 0),
              ("2026-05", 0), ("2026-06", 0), ("2026-07", 0))
    result = segment_outlet(r, WINDOW, valuable_threshold=50_000)
    assert result.segment in ("Dormant-valuable", "Dormant-low")
    assert result.months_since_last_bill == 5


def test_valuable_threshold_default_is_reachable_by_dormant_outlets():
    """Regression: the 75th-percentile default made Dormant-valuable
    unreachable once a few Core outlets' peaks dominated the top of the
    distribution -- 0 outlets qualified in the real dataset (492 billing
    outlets, Core+Slipping were the majority at 59%). Peaks here span the
    same range for both still-billing and gone-quiet outlets, as in the
    real data, so the median must be crossable by some dormant outlets
    without being trivially crossable by all of them."""
    data = {}
    for i in range(1, 31):
        peak = i * 100_000
        if i % 2 == 0:
            data[f"CORE{i}"] = rows((WINDOW[-1], peak))  # still billing now
        else:
            data[f"DORM{i}"] = rows(("2026-02", peak))  # quiet since month 1
    results = segment_all(data, WINDOW)
    dormant_valuable = [c for c, r in results.items() if r.segment == "Dormant-valuable"]
    dormant_low = [c for c, r in results.items() if r.segment == "Dormant-low"]
    assert dormant_valuable, "no dormant outlet qualified as valuable -- threshold is set too high to ever be reached"
    assert dormant_low, "every dormant outlet qualified as valuable -- threshold is set too low to discriminate"


def test_valuable_threshold_excludes_never_billed_outlets():
    threshold = compute_valuable_threshold(
        {"A": rows(("2026-07", 100_000)), "B": [], "C": rows(("2026-07", 0))},
        WINDOW,
    )
    assert threshold == 100_000


def test_segment_all_every_outlet_lands_in_exactly_one_segment():
    data = {
        "A": [],
        "B": rows(("2026-07", 0)),
        "C": rows(*[(m, 50_000) for m in WINDOW]),
        "D": rows(("2026-02", 500_000)),
    }
    results = segment_all(data, WINDOW)
    assert set(results.keys()) == set(data.keys())
    for code, result in results.items():
        assert result.segment in SEGMENTS, f"{code} landed in invalid segment {result.segment!r}"


def test_real_dataset_every_outlet_lands_in_exactly_one_segment():
    """Integration check against the actual shipped CSVs, not just synthetic
    fixtures -- this is the assertion the brief explicitly asks for."""
    outlets_path = REPO_ROOT / "outlets.csv"
    billing_path = REPO_ROOT / "billing-monthly.csv"
    if not outlets_path.exists() or not billing_path.exists():
        pytest.skip("source CSVs not present")

    with open(outlets_path, newline="", encoding="utf-8") as f:
        outlet_codes = [row["Outlet Code"] for row in csv.DictReader(f)]

    all_rows = {code: [] for code in outlet_codes}
    with open(billing_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["Outlet Code"]
            if code in all_rows:
                all_rows[code].append({"month": row["Month"], "value": float(row["Value"])})

    results = segment_all(all_rows, WINDOW)
    assert len(results) == len(outlet_codes)
    assert set(results.keys()) == set(outlet_codes)
    for code, result in results.items():
        assert result.segment in SEGMENTS, f"{code} landed in invalid segment {result.segment!r}"

    counts = {}
    for result in results.values():
        counts[result.segment] = counts.get(result.segment, 0) + 1
    assert sum(counts.values()) == len(outlet_codes)
