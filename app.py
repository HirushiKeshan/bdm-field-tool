"""
BDM Field Tool -- entrypoint. Three screens for the BDM (My Beat, Counter
Conversation, My Week), one manager view reached through a low-key link
at the bottom since it's a byproduct, not the point (see README).

No login: a BDM picks their own name from a list on first load. This is a
deliberate, named cut -- see README "What I left out and why".
"""
import psycopg2
import streamlit as st

from db.connection import get_connection
from screens import beat, counter, manager, week

st.set_page_config(page_title="BDM Field Tool", page_icon="\U0001F4F1", layout="centered")

MOBILE_CSS = """
<style>
/* Single column, large tap targets, no horizontal scroll -- tested at 390px. */
div.block-container {padding-top: 1rem; padding-bottom: 5rem; max-width: 480px;}
button[kind], .stButton>button, .stDownloadButton>button {
    min-height: 3rem; font-size: 1.05rem; width: 100%;
}
div[data-testid="stRadio"] label, div[data-testid="stSelectbox"] label {font-size: 1rem;}
input, select, textarea {font-size: 1.05rem !important;}
.beat-card {border: 1px solid rgba(128,128,128,0.3); border-radius: 10px; padding: 0.9rem;
            margin-bottom: 0.6rem;}
.badge {display:inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.78rem;
        font-weight: 600; margin-right: 0.3rem;}
.badge-slipping {background:#fde2e2; color:#8a1f1f;}
.badge-dormant-valuable {background:#fde8cf; color:#8a4b1f;}
.badge-dormant-low {background:#eee; color:#555;}
.badge-new {background:#e2eefd; color:#1f4a8a;}
.badge-core {background:#e0f5e2; color:#1f6b2a;}
.badge-dup {background:#f3e2fd; color:#5a1f8a;}
.section-label {font-size:0.85rem; text-transform:uppercase; letter-spacing:0.04em;
                 color:#888; margin-top:0.8rem; margin-bottom:0.2rem;}
footer {visibility: hidden;}
</style>
"""
st.markdown(MOBILE_CSS, unsafe_allow_html=True)


@st.cache_resource
def _conn():
    return get_connection()


def main():
    conn = _conn()

    if "bdm_code" not in st.session_state:
        st.session_state.bdm_code = st.query_params.get("bdm")
    if "screen" not in st.session_state:
        st.session_state.screen = st.query_params.get("screen", "beat")
    if "selected_outlet" not in st.session_state:
        st.session_state.selected_outlet = st.query_params.get("outlet")
        if st.session_state.selected_outlet:
            st.session_state.screen = "counter"

    try:
        if st.session_state.screen == "manager":
            manager.render(conn)
            return

        if not st.session_state.bdm_code:
            render_bdm_picker(conn)
            return

        if st.session_state.screen == "counter" and st.session_state.selected_outlet:
            counter.render(conn, st.session_state.bdm_code, st.session_state.selected_outlet)
        elif st.session_state.screen == "week":
            week.render(conn, st.session_state.bdm_code)
            render_bottom_nav()
        else:
            beat.render(conn, st.session_state.bdm_code)
            render_bottom_nav()
    except psycopg2.Error:
        # The connection is cached and reused across reruns (st.cache_resource) --
        # without this, one bad query leaves every later query on this
        # connection failing with "current transaction is aborted" until the
        # process restarts. Roll back so the next rerun starts clean.
        conn.rollback()
        raise


def render_bdm_picker(conn):
    from db.queries import fetch_bdms
    st.title("BDM Field Tool")
    st.caption("No login yet -- pick your name to see your beat.")
    bdms = fetch_bdms(conn)
    names = [f'{b["name"]} — {b["territory"]}' for b in bdms]
    choice = st.selectbox("Who are you?", options=range(len(bdms)), format_func=lambda i: names[i])
    if st.button("Start my day", type="primary"):
        st.session_state.bdm_code = bdms[choice]["bdm_code"]
        st.rerun()


def render_bottom_nav():
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("\U0001F4CD My Beat"):
            st.session_state.screen = "beat"
            st.rerun()
    with col2:
        if st.button("\U0001F4C5 My Week"):
            st.session_state.screen = "week"
            st.rerun()
    with col3:
        if st.button("\U0001F504 Switch BDM"):
            st.session_state.bdm_code = None
            st.rerun()
    st.markdown(
        '<div style="text-align:center; margin-top:0.5rem;">'
        '<a href="?manager=1" style="font-size:0.8rem; color:#888;">Manager view</a></div>',
        unsafe_allow_html=True,
    )


if st.query_params.get("manager") == "1":
    st.session_state.screen = "manager"

main()
