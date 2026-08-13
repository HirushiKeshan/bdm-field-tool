import streamlit as st

from db.queries import build_beat

SEGMENT_BADGE = {
    "Slipping": ("badge-slipping", "Slipping"),
    "Dormant-valuable": ("badge-dormant-valuable", "Dormant (valuable)"),
    "Dormant-low": ("badge-dormant-low", "Dormant"),
    "New/Never": ("badge-new", "New / never billed"),
    "Core": ("badge-core", "Core"),
}

# Display order matches urgency, not alphabet -- same order the beat is
# ranked in. The two "something's wrong, go find out why" segments open
# by default; the rest stay collapsed so a rep sees the outlets that need
# attention first, without scrolling past dozens of Core/New cards to
# get there.
SEGMENT_ORDER = ["Slipping", "Dormant-valuable", "Dormant-low", "Core", "New/Never"]
DEFAULT_OPEN = {"Slipping", "Dormant-valuable"}


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

    if not outlets:
        st.info("No outlets in this area.")
        return

    groups = {seg: [] for seg in SEGMENT_ORDER}
    for o in outlets:
        groups.setdefault(o["segment"], []).append(o)

    summary = " &nbsp;·&nbsp; ".join(
        f'<span class="badge {SEGMENT_BADGE.get(seg, ("badge-new", seg))[0]}">{SEGMENT_BADGE.get(seg, ("badge-new", seg))[1]}: {len(items)}</span>'
        for seg, items in groups.items() if items
    )
    st.markdown(
        f'<div class="section-label">{len(outlets)} outlets, grouped by what needs attention most '
        f'-- tap a section to open it</div><div style="margin-bottom:0.6rem;">{summary}</div>',
        unsafe_allow_html=True,
    )

    for seg in SEGMENT_ORDER:
        items = groups[seg]
        if not items:
            continue
        _, seg_label = SEGMENT_BADGE.get(seg, ("badge-new", seg))
        with st.expander(f"{seg_label} ({len(items)})", expanded=seg in DEFAULT_OPEN):
            for o in items:
                _render_card(o)


def _render_card(o):
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
