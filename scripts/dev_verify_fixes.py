"""Dev-only: verify the two bugs found by independent review are fixed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import get_connection
from db.queries import fetch_visit_recency, submit_visit
from logic.confidence import compute_confidence

conn = get_connection()

print("--- bug 1: recency should NOT shift when an unrelated outlet gets a new visit ---")
before = fetch_visit_recency(conn)
sample_code = next(iter(before))
print(f"{sample_code} days_since before:", before[sample_code]["days_since"])

submit_visit(
    conn, bdm_code="BDM001", outlet_code="OA0001", entered_code=None, responses=[],
    order_value=None, collection_amount=None, agreed_action_text=None, dues_amount=None,
    photo_taken=False, latitude=None, longitude=None, is_complete=False,
)

after = fetch_visit_recency(conn)
print(f"{sample_code} days_since after unrelated write:", after[sample_code]["days_since"])
assert before[sample_code]["days_since"] == after[sample_code]["days_since"], "BUG: unrelated write shifted recency!"
print("OK: unrelated outlet's recency did not move.")

print("\n--- bug 2: an empty click-through submission must be Unverified, not Partial ---")
visit_id = submit_visit(
    conn, bdm_code="BDM002", outlet_code="OA0006", entered_code=None,
    responses=[],  # simulates every blocker radio left at index=None, filtered out before reaching here
    order_value=None, collection_amount=None, agreed_action_text=None, dues_amount=None,
    photo_taken=False, latitude=None, longitude=None, is_complete=True,
)
with conn.cursor() as cur:
    cur.execute("SELECT confidence FROM visits WHERE visit_id = %s", (visit_id,))
    confidence = cur.fetchone()[0]
print("confidence for empty submission:", confidence)
assert confidence == "Unverified", f"BUG: empty submission got {confidence}, expected Unverified"
print("OK: empty submission correctly registers as Unverified.")

conn.close()
print("\nBoth fixes verified.")
