from logic.confidence import (
    LOCATION_MISMATCH_METERS,
    compute_confidence,
    flag_daily_volume,
    flag_location_mismatch,
    flag_outside_territory,
    flag_tight_pacing,
)

# Two real coordinates from outlets.csv, ~430m apart (Madurai, OA0099/OA0719
# from docs/data-notes.md's near-duplicate search) -- close enough that
# a naive "just tighten the threshold" instinct would be tempted to use
# this to discriminate between them. This module must not do that.
OUTLET_LAT, OUTLET_LON = 9.929, 78.119


def test_code_match_with_no_anomaly_is_verified():
    result = compute_confidence(code_match=True, has_outcome_evidence=False, gps_anomaly=None)
    assert result.level == "Verified"


def test_code_match_with_anomaly_downgrades_to_partial():
    result = compute_confidence(code_match=True, has_outcome_evidence=False, gps_anomaly="something's off")
    assert result.level == "Partial"


def test_outcome_evidence_without_code_is_partial():
    result = compute_confidence(code_match=False, has_outcome_evidence=True, gps_anomaly=None)
    assert result.level == "Partial"


def test_nothing_at_all_is_unverified():
    result = compute_confidence(code_match=False, has_outcome_evidence=False, gps_anomaly=None)
    assert result.level == "Unverified"


def test_location_mismatch_none_when_far_enough_within_threshold():
    # ~100m away -- well inside ordinary GPS error, must not flag.
    assert flag_location_mismatch(9.9299, 78.1191, 20, OUTLET_LAT, OUTLET_LON) is None


def test_location_mismatch_flags_gross_distance():
    # Chennai vs Madurai -- a code entered from the wrong city entirely.
    reason = flag_location_mismatch(13.0827, 80.2707, 15, OUTLET_LAT, OUTLET_LON)
    assert reason is not None
    assert "km" in reason


def test_location_mismatch_never_fires_within_adjacent_shop_range():
    """The Madurai guarantee: two points a few metres apart (adjacent
    counters) must never be flagged as a mismatch against each other --
    that would be using GPS to discriminate shops, which is exactly what
    the README says not to do."""
    # ~5m apart -- a shared-wall scenario.
    reason = flag_location_mismatch(OUTLET_LAT, OUTLET_LON, 10, OUTLET_LAT + 0.00004, OUTLET_LON)
    assert reason is None


def test_location_mismatch_skips_check_when_device_accuracy_is_unreliable():
    # Reported 3km away, but the device itself says its fix is only
    # accurate to 5km -- the reading isn't trustworthy enough to flag.
    reason = flag_location_mismatch(9.96, 78.15, 5000, OUTLET_LAT, OUTLET_LON)
    assert reason is None


def test_location_mismatch_none_when_any_coordinate_missing():
    assert flag_location_mismatch(None, None, None, OUTLET_LAT, OUTLET_LON) is None
    assert flag_location_mismatch(OUTLET_LAT, OUTLET_LON, 10, None, None) is None


def test_daily_volume_and_tight_pacing_thresholds_unchanged():
    assert flag_daily_volume(16) is not None
    assert flag_daily_volume(15) is None
    assert flag_tight_pacing(5, same_outlet=False) is not None
    assert flag_tight_pacing(5, same_outlet=True) is None


def test_outside_territory_unchanged():
    assert flag_outside_territory("Madurai", "Chennai") is not None
    assert flag_outside_territory("Madurai", "Madurai") is None
