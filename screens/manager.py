import streamlit as st

from db.manager_queries import (conversation_quality, coverage_gaps, log_integrity,
                                  recovery_pipeline, time_allocation_by_bdm)
from db.queries import fetch_bdms
from logic.charts import (build_anomaly_breakdown_figure, build_confidence_mix_figure,
                            build_time_allocation_figure)
from logic.scoring import format_inr

_CHART_CONFIG = {"displayModeBar": False, "staticPlot": False}
_SORT_LABELS = {"Lowest first (needs attention)": "lowest", "Highest first": "highest", "A-Z": "az"}
_ALL_BDMS = "All BDMs"


def render(conn):
    st.title("Insights")
    st.caption("Every number here traces back to the same outlets/billing/visit tables the field app reads "
               "-- nothing here is a separate rollup.")

    bdms = fetch_bdms(conn)
    bdm_labels = [_ALL_BDMS] + [f'{b["name"]} ({b["territory"]})' for b in bdms]
    view_choice = st.selectbox("View for", bdm_labels, key="insights_bdm_filter")
    bdm_code = None if view_choice == _ALL_BDMS else bdms[bdm_labels.index(view_choice) - 1]["bdm_code"]

    st.header("1. Coverage")
    st.caption("Of the outlets that bill, who hasn't been visited in 30 days? Named, not a percentage.")
    cov = coverage_gaps(conn, days_threshold=30, bdm_code=bdm_code)
    c1, c2 = st.columns(2)
    c1.metric("Billing outlets", cov["total_billing_outlets"])
    c2.metric("Not visited in 30+ days", len(cov["not_visited"]))
    with st.expander(f'{len(cov["not_visited"])} outlets with a coverage gap', expanded=False):
        for o in cov["not_visited"][:50]:
            days = "never visited" if o["days_since_last_visit"] is None else f'{o["days_since_last_visit"]}d ago'
            st.markdown(f'- **{o["outlet_name"]}** ({o["territory"]}, {o["bdm_name"]}) — {o["segment"]} — {days}')
        if len(cov["not_visited"]) > 50:
            st.caption(f'...and {len(cov["not_visited"]) - 50} more.')

    st.header("2. Time allocation")
    st.caption("Share of each BDM's visits going to outlets that actually matter (Core / Slipping / Dormant-valuable).")
    alloc = time_allocation_by_bdm(conn)
    if bdm_code:
        alloc = [r for r in alloc if r["bdm_code"] == bdm_code]
        st.plotly_chart(
            build_time_allocation_figure(alloc, sort_by="lowest"),
            use_container_width=True, config=_CHART_CONFIG, key="time_alloc_chart",
        )
    else:
        sort_choice = st.selectbox("Sort by", list(_SORT_LABELS.keys()), key="time_alloc_sort")
        st.plotly_chart(
            build_time_allocation_figure(alloc, sort_by=_SORT_LABELS[sort_choice]),
            use_container_width=True, config=_CHART_CONFIG, key="time_alloc_chart",
        )
    st.markdown(
        '<div style="font-size:0.72rem; color:#98a0b3; margin-top:-0.6rem;">'
        '<span style="color:#D6266E;">■</span> under 30% &nbsp; '
        '<span style="color:#F5821F;">■</span> 30-45% &nbsp; '
        '<span style="color:#1EBFAE;">■</span> 45%+ &nbsp; '
        '<em>(hover a bar for the exact numbers)</em></div>',
        unsafe_allow_html=True,
    )

    st.header("3. Conversation quality")
    st.caption("Checklist completion and verification confidence — did the conversation actually happen?")
    cq = conversation_quality(conn, bdm_code=bdm_code)
    c1, c2, c3 = st.columns(3)
    c1.metric("Visits logged", cq["total_visits"])
    c2.metric("No outcome recorded", f'{cq["pct_no_outcome"]}%')
    c2.caption("No remarks, and not an Order/Collection visit — a stricter cut than Phase 0's raw 38.3% blank-Remarks number in docs/data-notes.md.")
    if cq["pct_checklist_complete"] is None:
        c3.metric("Checklist complete", "—")
        c3.caption("No app-recorded visits yet")
    else:
        c3.metric("Checklist complete", f'{cq["pct_checklist_complete"]}% ({cq["app_visit_count"]} app visits)')
    mix = cq["confidence_mix"]
    if mix:
        st.plotly_chart(
            build_confidence_mix_figure(mix),
            use_container_width=True, config=_CHART_CONFIG, key="confidence_mix_chart",
        )

    st.header("4. Recovery pipeline")
    st.caption("Dormant-valuable outlets — used to bill well, have gone quiet. Who owns them, has anyone been in?")
    pipeline = recovery_pipeline(conn, bdm_code=bdm_code)
    with st.expander(f'{len(pipeline)} dormant-valuable outlets', expanded=len(pipeline) <= 10):
        for o in pipeline[:50]:
            visit_str = "never visited" if o["days_since_last_visit"] is None else f'last visit {o["days_since_last_visit"]}d ago'
            st.markdown(f'- **{o["outlet_name"]}** ({o["territory"]}, owned by {o["owner_bdm"]}) — '
                        f'quiet {o["months_quiet"]} months, used to do {format_inr(o["used_to_do_per_month"])}/mo — {visit_str}')

    st.header("5. Log integrity")
    st.caption("Why the old visit log couldn't be trusted, measured against the current one.")
    li = log_integrity(conn, bdm_code=bdm_code)
    c1, c2 = st.columns(2)
    c1.metric("Visits flagged as anomalous", f'{li["flagged_visits"]} ({li["pct_flagged"]}%)')
    c2.metric("Possible duplicate outlets", li["possible_duplicate_outlet_pairs"])
    if li["breakdown"]:
        st.plotly_chart(
            build_anomaly_breakdown_figure(li["breakdown"]),
            use_container_width=True, config=_CHART_CONFIG, key="anomaly_breakdown_chart",
        )
