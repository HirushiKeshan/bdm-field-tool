from logic.charts import (ACCENT, GREY, HIGH, LOW, MID, NAVY, build_anomaly_breakdown_figure,
                            build_confidence_mix_figure, build_time_allocation_figure, build_trend_figure)

WINDOW = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]


def trend(*vals_and_flags):
    return [{"month": m, "value": v, "has_record": has} for m, (v, has) in zip(WINDOW, vals_and_flags)]


def _line_trace(fig):
    return fig.data[0]


def test_no_record_month_leaves_a_none_in_the_line_trace_and_gets_a_hollow_marker():
    t = trend((100_000, True), (None, False), (80_000, True), (0, True), (90_000, True), (95_000, True))
    fig = build_trend_figure(t)
    line = _line_trace(fig)
    assert line.y[1] is None  # a real gap, not zero
    assert line.connectgaps is False
    # the hollow-marker overlay trace exists and is positioned at the gap month
    assert len(fig.data) == 2
    hollow = fig.data[1]
    assert hollow.x == ("2026-03",)
    assert hollow.marker.symbol == "circle-open"


def test_zero_bill_month_is_accent_colored_not_navy_and_still_connected():
    t = trend((100_000, True), (0, True), (100_000, True), (100_000, True), (100_000, True), (100_000, True))
    fig = build_trend_figure(t)
    line = _line_trace(fig)
    assert line.marker.color[1] == ACCENT
    assert all(c == NAVY for i, c in enumerate(line.marker.color) if i != 1)
    assert line.y[1] == 0  # a real value (zero), unlike the None used for no-record
    assert "billed nothing" in line.hovertext[1]


def test_no_record_never_silently_becomes_zero_in_hover_text():
    t = trend((100_000, True), (None, False), (100_000, True), (100_000, True), (100_000, True), (100_000, True))
    fig = build_trend_figure(t)
    line = _line_trace(fig)
    assert "no record" in line.hovertext[1]
    assert "billed nothing" not in line.hovertext[1]


def test_no_hollow_marker_trace_when_every_month_has_a_record():
    t = trend(*[(50_000, True) for _ in WINDOW])
    fig = build_trend_figure(t)
    assert len(fig.data) == 1


def test_empty_trend_does_not_crash():
    fig = build_trend_figure([])
    assert fig.data[0].x == ()


def test_single_month_does_not_crash():
    fig = build_trend_figure([{"month": "2026-07", "value": 50_000, "has_record": True}])
    assert fig.data[0].y[0] == 50_000


def _alloc(*rows):
    return [{"bdm_code": f"B{i}", "bdm_name": n, "territory": t, "total_visits": v, "pct_to_valuable_outlets": p}
            for i, (n, t, v, p) in enumerate(rows)]


def test_time_allocation_defaults_to_lowest_first():
    alloc = _alloc(("A", "X", 100, 60.0), ("B", "Y", 100, 20.0), ("C", "Z", 100, 40.0))
    fig = build_time_allocation_figure(alloc, sort_by="lowest")
    assert list(fig.data[0].x) == [20.0, 40.0, 60.0]


def test_time_allocation_highest_first_reverses_order():
    alloc = _alloc(("A", "X", 100, 60.0), ("B", "Y", 100, 20.0), ("C", "Z", 100, 40.0))
    fig = build_time_allocation_figure(alloc, sort_by="highest")
    assert list(fig.data[0].x) == [60.0, 40.0, 20.0]


def test_time_allocation_color_bands_match_thresholds():
    alloc = _alloc(("A", "X", 100, 10.0), ("B", "Y", 100, 35.0), ("C", "Z", 100, 80.0))
    fig = build_time_allocation_figure(alloc, sort_by="lowest")
    assert list(fig.data[0].marker.color) == [LOW, MID, HIGH]


def test_time_allocation_highlights_only_the_selected_bdm():
    alloc = _alloc(("A", "X", 100, 60.0), ("B", "Y", 100, 20.0), ("C", "Z", 100, 40.0))
    fig = build_time_allocation_figure(alloc, sort_by="lowest", highlight_bdm_code="B1")
    assert list(fig.data[0].marker.line.width) == [3, 0, 0]  # B1 ("B") sorts first at 20.0


def test_time_allocation_no_highlight_when_no_bdm_selected():
    alloc = _alloc(("A", "X", 100, 60.0), ("B", "Y", 100, 20.0))
    fig = build_time_allocation_figure(alloc, sort_by="lowest")
    assert list(fig.data[0].marker.line.width) == [0, 0]


def test_confidence_mix_orders_verified_partial_unverified():
    fig = build_confidence_mix_figure({"Unverified": 5, "Verified": 20, "Partial": 10})
    assert list(fig.data[0].y) == ["Verified", "Partial", "Unverified"]
    assert list(fig.data[0].x) == [20, 10, 5]


def test_confidence_mix_handles_missing_keys():
    fig = build_confidence_mix_figure({"Partial": 3})
    assert list(fig.data[0].y) == ["Partial"]


def test_anomaly_breakdown_sorts_ascending_for_readable_bar_lengths():
    fig = build_anomaly_breakdown_figure({"Tight pacing": 5, "Wrong territory": 20, "Daily volume": 12})
    assert list(fig.data[0].x) == [5, 12, 20]
    assert list(fig.data[0].y) == ["Tight pacing", "Daily volume", "Wrong territory"]
