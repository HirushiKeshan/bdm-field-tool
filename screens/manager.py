import streamlit as st

from db.manager_queries import (conversation_quality, coverage_gaps, log_integrity,
                                  recovery_pipeline, time_allocation_by_bdm)
from logic.scoring import format_inr


def render(conn):
    st.title("Manager view")
    st.caption("Every number here traces back to the same outlets/billing/visit tables the BDM app reads "
               "-- nothing here is a separate rollup.")

    st.header("1. Coverage")
    st.caption("Of the outlets that bill, who hasn't been visited in 30 days? Named, not a percentage.")
    cov = coverage_gaps(conn, days_threshold=30)
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
    for row in alloc:
        st.progress(min(1.0, row["pct_to_valuable_outlets"] / 100),
                    text=f'{row["bdm_name"]} ({row["territory"]}): {row["pct_to_valuable_outlets"]}% of '
                         f'{row["total_visits"]} visits to outlets that matter')

    st.header("3. Conversation quality")
    st.caption("Checklist completion and verification confidence — did the conversation actually happen?")
    cq = conversation_quality(conn)
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
    st.write(" · ".join(f"**{k}**: {v}" for k, v in sorted(mix.items(), key=lambda x: -x[1])))

    st.header("4. Recovery pipeline")
    st.caption("Dormant-valuable outlets — used to bill well, have gone quiet. Who owns them, has anyone been in?")
    pipeline = recovery_pipeline(conn)
    with st.expander(f'{len(pipeline)} dormant-valuable outlets', expanded=len(pipeline) <= 10):
        for o in pipeline[:50]:
            visit_str = "never visited" if o["days_since_last_visit"] is None else f'last visit {o["days_since_last_visit"]}d ago'
            st.markdown(f'- **{o["outlet_name"]}** ({o["territory"]}, owned by {o["owner_bdm"]}) — '
                        f'quiet {o["months_quiet"]} months, used to do {format_inr(o["used_to_do_per_month"])}/mo — {visit_str}')

    st.header("5. Log integrity")
    st.caption("Why the old visit log couldn't be trusted, measured against the current one.")
    li = log_integrity(conn)
    c1, c2 = st.columns(2)
    c1.metric("Visits flagged as anomalous", f'{li["flagged_visits"]} ({li["pct_flagged"]}%)')
    c2.metric("Possible duplicate outlets", li["possible_duplicate_outlet_pairs"])
    for reason, count in sorted(li["breakdown"].items(), key=lambda x: -x[1]):
        st.markdown(f'- {reason}: {count}')
