from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from db.queries import get_outlet_counter_context, submit_visit
from logic.charts import render_trend_sparkline
from logic.scoring import format_inr

_GPS_CAPTURE_HTML = """
<div style="font-family:sans-serif;">
<button id="gpsBtn" style="width:100%; min-height:2.8rem; border-radius:8px; border:1px solid #0B2D6B;
    background:#0B2D6B; color:white; font-size:1rem; font-weight:600; cursor:pointer;">
    \U0001F4CD Capture my location
</button>
<div id="gpsStatus" style="font-size:0.78rem; color:#8892a6; margin-top:0.4rem;"></div>
</div>
<script>
document.getElementById('gpsBtn').onclick = function() {
    var statusEl = document.getElementById('gpsStatus');
    statusEl.innerText = 'Getting your location...';
    if (!navigator.geolocation) {
        statusEl.innerText = 'This browser cannot share location.';
        return;
    }
    navigator.geolocation.getCurrentPosition(
        function(pos) {
            var params = new URLSearchParams(window.parent.location.search);
            params.set('cap_lat', pos.coords.latitude);
            params.set('cap_lon', pos.coords.longitude);
            params.set('cap_acc', Math.round(pos.coords.accuracy));
            window.parent.location.search = params.toString();
        },
        function(err) {
            statusEl.innerText = 'Could not get location (' + err.message + '). You can still submit without it.';
        },
        {enableHighAccuracy: true, timeout: 10000}
    );
};
</script>
"""


def _read_captured_location(outlet_code):
    """Session state, keyed to the outlet currently open -- a capture from
    a previously-viewed outlet must never leak onto this one."""
    if st.session_state.get("captured_gps_outlet") != outlet_code:
        for key in ("captured_lat", "captured_lon", "captured_acc"):
            st.session_state.pop(key, None)
        st.session_state.captured_gps_outlet = outlet_code

    cap_lat = st.query_params.get("cap_lat")
    if cap_lat is not None:
        try:
            st.session_state.captured_lat = float(cap_lat)
            st.session_state.captured_lon = float(st.query_params.get("cap_lon"))
            acc = st.query_params.get("cap_acc")
            st.session_state.captured_acc = float(acc) if acc else None
        except (TypeError, ValueError):
            pass
        finally:
            for key in ("cap_lat", "cap_lon", "cap_acc"):
                st.query_params.pop(key, None)

    return (
        st.session_state.get("captured_lat"),
        st.session_state.get("captured_lon"),
        st.session_state.get("captured_acc"),
    )


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

    cap_lat, cap_lon, cap_acc = _read_captured_location(outlet_code)
    st.markdown('<div class="section-label">Location</div>', unsafe_allow_html=True)
    if cap_lat is not None:
        acc_note = f' (±{cap_acc:.0f}m)' if cap_acc else ""
        st.success(f"📍 Location captured{acc_note}. This confirms roughly where your phone was, "
                   f"not which of two adjacent counters you were in — that's still the outlet code below.")
        maps_url = f"https://www.google.com/maps?q={cap_lat},{cap_lon}"
        st.markdown(
            f'<div style="font-size:0.85rem; color:#555; margin-top:-0.6rem; margin-bottom:0.6rem;">'
            f'{cap_lat:.5f}, {cap_lon:.5f} &nbsp;·&nbsp; <a href="{maps_url}" target="_blank">View on map ↗</a></div>',
            unsafe_allow_html=True,
        )
        if st.button("Recapture location", key="recapture_gps"):
            for key in ("captured_lat", "captured_lon", "captured_acc"):
                st.session_state.pop(key, None)
            st.rerun()
    else:
        components.html(_GPS_CAPTURE_HTML, height=80)
        st.caption("Optional, like the photo — it strengthens the audit trail but never blocks a submission.")

    # --- give before you ask ---
    st.markdown('<div class="section-label">This month vs last month</div>', unsafe_allow_html=True)
    latest, prior = ctx["latest_value"], ctx["prior_value"]
    c1, c2 = st.columns(2)
    c1.metric("This month", format_inr(latest) if latest is not None else "No record")
    c2.metric("Last month", format_inr(prior) if prior is not None else "No record")
    st.markdown(render_trend_sparkline(ctx["trend"]), unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.72rem; color:#98a0b3; margin-top:-0.3rem;">'
        '<span style="color:#0B2D6B;">●</span> billed &nbsp; '
        '<span style="color:#D6266E;">●</span> billed nothing &nbsp; '
        '<span style="color:#b6bcc9;">○</span> no record</div>',
        unsafe_allow_html=True,
    )

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
                captured_latitude=cap_lat, captured_longitude=cap_lon, captured_accuracy=cap_acc,
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
