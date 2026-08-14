"""
Postgres TIMESTAMPTZ columns store an absolute instant and psycopg2 hands it
back UTC -- but every BDM reading a screen is in India. Without converting,
a visit made at 7:58 PM IST shows up as 2:24 PM. IST has no daylight saving,
so a fixed +5:30 offset is correct year-round and needs no timezone database
(the embedded local Postgres used for dev doesn't ship one).
"""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(timezone.utc).astimezone(IST)


def to_ist(dt: datetime) -> datetime:
    """Converts a TIMESTAMPTZ-sourced datetime to IST for display. Treats a
    naive datetime as already UTC, since that's what an un-configured
    Postgres connection would otherwise hand back."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)
