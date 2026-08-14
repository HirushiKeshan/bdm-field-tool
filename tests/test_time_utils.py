from datetime import datetime, timezone

from logic.time_utils import now_ist, to_ist


def test_to_ist_converts_utc_to_plus_5_30():
    utc_dt = datetime(2026, 8, 14, 14, 24, 0, tzinfo=timezone.utc)
    result = to_ist(utc_dt)
    assert (result.hour, result.minute) == (19, 54)


def test_to_ist_rolls_over_to_next_day():
    utc_dt = datetime(2026, 8, 14, 19, 0, 0, tzinfo=timezone.utc)
    result = to_ist(utc_dt)
    assert result.day == 15
    assert (result.hour, result.minute) == (0, 30)


def test_to_ist_treats_naive_datetime_as_utc():
    naive_dt = datetime(2026, 8, 14, 14, 24, 0)
    result = to_ist(naive_dt)
    assert (result.hour, result.minute) == (19, 54)


def test_now_ist_is_five_hours_thirty_ahead_of_utc():
    diff = now_ist().utcoffset()
    assert diff.total_seconds() == 5.5 * 3600
