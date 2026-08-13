"""
BDM Field Tool -- entrypoint. My Beat, Counter Conversation, and My Week
are the BDM's screens; Manager view is a top-level tab alongside them.

Note on that last point: the brief this app was originally built against
argued Manager view should be a low-key, secondary link rather than an
equal nav tab ("manager visibility is a byproduct... never the primary
design goal") -- promoting it to a full tab, as done here, was an
explicit choice made after flagging that tradeoff. See docs/ai-log.md.

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

/* Equal-weight tab bar: My Beat / My Week / Manager. The active tab is a
   plain button (Streamlit's default styling reads as "selected" against
   the other two, which are ghost/outline via kind=secondary). */
.nav-row .stButton>button[kind="secondary"] {
    background: transparent; border: 1px solid rgba(128,128,128,0.35);
}
.switch-bdm-link {font-size:0.82rem; color:#888; text-decoration:none;}
</style>
"""
st.markdown(MOBILE_CSS, unsafe_allow_html=True)


@st.cache_resource
def _conn():
    conn = get_connection()
    _ensure_seeded(conn)
    return conn


def _ensure_seeded(conn):
    """Runs once per app process (guarded by @st.cache_resource on _conn).
    Lets a fresh deploy (e.g. a brand-new Supabase database) come up ready
    to use with nothing more than DATABASE_URL set -- no separate manual
    `python seed.py` step needed. Safe to call on an already-seeded
    database too: apply_schema is idempotent, and the row-count check
    below skips reloading if data is already present."""
    from db.connection import apply_schema

    apply_schema(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM outlets")
        already_seeded = cur.fetchone()[0] > 0
    if not already_seeded:
        with st.spinner("First-time setup: loading outlet, billing, and visit data..."):
            import seed
            seed.main()


NAV_TABS = [("beat", "\U0001F4CD My Beat"), ("week", "\U0001F4C5 My Week"), ("manager", "\U0001F4CA Manager")]


def main():
    conn = _conn()

    if "bdm_code" not in st.session_state:
        st.session_state.bdm_code = st.query_params.get("bdm")
    if "screen" not in st.session_state:
        screen = st.query_params.get("screen", "beat")
        st.session_state.screen = "manager" if st.query_params.get("manager") == "1" else screen
    if "selected_outlet" not in st.session_state:
        st.session_state.selected_outlet = st.query_params.get("outlet")
        if st.session_state.selected_outlet:
            st.session_state.screen = "counter"

    try:
        if st.session_state.screen == "counter" and st.session_state.selected_outlet:
            counter.render(conn, st.session_state.bdm_code, st.session_state.selected_outlet)
            return

        if st.session_state.screen == "manager":
            render_nav_bar(active="manager")
            manager.render(conn)
            return

        # My Beat / My Week both need a BDM identity; Manager does not.
        if not st.session_state.bdm_code:
            render_bdm_picker(conn)
            return

        render_nav_bar(active=st.session_state.screen)
        if st.session_state.screen == "week":
            week.render(conn, st.session_state.bdm_code)
        else:
            beat.render(conn, st.session_state.bdm_code)
    except psycopg2.Error:
        # The connection is cached and reused across reruns (st.cache_resource) --
        # without this, one bad query leaves every later query on this
        # connection failing with "current transaction is aborted" until the
        # process restarts. Roll back so the next rerun starts clean.
        conn.rollback()
        raise


def render_bdm_picker(conn):
    from db.queries import fetch_bdms
    render_nav_bar(active="beat")
    st.title("BDM Field Tool")
    st.caption("No login yet -- pick your name to see your beat.")
    bdms = fetch_bdms(conn)
    names = [f'{b["name"]} — {b["territory"]}' for b in bdms]
    choice = st.selectbox("Who are you?", options=range(len(bdms)), format_func=lambda i: names[i])
    if st.button("Start my day", type="primary"):
        st.session_state.bdm_code = bdms[choice]["bdm_code"]
        if st.session_state.screen not in ("beat", "week"):
            st.session_state.screen = "beat"
        st.rerun()


def render_nav_bar(active: str):
    """My Beat / My Week / Manager as three equal-weight tabs. Switching
    BDM is a separate, secondary action (small link, not a tab) since
    it's rare compared to moving between these three sections."""
    st.markdown('<div class="nav-row">', unsafe_allow_html=True)
    cols = st.columns(3)
    for col, (key, label) in zip(cols, NAV_TABS):
        with col:
            is_active = key == active
            if st.button(label, key=f"nav_{key}", type="primary" if is_active else "secondary"):
                # My Beat/My Week need a BDM identity; if none is set yet,
                # this still records the intended tab so render_bdm_picker
                # can land there right after "Start my day".
                st.session_state.screen = key
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if active in ("beat", "week") and st.session_state.get("bdm_code"):
        _, col_b = st.columns([3, 1])
        with col_b:
            if st.button("Switch BDM", key="switch_bdm"):
                st.session_state.bdm_code = None
                st.session_state.screen = "beat"
                st.rerun()
    st.divider()


main()
