"""
Every case here is a real value pulled from outlets.csv / visit-log.csv
during Phase 0 (see docs/data-notes.md), not synthetic data -- these are
the rows that actually broke a naive parse.
"""
from datetime import date

from logic.normalize import (
    normalize_credit_days,
    normalize_phone,
    normalize_purpose,
    normalize_status,
    normalize_town,
    parse_flexible_date,
)


def test_town_casing_and_synonyms_collapse_to_territory():
    for raw, expected in [
        ("KARUR", "Karur"), ("karur", "Karur"), ("Karur", "Karur"),
        ("Madras", "Chennai"), ("Mdu", "Madurai"), ("MADURAI", "Madurai"),
        ("Tanjore", "Thanjavur"), ("CBE", "Coimbatore"), ("Cbe", "Coimbatore"),
        ("Tiruchirappalli", "Trichy"), ("trichy", "Trichy"), ("TRICHY", "Trichy"),
        ("Nellai", "Tirunelveli"), ("TIRUNELVELI", "Tirunelveli"),
        ("tirupur", "Tirupur"), ("Tiruppur", "Tirupur"), ("TIRUPUR", "Tirupur"),
    ]:
        result = normalize_town(raw)
        assert result.ok, f"{raw!r} should have normalized"
        assert result.value == expected, f"{raw!r} -> {result.value}, expected {expected}"


def test_town_unrecognized_is_rejected_not_guessed():
    result = normalize_town("Pondicherry")
    assert result.status == "rejected"
    assert result.value is None


def test_status_casing_collapses_and_blank_is_not_defaulted():
    assert normalize_status("Active").value == "Active"
    assert normalize_status("ACTIVE").value == "Active"
    assert normalize_status("active").value == "Active"
    assert normalize_status("dormant").value == "Dormant"
    blank = normalize_status("")
    assert blank.status == "blank"
    assert blank.value is None  # never defaulted to "Active"


def test_credit_days_mixed_representations():
    assert normalize_credit_days("30").value == 30
    assert normalize_credit_days("30 days").value == 30
    assert normalize_credit_days("COD").value == 0
    assert normalize_credit_days("0").value == 0
    blank = normalize_credit_days("")
    assert blank.status == "blank"
    assert blank.value is None  # blank terms is NOT the same as COD's 0


def test_onboarded_date_three_real_formats():
    assert parse_flexible_date("22/12/2024").value == date(2024, 12, 22)
    assert parse_flexible_date("2020-11-17").value == date(2020, 11, 17)
    assert parse_flexible_date("06-Oct-22").value == date(2022, 10, 6)


def test_visit_date_slash_format_is_day_first_not_month_first():
    # 31/... could only be DD/MM; confirms the format assumption is safe.
    assert parse_flexible_date("31/07/2026").value == date(2026, 7, 31)
    assert parse_flexible_date("05/05/2026").value == date(2026, 5, 5)


def test_phone_formats_from_source():
    assert normalize_phone("6786043810").value == "6786043810"
    assert normalize_phone("+91 88889 93434").value == "8888993434"
    assert normalize_phone("916495562933").value == "6495562933"
    assert normalize_phone("60934-07894").value == "6093407894"
    zero = normalize_phone("0")
    assert zero.status == "blank"  # "0" is a placeholder, not a real number
    blank = normalize_phone("")
    assert blank.status == "blank"


def test_purpose_casing_collapses():
    assert normalize_purpose("Routine visit").value == "Routine visit"
    assert normalize_purpose("routine").value == "Routine visit"
    assert normalize_purpose("followup").value == "Follow up"
    assert normalize_purpose("Follow up").value == "Follow up"
    blank = normalize_purpose("")
    assert blank.status == "blank"
    assert blank.value is None
