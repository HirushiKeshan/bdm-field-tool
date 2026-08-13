"""
Every coercion rule found during Phase 0 (see docs/data-notes.md), in one
place, shared by seed.py and the app. Nothing here invents a value: a
function either returns a cleaned value plus a status of "ok"/"coerced",
or returns None plus a status of "blank"/"rejected" and a human-readable
note. Callers decide what a None means in context (never a silent 0).
"""
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

TOWN_TO_TERRITORY = {
    "karur": "Karur", "vellore": "Vellore", "trichy": "Trichy",
    "tiruchirappalli": "Trichy", "tirunelveli": "Tirunelveli", "nellai": "Tirunelveli",
    "erode": "Erode", "coimbatore": "Coimbatore", "cbe": "Coimbatore",
    "salem": "Salem", "dindigul": "Dindigul", "thanjavur": "Thanjavur",
    "tanjore": "Thanjavur", "tiruppur": "Tirupur", "tirupur": "Tirupur",
    "chennai": "Chennai", "madras": "Chennai", "madurai": "Madurai", "mdu": "Madurai",
}

STATUS_MAP = {"active": "Active", "dormant": "Dormant", "hold": "Hold", "inactive": "Inactive"}

PURPOSE_MAP = {
    "routine visit": "Routine visit", "routine": "Routine visit",
    "followup": "Follow up", "follow up": "Follow up",
    "collection": "Collection", "order": "Order", "complaint": "Complaint",
    "new onboarding": "New onboarding", "stock check": "Stock check",
}

_DATE_PATTERNS = [
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "%d/%m/%Y"),
    (re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2}$"), "%d-%b-%y"),
]


@dataclass
class Result:
    value: object
    status: str  # "ok" | "coerced" | "blank" | "rejected"
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "coerced")


def clean_key(raw: str) -> str:
    """Trim whitespace on join keys (Outlet Code / BDM Code). Defensive: none
    of the shipped CSVs had padded keys, but a join must not silently fail
    if a future export does."""
    return (raw or "").strip()


def normalize_town(raw: str) -> Result:
    key = (raw or "").strip().lower()
    if not key:
        return Result(None, "blank", "Town not recorded")
    territory = TOWN_TO_TERRITORY.get(key)
    if territory is None:
        return Result(None, "rejected", f"Unrecognized town spelling: {raw!r}")
    status = "ok" if territory.lower() == key else "coerced"
    return Result(territory, status, "" if status == "ok" else f"{raw!r} -> {territory}")


def normalize_status(raw: str) -> Result:
    key = (raw or "").strip().lower()
    if not key:
        return Result(None, "blank", "Status not recorded")
    canonical = STATUS_MAP.get(key)
    if canonical is None:
        return Result(None, "rejected", f"Unrecognized status: {raw!r}")
    status = "ok" if canonical == raw else "coerced"
    return Result(canonical, status)


def normalize_type(raw: str) -> Result:
    val = (raw or "").strip()
    if not val:
        return Result(None, "blank", "Outlet type not recorded")
    return Result(val, "ok")


def normalize_credit_days(raw: str) -> Result:
    val = (raw or "").strip().lower()
    if not val:
        return Result(None, "blank", "Credit terms not recorded")
    if val == "cod":
        return Result(0, "coerced", "COD -> 0 credit days")
    m = re.match(r"^(\d+)\s*days?$", val)
    if m:
        return Result(int(m.group(1)), "coerced", f"{raw!r} -> {m.group(1)}")
    if val.isdigit():
        return Result(int(val), "ok")
    return Result(None, "rejected", f"Unparseable credit days: {raw!r}")


def normalize_phone(raw: str) -> Result:
    val = (raw or "").strip()
    if not val or val == "0":
        return Result(None, "blank", "No phone on file")
    digits = re.sub(r"\D", "", val)
    if len(digits) == 10:
        return Result(digits, "ok" if digits == val else "coerced")
    if len(digits) == 12 and digits.startswith("91"):
        return Result(digits[2:], "coerced", f"{raw!r} -> stripped +91 prefix")
    return Result(None, "rejected", f"Unparseable phone: {raw!r}")


def parse_flexible_date(raw: str) -> Result:
    val = (raw or "").strip()
    if not val:
        return Result(None, "blank", "Date not recorded")
    for pattern, fmt in _DATE_PATTERNS:
        if pattern.match(val):
            try:
                from datetime import datetime
                d = datetime.strptime(val, fmt).date()
                status = "ok" if fmt == "%Y-%m-%d" else "coerced"
                return Result(d, status, "" if status == "ok" else f"{raw!r} parsed as {fmt}")
            except ValueError:
                return Result(None, "rejected", f"Invalid date value: {raw!r}")
    return Result(None, "rejected", f"Unrecognized date format: {raw!r}")


def normalize_purpose(raw: str) -> Result:
    key = (raw or "").strip().lower()
    if not key:
        return Result(None, "blank", "Purpose not logged")
    canonical = PURPOSE_MAP.get(key)
    if canonical is None:
        return Result(None, "rejected", f"Unrecognized visit purpose: {raw!r}")
    status = "ok" if canonical == raw else "coerced"
    return Result(canonical, status)


def normalize_remarks(raw: str) -> Result:
    val = (raw or "").strip()
    if not val:
        return Result(None, "blank", "Outcome not logged")
    return Result(val, "ok")


def normalize_int(raw: str, field_name: str = "value") -> Result:
    val = (raw or "").strip()
    if not val:
        return Result(None, "blank", f"{field_name} not recorded")
    try:
        return Result(int(val), "ok")
    except ValueError:
        try:
            return Result(int(float(val)), "coerced", f"{raw!r} -> int")
        except ValueError:
            return Result(None, "rejected", f"Unparseable {field_name}: {raw!r}")


def normalize_float(raw: str, field_name: str = "value") -> Result:
    val = (raw or "").strip()
    if not val:
        return Result(None, "blank", f"{field_name} not recorded")
    try:
        return Result(float(val), "ok")
    except ValueError:
        return Result(None, "rejected", f"Unparseable {field_name}: {raw!r}")
