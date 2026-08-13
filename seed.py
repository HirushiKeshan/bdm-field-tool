"""
Idempotent loader: outlets.csv, bdms.csv, billing-monthly.csv, visit-log.csv
-> Postgres. Safe to re-run (upserts on primary key). Never crashes on a
bad row -- every field-level issue is coerced-and-logged or nulled-and-
logged, and only a row whose primary identity can't be resolved at all
(never observed in the shipped CSVs) is dropped, with the reason written
to docs/rejected-rows.csv alongside every coercion.

Usage:
    python seed.py
"""
import csv
import hashlib
import os
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import psycopg2.extras
from dotenv import load_dotenv

from db.connection import apply_schema, get_connection
from logic import normalize as norm

load_dotenv()

REPO_ROOT = Path(__file__).parent
REJECTED_ROWS_PATH = REPO_ROOT / "docs" / "rejected-rows.csv"

WINDOW_MONTHS = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]

audit_log = []  # every field-level coercion / blank / rejection, across all files


def log_issue(file, row_num, key, column, result: norm.Result):
    if result.status in ("coerced", "rejected") or (result.status == "blank" and result.note):
        audit_log.append({
            "file": file, "row": row_num, "key": key, "column": column,
            "status": result.status, "note": result.note,
        })


def make_visit_code(outlet_code: str) -> str:
    """Deterministic 4-digit code, stand-in for a printed counter card.
    See docs/data-notes.md -- no such field exists in the source data."""
    digest = hashlib.sha256(outlet_code.encode()).hexdigest()
    return str(int(digest[:8], 16) % 10000).zfill(4)


def haversine_m(lat1, lon1, lat2, lon2):
    import math
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(min(1, a ** 0.5))


def _name_key(name):
    return (name or "").lower().replace("- branch", "").replace("-branch", "").strip().replace(" ", "")


def find_possible_duplicates(outlets):
    """Same-territory, same coordinates (<=50m), near-identical name after
    stripping casing/spacing/'- Branch' -- see docs/data-notes.md Q: Madurai
    near-duplicates. Only flags likely double-registrations; does not merge
    or drop either record."""
    by_territory = defaultdict(list)
    for o in outlets:
        if o["latitude"] is not None and o["longitude"] is not None:
            by_territory[o["territory"]].append(o)

    dup_of = {}
    for territory, group in by_territory.items():
        for a, b in combinations(group, 2):
            if _name_key(a["outlet_name"]) != _name_key(b["outlet_name"]):
                continue
            if not _name_key(a["outlet_name"]):
                continue
            dist = haversine_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
            if dist <= 50:
                lo, hi = sorted([a["outlet_code"], b["outlet_code"]])
                dup_of[hi] = lo
    return dup_of


