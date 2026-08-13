from datetime import datetime

import streamlit as st

from db.queries import get_outlet_counter_context, submit_visit
from logic.scoring import format_inr


def _trend_chip(point):
    if not point["has_record"]:
        return f'<span style="color:#aaa; border:1px dashed #ccc; border-radius:6px; padding:2px 6px; font-size:0.75rem;">{point["month"][-2:]}: no record</span>'
    if point["value"] == 0:
        return f'<span style="color:#8a1f1f; border:1px solid #f3c; background:#fde2e2; border-radius:6px; padding:2px 6px; font-size:0.75rem;">{point["month"][-2:]}: ₹0 (billed nothing)</span>'
    return f'<span style="border:1px solid #ccc; border-radius:6px; padding:2px 6px; font-size:0.75rem;">{point["month"][-2:]}: {format_inr(point["value"])}</span>'


def render(conn, bdm_code, outlet_code):
    ctx = get_outlet_counter_context(conn, outlet_code)
    outlet = ctx["outlet"]
    if outlet is None:
        st.error("Outlet not found.")
        return

    if st.button("← Back to My Visits"):
        st.session_state.screen = "beat"
        st.session_state.selected_outlet = None
        st.rerun()

    st.title(outlet["outlet_name"] or f"Unnamed outlet ({outlet_code})")
    st.caption(f'{outlet["outlet_type"] or "Type not recorded"} · {outlet["town_raw"]} · {outlet_code}')
    if outlet.get("possible_duplicate_of"):
        st.warning(f'⚠ Possible duplicate of outlet {outlet["possible_duplicate_of"]} — same location, similar name. '
                   f'Verify with the owner before treating this as a separate account.')

    # --- give before you ask ---
    st.markdown('<div class="section-label">This month vs last month</div>', unsafe_allow_html=True)
    latest, prior = ctx["latest_value"], ctx["prior_value"]
    c1, c2 = st.columns(2)
    c1.metric("This month", format_inr(latest) if latest is not None else "No record")
    c2.metric("Last month", format_inr(prior) if prior is not None else "No record")
    st.markdown(" ".join(_trend_chip(p) for p in ctx["trend"]), unsafe_allow_html=True)

    st.markdown('<div class="section-label">Outstanding dues</div>', unsafe_allow_html=True)
    if ctx["dues"]:
        st.write(f'₹{ctx["dues"]["amount"]} as of last visit ({ctx["dues"]["updated_at"]:%d %b})')
    else:
        st.caption("Dues not tracked from source data — enter what the owner tells you below.")
    dues_amount_input = st.number_input("Dues owed right now (₹, optional)", min_value=0, step=500, key="dues_input")

    st.markdown('<div class="section-label">Last time, we agreed to...</div>', unsafe_allow_html=True)
    if ctx["agreed_action"]:
        aa = ctx["agreed_action"]
        st.info(f'{aa["action_text"]}  \n_{aa["status"]} · agreed {aa["created_at"]:%d %b}_')
    else:
        st.caption("No agreed action on file from a previous visit.")

    st.divider()
    st.markdown("### Today's conversation")
    st.caption(f'Up to {len(ctx["checklist"])} things to cover — no more, you\'re on the road.')

    with st.form("visit_form", clear_on_submit=False):
        responses = []
        order_value = st.number_input("Order taken today (₹, 0 if none)", min_value=0, step=1000, key="order_val")
        collection_amount = st.number_input("Collected today (₹, 0 if none)", min_value=0, step=500, key="collect_val")

        for item in ctx["checklist"]:
            if item["type"] in ("order", "collection"):
                continue  # already captured above as the universal order/collection inputs
            st.markdown(f'**{item["label"]}**')
            if item["type"] == "blocker":
                # index=None so nothing is pre-selected -- a radio with a
                # default selection would count as "answered" the moment
                # the form renders, before the BDM touches anything, which
                # would make Partial/Verified reachable without a real
                # conversation happening. See docs/ai-log.md.
                choice = st.radio(item["label"], item["options"], index=None, key=f'item_{item["key"]}',
                                   label_visibility="collapsed")
                note = st.text_input("Note (optional)", key=f'note_{item["key"]}', label_visibility="collapsed",
                                      placeholder="Optional note")
                response_value = (f"{choice}" + (f" — {note}" if note else "")) if choice is not None else None
                responses.append({"item_key": item["key"], "item_label": item["label"],
                                   "response_type": "blocker", "response_value": response_value})
            elif item["type"] == "action":
                text = st.text_input(item["label"], key=f'item_{item["key"]}', label_visibility="collapsed",
                                      placeholder="e.g. Will visit again after Diwali stock lands")
                responses.append({"item_key": item["key"], "item_label": item["label"],
                                   "response_type": "note", "response_value": text or None})

        st.divider()
        st.markdown('<div class="section-label">Verification</div>', unsafe_allow_html=True)
        st.caption("Ask the owner to read the code off the card at the counter.")
        entered_code = st.text_input("Outlet code (4 digits, from the counter card)", max_chars=4, key="entered_code")
        photo = st.camera_input("Optional: photo of the counter", key="photo_input")

        col_a, col_b = st.columns(2)
        save_partial = col_a.form_submit_button("Save partial")
        submit_full = col_b.form_submit_button("Submit visit", type="primary")

        if save_partial or submit_full:
            agreed_action_text = None
            for r in responses:
                if r["item_key"] == "agreed_action" and r["response_value"]:
                    agreed_action_text = r["response_value"]

            visit_id = submit_visit(
                conn, bdm_code=bdm_code, outlet_code=outlet_code,
                entered_code=entered_code or None,
                responses=[r for r in responses if r["response_value"]],
                order_value=order_value or None,
                collection_amount=collection_amount or None,
                agreed_action_text=agreed_action_text,
                dues_amount=dues_amount_input or None,
                photo_taken=photo is not None,
                latitude=outlet.get("latitude"), longitude=outlet.get("longitude"),
                is_complete=bool(submit_full),
            )
            if submit_full:
                st.success(f"Visit submitted ({visit_id}).")
            else:
                st.warning(f"Saved as partial ({visit_id}) — finish it next time you're here.")
            st.session_state.screen = "beat"
            st.session_state.selected_outlet = None
            st.rerun()

    st.markdown('<div class="section-label">Recent visits</div>', unsafe_allow_html=True)
    for v in ctx["recent_visits"][:5]:
        outcome = v["remarks"] or (v["purpose"] or "Outcome not logged")
        st.caption(f'{v["visit_date"]} · {v["confidence"]} · {outcome}')
