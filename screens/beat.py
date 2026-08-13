import streamlit as st

from db.queries import build_beat

SEGMENT_BADGE = {
    "Slipping": ("badge-slipping", "Slipping"),
    "Dormant-valuable": ("badge-dormant-valuable", "Dormant (valuable)"),
    "Dormant-low": ("badge-dormant-low", "Dormant"),
    "New/Never": ("badge-new", "New / never billed"),
    "Core": ("badge-core", "Core"),
}


def render(conn, bdm_code):
    st.title("My Visits")

    area_filter = st.session_state.get("beat_area_filter", "All areas")
    data = build_beat(conn, bdm_code, area=None if area_filter == "All areas" else area_filter)
    bdm = data["bdm"]
    if bdm is None:
        st.error("BDM not found.")
        return

    st.caption(f"{bdm['name']} · {bdm['territory']} territory")

    areas = ["All areas"] + data["areas"]
    chosen = st.selectbox(
        "Filter by area (derived from outlet location, not a real locality name)",
        areas, index=areas.index(area_filter) if area_filter in areas else 0,
        key="beat_area_select",
    )
    if chosen != area_filter:
        st.session_state.beat_area_filter = chosen
        st.rerun()

    outlets = build_beat(conn, bdm_code, area=None if chosen == "All areas" else chosen)["outlets"]

    st.markdown(f'<div class="section-label">{len(outlets)} outlets, ranked by what needs attention most</div>',
                unsafe_allow_html=True)

    for o in outlets:
        badge_class, badge_text = SEGMENT_BADGE.get(o["segment"], ("badge-new", o["segment"]))
        dup_badge = '<span class="badge badge-dup">⚠ possible duplicate</span>' if o["is_flagged_duplicate"] else ""
        visit_line = (
            "Never visited" if o["days_since_last_visit"] is None
            else f'Visited {o["days_since_last_visit"]}d ago'
        )
        confidence_note = f' · <span style="color:#999;">{o["confidence_note"]}</span>' if o["confidence_note"] else ""

        with st.container():
            st.markdown(
                f'<div class="beat-card">'
                f'<span class="badge {badge_class}">{badge_text}</span>{dup_badge}'
                f'<div style="font-size:1.1rem; font-weight:600; margin-top:0.35rem;">{o["outlet_name"]}</div>'
                f'<div style="color:#777; font-size:0.85rem;">{o["outlet_type"]} · {o["area"]} · {visit_line}</div>'
                f'<div style="margin-top:0.4rem;">{o["reason"]}{confidence_note}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button(f'Open {o["outlet_code"]}', key=f'open_{o["outlet_code"]}'):
                st.session_state.selected_outlet = o["outlet_code"]
                st.session_state.screen = "counter"
                st.rerun()

    if not outlets:
        st.info("No outlets in this area.")
