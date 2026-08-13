from logic.scoring import format_inr, score_outlet
from logic.segmentation import segment_outlet

WINDOW = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]


def rows(*pairs):
    return [{"month": m, "value": v} for m, v in pairs]


def test_format_inr_lakhs_and_thousands():
    assert format_inr(420_000) == "₹4.2L"
    assert format_inr(82_000) == "₹82k"
    assert format_inr(500) == "₹500"
    assert format_inr(None) == "no recorded value"


def test_slipping_missed_latest_month_reason_matches_the_facts():
    seg = segment_outlet(rows(("2026-05", 100_000), ("2026-06", 420_000)), WINDOW, valuable_threshold=200_000)
    result = score_outlet(seg, days_since_last_visit=10, value_percentile=0.8)
    assert "₹4.2L" in result.reason
    assert "nothing this month" in result.reason


def test_dormant_reason_uses_average_not_peak():
    seg = segment_outlet(rows(("2026-02", 100_000), ("2026-03", 300_000)), WINDOW, valuable_threshold=50_000)
    result = score_outlet(seg, days_since_last_visit=90, value_percentile=0.9)
    assert "Quiet 4 months" in result.reason
    assert "₹2.0L/mo" in result.reason  # avg of 100k and 300k = 200k = 2.0L


def test_never_visited_outlet_flagged_in_reason_and_maxes_coverage_points():
    seg = segment_outlet([], WINDOW, valuable_threshold=200_000)
    result = score_outlet(seg, days_since_last_visit=None, value_percentile=0.0)
    assert "never visited" in result.reason


def test_limited_history_outlet_has_confidence_note():
    seg = segment_outlet(rows(("2026-07", 62_000)), WINDOW, valuable_threshold=200_000)
    result = score_outlet(seg, days_since_last_visit=5, value_percentile=0.5)
    assert result.confidence_note is not None
    assert "1 billed month" in result.confidence_note


def test_slipping_always_outranks_core_at_equal_value_and_coverage():
    core_seg = segment_outlet(rows(*[(m, 100_000) for m in WINDOW]), WINDOW, valuable_threshold=200_000)
    slipping_seg = segment_outlet(
        rows(("2026-02", 100_000), ("2026-03", 100_000), ("2026-04", 100_000),
             ("2026-05", 100_000), ("2026-06", 100_000), ("2026-07", 40_000)),
        WINDOW, valuable_threshold=200_000,
    )
    core_result = score_outlet(core_seg, days_since_last_visit=5, value_percentile=0.5)
    slipping_result = score_outlet(slipping_seg, days_since_last_visit=5, value_percentile=0.5)
    assert slipping_result.score > core_result.score


def test_possible_duplicate_flagged_in_reason():
    seg = segment_outlet(rows(("2026-07", 62_000)), WINDOW, valuable_threshold=200_000)
    result = score_outlet(seg, days_since_last_visit=5, value_percentile=0.5, is_possible_duplicate=True)
    assert "possible duplicate" in result.reason