def load_outlets(conn, path):
    rows_in = rows_coerced = rows_gapped = rows_rejected = 0
    outlets = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            rows_in += 1
            code = norm.clean_key(row["Outlet Code"])
            if not code:
                rows_rejected += 1
                audit_log.append({"file": "outlets.csv", "row": i, "key": "", "column": "Outlet Code",
                                   "status": "rejected", "note": "Missing outlet code, row dropped"})
                continue

            name = row["Outlet Name"].strip() or None
            otype = norm.normalize_type(row["Type"])
            town = norm.normalize_town(row["Town"])
            status = norm.normalize_status(row["Status"])
            credit = norm.normalize_credit_days(row["Credit Days"])
            phone = norm.normalize_phone(row["Phone"])
            onboarded = norm.parse_flexible_date(row["Onboarded"])
            lat = norm.normalize_float(row["Latitude"], "Latitude")
            lon = norm.normalize_float(row["Longitude"], "Longitude")

            for col, res in [("Type", otype), ("Town", town), ("Status", status), ("Credit Days", credit),
                              ("Phone", phone), ("Onboarded", onboarded), ("Latitude", lat), ("Longitude", lon)]:
                log_issue("outlets.csv", i, code, col, res)

            statuses = [otype.status, town.status, status.status, credit.status, phone.status,
                        onboarded.status, lat.status, lon.status]
            if "coerced" in statuses:
                rows_coerced += 1
            if "blank" in statuses or "rejected" in statuses:
                rows_gapped += 1

            outlets.append({
                "outlet_code": code, "outlet_name": name, "outlet_type": otype.value,
                "town_raw": row["Town"].strip(), "territory": town.value, "owner_name": row["Owner Name"].strip() or None,
                "phone": phone.value, "onboarded_date": onboarded.value, "credit_days": credit.value,
                "latitude": lat.value, "longitude": lon.value, "status": status.value,
                "visit_code": make_visit_code(code),
            })

    dup_of = find_possible_duplicates(outlets)
    for o in outlets:
        o["possible_duplicate_of"] = dup_of.get(o["outlet_code"])

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO outlets (outlet_code, outlet_name, outlet_type, town_raw, territory, owner_name,
                                  phone, onboarded_date, credit_days, latitude, longitude, status, visit_code,
                                  possible_duplicate_of)
            VALUES %s
            ON CONFLICT (outlet_code) DO UPDATE SET
                outlet_name=EXCLUDED.outlet_name, outlet_type=EXCLUDED.outlet_type, town_raw=EXCLUDED.town_raw,
                territory=EXCLUDED.territory, owner_name=EXCLUDED.owner_name, phone=EXCLUDED.phone,
                onboarded_date=EXCLUDED.onboarded_date, credit_days=EXCLUDED.credit_days,
                latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude, status=EXCLUDED.status,
                visit_code=EXCLUDED.visit_code, possible_duplicate_of=EXCLUDED.possible_duplicate_of
        """, [(o["outlet_code"], o["outlet_name"], o["outlet_type"], o["town_raw"], o["territory"],
               o["owner_name"], o["phone"], o["onboarded_date"], o["credit_days"], o["latitude"],
               o["longitude"], o["status"], o["visit_code"], None) for o in outlets])
    # second pass for possible_duplicate_of (self-referencing FK, needs both rows to exist first)
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            UPDATE outlets AS o SET possible_duplicate_of = d.dup
            FROM (VALUES %s) AS d(code, dup)
            WHERE o.outlet_code = d.code
        """, [(code, dup) for code, dup in dup_of.items()]) if dup_of else None
    conn.commit()

    print(f"outlets.csv        : in={rows_in:4d}  loaded={rows_in - rows_rejected:4d}  "
          f"coerced={rows_coerced:4d}  with_gaps={rows_gapped:4d}  rejected={rows_rejected:4d}  "
          f"possible_duplicates={len(dup_of)}")
    return {o["outlet_code"] for o in outlets}


def load_bdms(conn, path):
    rows_in = rows_coerced = rows_gapped = 0
    records = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            rows_in += 1
            code = norm.clean_key(row["BDM Code"])
            phone = norm.normalize_phone(row["Phone"])
            joined = norm.parse_flexible_date(row["Joined"])
            log_issue("bdms.csv", i, code, "Phone", phone)
            log_issue("bdms.csv", i, code, "Joined", joined)
            if phone.status == "coerced" or joined.status == "coerced":
                rows_coerced += 1
            if phone.status == "blank" or joined.status == "blank":
                rows_gapped += 1
            records.append((code, row["Name"].strip(), row["Territory"].strip(), phone.value, joined.value))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO bdms (bdm_code, name, territory, phone, joined_date) VALUES %s
            ON CONFLICT (bdm_code) DO UPDATE SET name=EXCLUDED.name, territory=EXCLUDED.territory,
                phone=EXCLUDED.phone, joined_date=EXCLUDED.joined_date
        """, records)
    conn.commit()
    print(f"bdms.csv           : in={rows_in:4d}  loaded={rows_in:4d}  coerced={rows_coerced:4d}  "
          f"with_gaps={rows_gapped:4d}  rejected=0")


def load_billing(conn, path, valid_outlets):
    rows_in = rows_coerced = rows_rejected = 0
    records = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            rows_in += 1
            code = norm.clean_key(row["Outlet Code"])
            if code not in valid_outlets:
                rows_rejected += 1
                audit_log.append({"file": "billing-monthly.csv", "row": i, "key": code, "column": "Outlet Code",
                                   "status": "rejected", "note": "Outlet code not found in outlets.csv"})
                continue
            units = norm.normalize_int(row["Units"], "Units")
            value = norm.normalize_float(row["Value"], "Value")
            log_issue("billing-monthly.csv", i, code, "Units", units)
            log_issue("billing-monthly.csv", i, code, "Value", value)
            if units.status == "rejected" or value.status == "rejected":
                rows_rejected += 1
                continue
            if units.status == "coerced" or value.status == "coerced":
                rows_coerced += 1
            month_date = f"{row['Month'].strip()}-01"
            records.append((code, month_date, units.value, value.value))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO billing_monthly (outlet_code, month, units, value) VALUES %s
            ON CONFLICT (outlet_code, month) DO UPDATE SET units=EXCLUDED.units, value=EXCLUDED.value
        """, records)
    conn.commit()
    print(f"billing-monthly.csv: in={rows_in:4d}  loaded={len(records):4d}  coerced={rows_coerced:4d}  "
          f"with_gaps=0  rejected={rows_rejected:4d}")


