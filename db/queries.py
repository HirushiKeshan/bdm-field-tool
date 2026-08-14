"""
All reads and writes the app needs, on top of psycopg2. Segmentation,
scoring, and confidence are pure functions from logic/ -- this module's
job is only to shape Postgres rows into the plain dicts/lists those
functions expect, and to persist what the app writes back.
"""
import uuid
from collections import defaultdict
from datetime import date

from logic import scoring
from logic.checklist import get_checklist_for_type, load_checklist_config
from logic.confidence import compute_confidence, flag_location_mismatch, flag_outside_territory
from logic.geo import assign_area, compute_centroids
from logic.segmentation import compute_valuable_threshold, segment_outlet

DUES_ITEM_KEY = "dues_manual_entry"


def fetch_window_months(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT to_char(month, 'YYYY-MM') FROM billing_monthly ORDER BY 1")
        return [r[0] for r in cur.fetchall()]


def fetch_bdms(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT bdm_code, name, territory, phone FROM bdms ORDER BY name")
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_outlets(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT outlet_code, outlet_name, outlet_type, town_raw, territory, owner_name,
                   phone, onboarded_date, credit_days, latitude, longitude, status, visit_code,
                   possible_duplicate_of
            FROM outlets
        """)
        cols = [c.name for c in cur.description]
        outlets = [dict(zip(cols, row)) for row in cur.fetchall()]
    duplicate_targets = {o["possible_duplicate_of"] for o in outlets if o["possible_duplicate_of"]}
    for o in outlets:
        o["is_flagged_duplicate"] = bool(o["possible_duplicate_of"]) or o["outlet_code"] in duplicate_targets
    return outlets


def fetch_billing_rows(conn) -> dict:
    rows = defaultdict(list)
    with conn.cursor() as cur:
        cur.execute("SELECT outlet_code, to_char(month, 'YYYY-MM'), value FROM billing_monthly ORDER BY month")
        for code, month, value in cur.fetchall():
            rows[code].append({"month": month, "value": float(value)})
    return dict(rows)


def fetch_visit_recency(conn) -> dict:
    """{outlet_code: {"last_visit_date": date, "days_since": int}}"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT outlet_code, MAX(visit_date) FROM visits WHERE visit_date IS NOT NULL GROUP BY outlet_code
        """)
        today = date.today()
        out = {}
        for code, last_date in cur.fetchall():
            out[code] = {"last_visit_date": last_date, "days_since": (today - last_date).days}
        return out


def fetch_latest_agreed_action(conn, outlet_code: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT action_text, status, created_at FROM agreed_actions
            WHERE outlet_code = %s ORDER BY created_at DESC LIMIT 1
        """, (outlet_code,))
        row = cur.fetchone()
        if not row:
            return None
        return {"action_text": row[0], "status": row[1], "created_at": row[2]}


def fetch_manual_dues(conn, outlet_code: str):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT vcr.response_value, vcr.created_at FROM visit_checklist_responses vcr
            JOIN visits v ON v.visit_id = vcr.visit_id
            WHERE v.outlet_code = %s AND vcr.item_key = %s
            ORDER BY vcr.created_at DESC LIMIT 1
        """, (outlet_code, DUES_ITEM_KEY))
        row = cur.fetchone()
        if not row:
            return None
        return {"amount": row[0], "updated_at": row[1]}


def fetch_recent_visits(conn, outlet_code: str, limit: int = 10) -> list:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT visit_id, bdm_code, visit_date, purpose, remarks, confidence, source
            FROM visits WHERE outlet_code = %s
            ORDER BY visit_date DESC NULLS LAST, created_at DESC LIMIT %s
        """, (outlet_code, limit))
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _value_percentile_ranks(segments: dict) -> dict:
    """0..1 percentile rank of each outlet's 'relevant value' (peak for
    dormant/new, trailing-avg-or-latest for core/slipping) among outlets
    that have ever billed. Outlets with no billing history rank at 0."""
    scored = []
    for code, seg in segments.items():
        if seg.segment == "New/Never":
            scored.append((code, 0.0))
        else:
            val = seg.trailing_avg or seg.latest_value or seg.peak_value or 0.0
            scored.append((code, val))
    scored.sort(key=lambda x: x[1])
    n = len(scored)
    ranks = {}
    for i, (code, _) in enumerate(scored):
        ranks[code] = i / (n - 1) if n > 1 else 0.0
    return ranks


def build_beat(conn, bdm_code: str, area: str = None) -> dict:
    """Everything 'My Beat' needs: ranked outlet list with segment, score,
    reason, area, duplicate flag, and days since last visit."""
    outlets = fetch_outlets(conn)
    billing = fetch_billing_rows(conn)
    recency = fetch_visit_recency(conn)
    window_months = fetch_window_months(conn)

    all_rows = {o["outlet_code"]: billing.get(o["outlet_code"], []) for o in outlets}
    threshold = compute_valuable_threshold(all_rows, window_months)
    segments = {code: segment_outlet(rows, window_months, threshold) for code, rows in all_rows.items()}
    value_ranks = _value_percentile_ranks(segments)
    centroids = compute_centroids(outlets)

    bdm = next((b for b in fetch_bdms(conn) if b["bdm_code"] == bdm_code), None)
    if bdm is None:
        return {"bdm": None, "outlets": [], "areas": []}

    territory_outlets = [o for o in outlets if o["territory"] == bdm["territory"]]

    beat = []
    for o in territory_outlets:
        code = o["outlet_code"]
        seg = segments[code]
        rec = recency.get(code)
        days_since = rec["days_since"] if rec else None
        area_label = assign_area(o["latitude"], o["longitude"], centroids.get(o["territory"]))
        priority = scoring.score_outlet(
            seg, days_since, value_ranks.get(code, 0.0), is_possible_duplicate=o["is_flagged_duplicate"]
        )
        beat.append({
            "outlet_code": code,
            "outlet_name": o["outlet_name"] or f"Unnamed outlet ({code})",
            "outlet_type": o["outlet_type"] or "Type not recorded",
            "area": area_label,
            "segment": seg.segment,
            "score": priority.score,
            "reason": priority.reason,
            "confidence_note": priority.confidence_note,
            "days_since_last_visit": days_since,
            "last_billed_value": seg.latest_value,
            "is_flagged_duplicate": o["is_flagged_duplicate"],
            "status": o["status"],
        })

    beat.sort(key=lambda x: x["score"], reverse=True)
    if area:
        beat = [b for b in beat if b["area"] == area]

    areas = sorted({assign_area(o["latitude"], o["longitude"], centroids.get(o["territory"])) for o in territory_outlets})
    return {"bdm": bdm, "outlets": beat, "areas": areas}


def get_outlet_counter_context(conn, outlet_code: str) -> dict:
    """Everything the Counter Conversation screen shows 'before you ask'."""
    all_outlets = fetch_outlets(conn)
    outlets = {o["outlet_code"]: o for o in all_outlets}
    outlet = outlets.get(outlet_code)
    billing = fetch_billing_rows(conn).get(outlet_code, [])
    window_months = fetch_window_months(conn)

    by_month = {r["month"]: r["value"] for r in billing}
    trend = [{"month": m, "value": by_month.get(m), "has_record": m in by_month} for m in window_months]

    latest_value = trend[-1]["value"] if trend and trend[-1]["has_record"] else None
    prior_value = trend[-2]["value"] if len(trend) > 1 and trend[-2]["has_record"] else None

    agreed_action = fetch_latest_agreed_action(conn, outlet_code)
    dues = fetch_manual_dues(conn, outlet_code)
    checklist = get_checklist_for_type(outlet.get("outlet_type") if outlet else None, load_checklist_config())

    area = None
    if outlet:
        centroids = compute_centroids(all_outlets)
        area = assign_area(outlet["latitude"], outlet["longitude"], centroids.get(outlet["territory"]))

    return {
        "outlet": outlet,
        "area": area,
        "trend": trend,
        "latest_value": latest_value,
        "prior_value": prior_value,
        "agreed_action": agreed_action,
        "dues": dues,
        "checklist": checklist,
        "recent_visits": fetch_recent_visits(conn, outlet_code),
    }


# --- writes ---

def submit_visit(conn, *, bdm_code, outlet_code, entered_code, responses, order_value, collection_amount,
                  agreed_action_text, dues_amount, photo_taken, captured_latitude, captured_longitude,
                  captured_accuracy, is_complete) -> str:
    """responses: list of {item_key, item_label, response_type, response_value}

    captured_latitude/longitude/accuracy would come from the BDM's own
    phone via a browser geolocation capture -- the Counter Conversation
    screen no longer offers that (see docs/ai-log.md for why), so these
    are always None from the current UI and the code below falls back
    to the outlet's own registered coordinates. The parameters are kept
    so this function still works unchanged if device capture is ever
    added back. Either way, location is an anomaly/audit signal only --
    never used to decide which of two nearby outlets a visit was at
    (see README "The Madurai decision"): typical phone GPS error
    (10-50m) is larger than the gap between two adjacent counters
    (3-5m), so no threshold here can safely do that.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT visit_code, territory, latitude, longitude FROM outlets WHERE outlet_code = %s", (outlet_code,))
        row = cur.fetchone()
        visit_code_on_file, outlet_territory, outlet_lat, outlet_lon = row if row else (None, None, None, None)
        cur.execute("SELECT territory FROM bdms WHERE bdm_code = %s", (bdm_code,))
        bdm_row = cur.fetchone()
        bdm_territory = bdm_row[0] if bdm_row else None

    code_match = bool(entered_code) and (entered_code or "").strip() == (visit_code_on_file or "").strip()
    has_outcome = bool(order_value) or bool(collection_amount) or any(
        r["response_type"] == "blocker" and r["response_value"] for r in responses
    )
    gps_anomaly = (
        flag_outside_territory(outlet_territory, bdm_territory)
        or flag_location_mismatch(captured_latitude, captured_longitude, captured_accuracy, outlet_lat, outlet_lon)
    )
    confidence = compute_confidence(code_match=code_match, has_outcome_evidence=has_outcome, gps_anomaly=gps_anomaly)

    if captured_latitude is not None and captured_longitude is not None:
        stored_lat, stored_lon, location_source = captured_latitude, captured_longitude, "device"
    else:
        stored_lat, stored_lon, location_source = outlet_lat, outlet_lon, ("outlet_registered" if outlet_lat is not None else None)

    # uuid4, not a timestamp: two visits submitted in rapid succession can
    # land in the same tick on Windows (clock resolution ~15ms), which
    # collided in testing -- see docs/ai-log.md.
    visit_id = f"APP-{uuid.uuid4().hex[:16]}-{outlet_code}"

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO visits (visit_id, bdm_code, outlet_code, visit_date, check_in_time, source,
                                 entered_code, code_match, photo_taken, latitude, longitude,
                                 location_accuracy_m, location_source,
                                 gps_anomaly, confidence, is_complete)
            VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_TIME, 'app', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (visit_id, bdm_code, outlet_code, entered_code, code_match, photo_taken,
              stored_lat, stored_lon, captured_accuracy, location_source, gps_anomaly, confidence.level, is_complete))

        for r in responses:
            cur.execute("""
                INSERT INTO visit_checklist_responses (visit_id, item_key, item_label, response_type, response_value)
                VALUES (%s, %s, %s, %s, %s)
            """, (visit_id, r["item_key"], r["item_label"], r["response_type"], r["response_value"]))

        if order_value:
            cur.execute("INSERT INTO orders (visit_id, outlet_code, value) VALUES (%s, %s, %s)",
                        (visit_id, outlet_code, order_value))
        if collection_amount:
            cur.execute("INSERT INTO collections (visit_id, outlet_code, amount) VALUES (%s, %s, %s)",
                        (visit_id, outlet_code, collection_amount))
        if agreed_action_text:
            cur.execute("""
                INSERT INTO agreed_actions (visit_id, outlet_code, action_text, status)
                VALUES (%s, %s, %s, 'open')
            """, (visit_id, outlet_code, agreed_action_text))
        if dues_amount is not None:
            cur.execute("""
                INSERT INTO visit_checklist_responses (visit_id, item_key, item_label, response_type, response_value)
                VALUES (%s, %s, %s, 'manual_entry', %s)
            """, (visit_id, DUES_ITEM_KEY, "Outstanding dues (manual entry)", str(dues_amount)))

    conn.commit()
    return visit_id


def fetch_week_summary(conn, bdm_code: str, days: int = 7) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT outlet_code), COUNT(*)
            FROM visits WHERE bdm_code = %s AND visit_date >= CURRENT_DATE - %s
        """, (bdm_code, days))
        distinct_outlets, visit_count = cur.fetchone()

        cur.execute("""
            SELECT COALESCE(SUM(c.amount), 0) FROM collections c JOIN visits v ON v.visit_id = c.visit_id
            WHERE v.bdm_code = %s AND v.visit_date >= CURRENT_DATE - %s
        """, (bdm_code, days))
        collected = cur.fetchone()[0]

        cur.execute("""
            SELECT COALESCE(SUM(o.value), 0) FROM orders o JOIN visits v ON v.visit_id = o.visit_id
            WHERE v.bdm_code = %s AND v.visit_date >= CURRENT_DATE - %s
        """, (bdm_code, days))
        ordered = cur.fetchone()[0]

        cur.execute("""
            SELECT aa.outlet_code, o.outlet_name, aa.action_text, aa.created_at
            FROM agreed_actions aa
            JOIN visits v ON v.visit_id = aa.visit_id
            LEFT JOIN outlets o ON o.outlet_code = aa.outlet_code
            WHERE v.bdm_code = %s AND aa.status = 'open'
            ORDER BY aa.created_at DESC
        """, (bdm_code,))
        cols = [c.name for c in cur.description]
        open_actions = [dict(zip(cols, row)) for row in cur.fetchall()]

        cur.execute("SELECT COUNT(*) FROM outlets WHERE territory = (SELECT territory FROM bdms WHERE bdm_code = %s)",
                     (bdm_code,))
        territory_outlet_count = cur.fetchone()[0]

        # created_at, not visit_date -- visit_date is just a calendar day,
        # created_at is the real moment the BDM actually hit submit, which
        # is what "what time did he visit" actually means here.
        cur.execute("""
            SELECT v.outlet_code, o.outlet_name, v.created_at, v.confidence
            FROM visits v
            LEFT JOIN outlets o ON o.outlet_code = v.outlet_code
            WHERE v.bdm_code = %s AND v.visit_date >= CURRENT_DATE - %s
            ORDER BY v.created_at DESC
        """, (bdm_code, days))
        cols = [c.name for c in cur.description]
        visits = [dict(zip(cols, row)) for row in cur.fetchall()]

    return {
        "distinct_outlets_visited": distinct_outlets or 0,
        "visit_count": visit_count or 0,
        "collected": float(collected or 0),
        "ordered": float(ordered or 0),
        "open_actions": open_actions,
        "territory_outlet_count": territory_outlet_count or 0,
        "visits": visits,
    }


def mark_action_done(conn, action_row_created_at, outlet_code):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE agreed_actions SET status = 'done'
            WHERE outlet_code = %s AND created_at = %s
        """, (outlet_code, action_row_created_at))
    conn.commit()
