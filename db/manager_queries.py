"""
Phase 4 -- one manager page, five sections. Every number here is computed
from the same outlets/billing/visits tables the BDM app reads, not a
separate rollup -- so the manager view can never show something the data
doesn't support.
"""
from collections import defaultdict

from db.queries import fetch_bdms, fetch_billing_rows, fetch_outlets, fetch_visit_recency, fetch_window_months
from logic.segmentation import compute_valuable_threshold, segment_outlet

BILLING_OUTLET_SEGMENTS = {"Core", "Slipping", "Dormant-valuable", "Dormant-low"}  # excludes New/Never


def _all_segments(conn):
    outlets = fetch_outlets(conn)
    billing = fetch_billing_rows(conn)
    window_months = fetch_window_months(conn)
    all_rows = {o["outlet_code"]: billing.get(o["outlet_code"], []) for o in outlets}
    threshold = compute_valuable_threshold(all_rows, window_months)
    segments = {code: segment_outlet(rows, window_months, threshold) for code, rows in all_rows.items()}
    return outlets, segments


def coverage_gaps(conn, days_threshold: int = 30) -> dict:
    outlets, segments = _all_segments(conn)
    recency = fetch_visit_recency(conn)
    bdm_by_territory = {b["territory"]: b["name"] for b in fetch_bdms(conn)}

    billing_outlets = [o for o in outlets if segments[o["outlet_code"]].segment != "New/Never"]
    not_visited, visited_recently = [], []
    for o in billing_outlets:
        code = o["outlet_code"]
        rec = recency.get(code)
        days_since = rec["days_since"] if rec else None
        entry = {
            "outlet_code": code,
            "outlet_name": o["outlet_name"] or f"Unnamed outlet ({code})",
            "territory": o["territory"],
            "bdm_name": bdm_by_territory.get(o["territory"], "Unassigned"),
            "segment": segments[code].segment,
            "days_since_last_visit": days_since,
        }
        if days_since is None or days_since > days_threshold:
            not_visited.append(entry)
        else:
            visited_recently.append(entry)

    not_visited.sort(key=lambda x: (x["days_since_last_visit"] is not None, x["days_since_last_visit"] or 9999), reverse=True)
    return {
        "total_billing_outlets": len(billing_outlets),
        "visited_recently_count": len(visited_recently),
        "not_visited": not_visited,
    }


def time_allocation_by_bdm(conn) -> list:
    outlets, segments = _all_segments(conn)
    seg_by_code = {o["outlet_code"]: segments[o["outlet_code"]].segment for o in outlets}

    with conn.cursor() as cur:
        cur.execute("SELECT bdm_code, outlet_code FROM visits WHERE outlet_code IS NOT NULL")
        visits = cur.fetchall()

    bdms = {b["bdm_code"]: b for b in fetch_bdms(conn)}
    per_bdm = defaultdict(lambda: {"total": 0, "valuable": 0, "low_value": 0})
    for bdm_code, outlet_code in visits:
        seg = seg_by_code.get(outlet_code)
        bucket = per_bdm[bdm_code]
        bucket["total"] += 1
        if seg in ("Core", "Slipping", "Dormant-valuable"):
            bucket["valuable"] += 1
        else:
            bucket["low_value"] += 1

    result = []
    for bdm_code, b in bdms.items():
        bucket = per_bdm.get(bdm_code, {"total": 0, "valuable": 0, "low_value": 0})
        pct_valuable = (bucket["valuable"] / bucket["total"] * 100) if bucket["total"] else 0.0
        result.append({
            "bdm_name": b["name"], "territory": b["territory"], "total_visits": bucket["total"],
            "pct_to_valuable_outlets": round(pct_valuable, 1),
        })
    result.sort(key=lambda x: x["pct_to_valuable_outlets"])
    return result


def conversation_quality(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT confidence, COUNT(*) FROM visits GROUP BY confidence")
        confidence_mix = dict(cur.fetchall())
        cur.execute("SELECT COUNT(*) FROM visits")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM visits WHERE remarks IS NULL AND (purpose IS NULL OR purpose NOT IN ('Order','Collection'))")
        no_outcome = cur.fetchone()[0]
        # Checklist completion only means something for visits that went
        # through this app's checklist -- historical rows are seeded with
        # is_complete=True as "a finished log entry", which would read as a
        # meaningless 100% otherwise. See docs/ai-log.md.
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_complete) FROM visits WHERE source = 'app'")
        app_total, app_complete = cur.fetchone()
    return {
        "total_visits": total,
        "confidence_mix": confidence_mix,
        "pct_no_outcome": round(no_outcome / total * 100, 1) if total else 0.0,
        "app_visit_count": app_total,
        "pct_checklist_complete": round(app_complete / app_total * 100, 1) if app_total else None,
    }


def recovery_pipeline(conn) -> list:
    outlets, segments = _all_segments(conn)
    recency = fetch_visit_recency(conn)
    bdm_by_territory = {b["territory"]: b["name"] for b in fetch_bdms(conn)}

    pipeline = []
    for o in outlets:
        seg = segments[o["outlet_code"]]
        if seg.segment != "Dormant-valuable":
            continue
        code = o["outlet_code"]
        rec = recency.get(code)
        pipeline.append({
            "outlet_code": code,
            "outlet_name": o["outlet_name"] or f"Unnamed outlet ({code})",
            "territory": o["territory"],
            "owner_bdm": bdm_by_territory.get(o["territory"], "Unassigned"),
            "months_quiet": seg.months_since_last_bill,
            "used_to_do_per_month": seg.avg_positive_value,
            "days_since_last_visit": rec["days_since"] if rec else None,
        })
    pipeline.sort(key=lambda x: x["used_to_do_per_month"] or 0, reverse=True)
    return pipeline


def _classify_anomaly(reason: str) -> str:
    if reason is None:
        return "none"
    if "visits logged by this BDM" in reason:
        return "Implausible daily volume"
    if "min since previous check-in" in reason:
        return "Impossibly tight pacing between outlets"
    if "Outlet is in" in reason:
        return "Visit outside assigned territory"
    if "km from the outlet's registered address" in reason:
        return "Device GPS far from outlet address"
    return "Other"


def log_integrity(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT gps_anomaly FROM visits WHERE gps_anomaly IS NOT NULL")
        reasons = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM visits")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM outlets WHERE possible_duplicate_of IS NOT NULL")
        duplicate_pairs = cur.fetchone()[0]

    breakdown = defaultdict(int)
    for r in reasons:
        breakdown[_classify_anomaly(r)] += 1

    return {
        "total_visits": total,
        "flagged_visits": len(reasons),
        "pct_flagged": round(len(reasons) / total * 100, 1) if total else 0.0,
        "breakdown": dict(breakdown),
        "possible_duplicate_outlet_pairs": duplicate_pairs,
    }