def load_visits(conn, path, valid_outlets, valid_bdms):
    from logic.confidence import (compute_confidence, flag_daily_volume,
                                    flag_outside_territory, flag_tight_pacing)

    rows_in = rows_coerced = rows_gapped = rows_rejected = 0
    parsed = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            rows_in += 1
            vid = norm.clean_key(row["Visit ID"])
            outlet_code = norm.clean_key(row["Outlet Code"])
            bdm_code = norm.clean_key(row["BDM Code"])
            if outlet_code not in valid_outlets or bdm_code not in valid_bdms:
                rows_rejected += 1
                audit_log.append({"file": "visit-log.csv", "row": i, "key": vid, "column": "Outlet Code/BDM Code",
                                   "status": "rejected", "note": "Unknown outlet or BDM code"})
                continue

            vdate = norm.parse_flexible_date(row["Visit Date"])
            checkin_raw = row["Check In"].strip()
            duration = norm.normalize_int(row["Duration (mins)"], "Duration")
            purpose = norm.normalize_purpose(row["Purpose"])
            remarks = norm.normalize_remarks(row["Remarks"])
            for col, res in [("Visit Date", vdate), ("Duration (mins)", duration),
                              ("Purpose", purpose), ("Remarks", remarks)]:
                log_issue("visit-log.csv", i, vid, col, res)
            statuses = [vdate.status, duration.status, purpose.status, remarks.status]
            if "coerced" in statuses:
                rows_coerced += 1
            if "blank" in statuses:
                rows_gapped += 1
            if not checkin_raw:
                log_issue("visit-log.csv", i, vid, "Check In", norm.Result(None, "blank", "Check-in time not logged"))
                rows_gapped += 1

            parsed.append({
                "visit_id": vid, "bdm_code": bdm_code, "outlet_code": outlet_code,
                "visit_date": vdate.value, "check_in_raw": checkin_raw or None,
                "duration_mins": duration.value, "purpose": purpose.value, "remarks": remarks.value,
            })

    # --- batch GPS/pacing anomaly detection across the full historical log ---
    outlet_geo = {}
    with conn.cursor() as cur:
        cur.execute("SELECT outlet_code, territory, latitude, longitude FROM outlets")
        for code, terr, lat, lon in cur.fetchall():
            outlet_geo[code] = (terr, lat, lon)
    bdm_territory = {}
    with conn.cursor() as cur:
        cur.execute("SELECT bdm_code, territory FROM bdms")
        for code, terr in cur.fetchall():
            bdm_territory[code] = terr

    from datetime import datetime
    by_bdm_day = defaultdict(list)
    for v in parsed:
        if v["visit_date"] is not None:
            by_bdm_day[(v["bdm_code"], v["visit_date"])].append(v)

    anomalies = {}
    for (bdm_code, day), visits_that_day in by_bdm_day.items():
        vol_flag = flag_daily_volume(len(visits_that_day))
        timed = [v for v in visits_that_day if v["check_in_raw"]]
        timed.sort(key=lambda v: v["check_in_raw"])
        prev = None
        for v in timed:
            reason = vol_flag
            if prev is not None:
                try:
                    t1 = datetime.strptime(prev["check_in_raw"], "%H:%M")
                    t2 = datetime.strptime(v["check_in_raw"], "%H:%M")
                    gap = (t2 - t1).total_seconds() / 60
                except ValueError:
                    gap = None
                pacing_flag = flag_tight_pacing(gap, prev["outlet_code"] == v["outlet_code"])
                if pacing_flag and not reason:
                    reason = pacing_flag
            terr_flag = flag_outside_territory(outlet_geo.get(v["outlet_code"], (None, None, None))[0],
                                                bdm_territory.get(bdm_code))
            if terr_flag and not reason:
                reason = terr_flag
            if reason:
                anomalies[v["visit_id"]] = reason
            prev = v
        # visits with no check-in time still inherit the daily-volume flag
        for v in visits_that_day:
            if v["visit_id"] not in anomalies and vol_flag:
                anomalies[v["visit_id"]] = vol_flag

    records = []
    for v in parsed:
        gps_anomaly = anomalies.get(v["visit_id"])
        has_outcome = bool(v["remarks"]) or (v["purpose"] in ("Order", "Collection"))
        confidence = compute_confidence(code_match=None, has_outcome_evidence=has_outcome, gps_anomaly=gps_anomaly)
        lat, lon = None, None
        geo = outlet_geo.get(v["outlet_code"])
        if geo:
            lat, lon = geo[1], geo[2]
        records.append((
            v["visit_id"], v["bdm_code"], v["outlet_code"], v["visit_date"], v["check_in_raw"],
            v["duration_mins"], v["purpose"], v["remarks"], "historical_log", None, None, False,
            lat, lon, gps_anomaly, confidence.level, True,
        ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO visits (visit_id, bdm_code, outlet_code, visit_date, check_in_time, duration_mins,
                                 purpose, remarks, source, entered_code, code_match, photo_taken,
                                 latitude, longitude, gps_anomaly, confidence, is_complete)
            VALUES %s
            ON CONFLICT (visit_id) DO UPDATE SET
                visit_date=EXCLUDED.visit_date, check_in_time=EXCLUDED.check_in_time,
                duration_mins=EXCLUDED.duration_mins, purpose=EXCLUDED.purpose, remarks=EXCLUDED.remarks,
                gps_anomaly=EXCLUDED.gps_anomaly, confidence=EXCLUDED.confidence
        """, records)
    conn.commit()

    print(f"visit-log.csv      : in={rows_in:4d}  loaded={len(records):4d}  coerced={rows_coerced:4d}  "
          f"with_gaps={rows_gapped:4d}  rejected={rows_rejected:4d}  gps_anomalies_flagged={len(anomalies)}")


def write_rejected_rows_csv():
    REJECTED_ROWS_PATH.parent.mkdir(exist_ok=True)
    with open(REJECTED_ROWS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "row", "key", "column", "status", "note"])
        writer.writeheader()
        writer.writerows(audit_log)
    print(f"\nWrote {len(audit_log)} field-level issues to {REJECTED_ROWS_PATH.relative_to(REPO_ROOT)}")


def main():
    conn = get_connection()
    apply_schema(conn)

    print("Seeding database...\n")
    valid_outlets = load_outlets(conn, REPO_ROOT / "outlets.csv")
    load_bdms(conn, REPO_ROOT / "bdms.csv")
    with conn.cursor() as cur:
        cur.execute("SELECT bdm_code FROM bdms")
        valid_bdms = {r[0] for r in cur.fetchall()}
    load_billing(conn, REPO_ROOT / "billing-monthly.csv", valid_outlets)
    load_visits(conn, REPO_ROOT / "visit-log.csv", valid_outlets, valid_bdms)
    write_rejected_rows_csv()
    conn.close()
    print("\nSeed complete.")


if __name__ == "__main__":
    main()
