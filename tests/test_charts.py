from logic.charts import render_trend_sparkline

WINDOW = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]


def trend(*vals_and_flags):
    return [{"month": m, "value": v, "has_record": has} for m, (v, has) in zip(WINDOW, vals_and_flags)]


def test_no_record_month_renders_hollow_dashed_not_a_zero_line_point():
    t = trend((100_000, True), (None, False), (80_000, True), (0, True), (90_000, True), (95_000, True))
    svg = render_trend_sparkline(t)
    assert svg.count("stroke-dasharray") == 1  # exactly the one no-record month


def test_zero_bill_month_renders_accent_colored_not_navy():
    t = trend((100_000, True), (0, True), (100_000, True), (100_000, True), (100_000, True), (100_000, True))
    svg = render_trend_sparkline(t)
    assert "#D6266E" in svg  # the accent-colored zero-bill dot
    assert svg.count("fill=\"#0B2D6B\"") == 5  # the other five are real values


def test_line_never_bridges_a_no_record_gap():
    # months 0 and 2 both have data, month 1 doesn't -- there must be no
    # single <line> segment directly connecting point 0 to point 2 that
    # skips over the gap.
    t = trend((100_000, True), (None, False), (100_000, True), (None, False), (None, False), (100_000, True))
    svg = render_trend_sparkline(t)
    assert svg.count("<line") == 1  # baseline axis line only -- zero connecting segments drawn
    assert svg.count("stroke-dasharray") == 3


def test_empty_trend_does_not_crash():
    assert render_trend_sparkline([]) == "<svg></svg>"


def test_single_month_does_not_divide_by_zero():
    svg = render_trend_sparkline([{"month": "2026-07", "value": 50_000, "has_record": True}])
    assert "<svg" in svg
