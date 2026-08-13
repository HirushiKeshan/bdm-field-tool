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


def _bdm_territory(conn, bdm_code):
    if not bdm_code:
        return None
    for b in fetch_bdms(conn):
        if b["bdm_code"] == bdm_code:
            return b["territory"]
    return None


def coverage_gaps(conn, days_threshold: int = 30, bdm_code: str = None) -> dict:
    outlets, segments = _all_segments(conn)
    recency = fetch_visit_recency(conn)
    bdm_by_territory = {b["territory"]: b["name"] for b in fetch_bdms(conn)}

    territory = _bdm_territory(conn, bdm_code)
    if territory:
        outlets = [o for o in outlets if o["territory"] == territory]

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
            "bdm_code": bdm_code, "bdm_name": b["name"], "territory": b["territory"],
            "total_visits": bucket["total"], "pct_to_valuable_outlets": round(pct_valuable, 1),
        })
    result.sort(key=lambda x: x["pct_to_valuable_outlets"])
    return result


def conversation_quality(conn, bdm_code: str = None) -> dict:
    where = "WHERE bdm_code = %s" if bdm_code else ""
    params = (bdm_code,) if bdm_code else ()
    and_where = "AND bdm_code = %s" if bdm_code else ""
    with conn.cursor() as cur:
        cur.execute(f"SELECT confidence, COUNT(*) FROM visits {where} GROUP BY confidence", params)
        confidence_mix = dict(cur.fetchall())
        cur.execute(f"SELECT COUNT(*) FROM visits {where}", params)
        total = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM visits WHERE remarks IS NULL AND "
                    f"(purpose IS NULL OR purpose NOT IN ('Order','Collection')) {and_where}", params)
        no_outcome = cur.fetchone()[0]
        # Checklist completion only means something for visits that went
        # through this app's checklist -- historical rows are seeded with
        # is_complete=True as "a finished log entry", which would read as a
        # meaningless 100% otherwise. See docs/ai-log.md.
        cur.execute(f"SELECT COUNT(*), COUNT(*) FILTER (WHERE is_complete) FROM visits "
                    f"WHERE source = 'app' {and_where}", params)
        app_total, app_complete = cur.fetchone()
    return {
        "total_visits": total,
        "confidence_mix": confidence_mix,
        "pct_no_outcome": round(no_outcome / total * 100, 1) if total else 0.0,
        "app_visit_count": app_total,
        "pct_checklist_complete": round(app_complete / app_total * 100, 1) if app_total else None,
    }


def recovery_pipeline(conn, bdm_code: str = None) -> list:
    outlets, segments = _all_segments(conn)
    recency = fetch_visit_recency(conn)
    bdm_by_territory = {b["territory"]: b["name"] for b in fetch_bdms(conn)}

    territory = _bdm_territory(conn, bdm_code)
    if territory:
        outlets = [o for o in outlets if o["territory"] == territory]

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


def log_integrity(conn, bdm_code: str = None) -> dict:
    and_where = "AND bdm_code = %s" if bdm_code else ""
    params = (bdm_code,) if bdm_code else ()
    territory = _bdm_territory(conn, bdm_code)
    with conn.cursor() as cur:
        cur.execute(f"SELECT gps_anomaly FROM visits WHERE gps_anomaly IS NOT NULL {and_where}", params)
        reasons = [r[0] for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM visits WHERE 1=1 {and_where}", params)
        total = cur.fetchone()[0]
        if territory:
            cur.execute("SELECT COUNT(*) FROM outlets WHERE possible_duplicate_of IS NOT NULL AND territory = %s",
                        (territory,))
        else:
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


def insights_summary(conn, bdm_code: str = None) -> dict:
    """Compact snapshot of everything the Insights page renders, for the
    AI question box -- the SAME aggregates the page already shows, not a
    separate rollup, so the assistant can never answer with a number that
    isn't visible on screen. Outlet-level lists are capped at 10 -- the
    scale of the problem (counts, percentages) matters far more to a
    question-answering model than every individual row."""
    cov = coverage_gaps(conn, days_threshold=30, bdm_code=bdm_code)
    alloc = time_allocation_by_bdm(conn)
    if bdm_code:
        alloc = [r for r in alloc if r["bdm_code"] == bdm_code]
    cq = conversation_quality(conn, bdm_code=bdm_code)
    pipeline = recovery_pipeline(conn, bdm_code=bdm_code)
    li = log_integrity(conn, bdm_code=bdm_code)

    return {
        "scope": "all BDMs" if not bdm_code else bdm_code,
        "coverage": {
            "billing_outlets": cov["total_billing_outlets"],
            "not_visited_30d_plus": len(cov["not_visited"]),
            "worst_gaps": [
                {"outlet": o["outlet_name"], "bdm": o["bdm_name"], "days_since_visit": o["days_since_last_visit"]}
                for o in cov["not_visited"][:10]
            ],
        },
        "time_allocation_by_bdm": [
            {"bdm": r["bdm_name"], "territory": r["territory"],
             "pct_to_valuable_outlets": r["pct_to_valuable_outlets"], "total_visits": r["total_visits"]}
            for r in alloc
        ],
        "conversation_quality": {
            "total_visits": cq["total_visits"],
            "pct_no_outcome": cq["pct_no_outcome"],
            "confidence_mix": cq["confidence_mix"],
            "pct_checklist_complete": cq["pct_checklist_complete"],
        },
        "recovery_pipeline": {
            "count": len(pipeline),
            "top_outlets": [
                {"outlet": o["outlet_name"], "owner_bdm": o["owner_bdm"], "months_quiet": o["months_quiet"],
                 "used_to_do_per_month": o["used_to_do_per_month"]}
                for o in pipeline[:10]
            ],
        },
        "log_integrity": {
            "flagged_visits": li["flagged_visits"],
            "pct_flagged": li["pct_flagged"],
            "possible_duplicate_outlets": li["possible_duplicate_outlet_pairs"],
            "breakdown": li["breakdown"],
        },
    }
