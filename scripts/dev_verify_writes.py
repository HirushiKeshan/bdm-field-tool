import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import get_connection
from db.manager_queries import (conversation_quality, coverage_gaps, log_integrity,
                                  recovery_pipeline, time_allocation_by_bdm)
from db.queries import fetch_week_summary, get_outlet_counter_context, submit_visit

conn = get_connection()

print("--- submit_visit: full submission with code match ---")
ctx = get_outlet_counter_context(conn, "OA0363")
visit_id = submit_visit(
    conn, bdm_code="BDM004", outlet_code="OA0363",
    entered_code=ctx["outlet"]["visit_code"],  # simulate the owner reading the correct code
    responses=[{"item_key": "competitor_pressure", "item_label": "Competitor pressure",
                "response_type": "blocker", "response_value": "No"}],
    order_value=50000, collection_amount=20000,
    agreed_action_text="Will push the new iPhone bundle next visit",
    dues_amount=15000, photo_taken=False,
    captured_latitude=ctx["outlet"]["latitude"], captured_longitude=ctx["outlet"]["longitude"], captured_accuracy=15,
    is_complete=True,
)
print("created visit:", visit_id)

with conn.cursor() as cur:
    cur.execute("SELECT confidence, code_match, entered_code FROM visits WHERE visit_id = %s", (visit_id,))
    print("stored confidence/code_match/entered_code:", cur.fetchone())
    cur.execute("SELECT value FROM orders WHERE visit_id = %s", (visit_id,))
    print("order:", cur.fetchone())
    cur.execute("SELECT amount FROM collections WHERE visit_id = %s", (visit_id,))
    print("collection:", cur.fetchone())
    cur.execute("SELECT action_text, status FROM agreed_actions WHERE visit_id = %s", (visit_id,))
    print("agreed action:", cur.fetchone())
    cur.execute("SELECT item_key, response_value FROM visit_checklist_responses WHERE visit_id = %s ORDER BY item_key", (visit_id,))
    print("checklist responses:", cur.fetchall())

print("\n--- re-fetch counter context: agreed action + dues should now show ---")
ctx2 = get_outlet_counter_context(conn, "OA0363")
print("agreed_action:", ctx2["agreed_action"])
print("dues:", ctx2["dues"])

print("\n--- submit_visit: no code entered, no outcome -> should be Unverified ---")
visit_id2 = submit_visit(
    conn, bdm_code="BDM004", outlet_code="OA0363", entered_code=None, responses=[],
    order_value=None, collection_amount=None, agreed_action_text=None, dues_amount=None,
    photo_taken=False, captured_latitude=None, captured_longitude=None, captured_accuracy=None, is_complete=False,
)
with conn.cursor() as cur:
    cur.execute("SELECT confidence, is_complete FROM visits WHERE visit_id = %s", (visit_id2,))
    print("stored:", cur.fetchone())

print("\n--- submit_visit: wrong code entered but outcome recorded -> should be Partial ---")
visit_id3 = submit_visit(
    conn, bdm_code="BDM004", outlet_code="OA0363", entered_code="0000", responses=[],
    order_value=10000, collection_amount=None, agreed_action_text=None, dues_amount=None,
    photo_taken=False, captured_latitude=None, captured_longitude=None, captured_accuracy=None, is_complete=True,
)
with conn.cursor() as cur:
    cur.execute("SELECT confidence, code_match FROM visits WHERE visit_id = %s", (visit_id3,))
    print("stored:", cur.fetchone())

print("\n--- submit_visit: code matches but captured GPS is 400km away -> location mismatch anomaly ---")
visit_id4 = submit_visit(
    conn, bdm_code="BDM004", outlet_code="OA0363", entered_code=ctx["outlet"]["visit_code"], responses=[],
    order_value=None, collection_amount=None, agreed_action_text=None, dues_amount=None,
    photo_taken=False, captured_latitude=13.0827, captured_longitude=80.2707, captured_accuracy=10,
    is_complete=True,
)
with conn.cursor() as cur:
    cur.execute("SELECT confidence, gps_anomaly, location_source FROM visits WHERE visit_id = %s", (visit_id4,))
    print("stored:", cur.fetchone())

print("\n--- fetch_week_summary for BDM004 ---")
print(fetch_week_summary(conn, "BDM004"))

print("\n--- manager_queries smoke test ---")
print("coverage_gaps total_billing_outlets:", coverage_gaps(conn)["total_billing_outlets"])
print("time_allocation sample:", time_allocation_by_bdm(conn)[:2])
print("conversation_quality:", conversation_quality(conn))
print("recovery_pipeline count:", len(recovery_pipeline(conn)))
print("log_integrity:", log_integrity(conn))

conn.close()
print("\nAll write-path and manager-query checks completed without error.")
