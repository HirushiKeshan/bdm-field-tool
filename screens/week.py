import streamlit as st

from db.queries import fetch_week_summary
from logic.scoring import format_inr
from logic.time_utils import to_ist


def render(conn, bdm_code):
    st.title("This Week")
    st.caption("Last 7 days.")

    summary = fetch_week_summary(conn, bdm_code, days=7)

    c1, c2 = st.columns(2)
    c1.metric("Outlets covered", f'{summary["distinct_outlets_visited"]} / {summary["territory_outlet_count"]}')
    c2.metric("Visits logged", summary["visit_count"])

    c3, c4 = st.columns(2)
    c3.metric("Collected", format_inr(summary["collected"]))
    c4.metric("Orders taken", format_inr(summary["ordered"]),
              f'{summary["units_ordered"]} units' if summary["units_ordered"] else None, delta_color="off")

    st.markdown('<div class="section-label">Open actions carrying over</div>', unsafe_allow_html=True)
    if summary["open_actions"]:
        for a in summary["open_actions"]:
            name = a["outlet_name"] or f'Unnamed outlet ({a["outlet_code"]})'
            st.markdown(f'- **{name}**: {a["action_text"]}  \n  _agreed {to_ist(a["created_at"]):%d %b}_')
    else:
        st.caption("Nothing open — every agreed action has been closed out.")

    st.markdown('<div class="section-label">Visits this week</div>', unsafe_allow_html=True)
    if summary["visits"]:
        for v in summary["visits"]:
            name = v["outlet_name"] or f'Unnamed outlet ({v["outlet_code"]})'
            st.markdown(f'- **{name}** — {to_ist(v["created_at"]):%d %b, %I:%M %p} · {v["confidence"]}')
    else:
        st.info("No visits logged in the last 7 days yet. This fills in as you submit visits from My Visits.")
