"""
IT WORLD Field Sales -- entrypoint. My Visits, Counter Conversation, and
This Week are the field executive's screens; Insights is a top-level tab
alongside them.

Note on that last point: the brief this app was originally built against
argued the manager-facing view should be a low-key, secondary link rather
than an equal nav tab ("manager visibility is a byproduct... never the
primary design goal") -- promoting it to a full tab, as done here, was an
explicit choice made after flagging that tradeoff. See docs/ai-log.md.

No login: a rep picks their own name from a list on first load. This is a
deliberate, named cut -- see README "What I left out and why".

Branding: colors and wordmark styling are drawn from it-world.in's public
site (navy #012B73, magenta accent, clean sans-serif) -- see docs/ai-log.md
for what was and wasn't pulled from there and why.
"""
import psycopg2
import streamlit as st

from db.connection import get_connection
from screens import beat, counter, manager, week

BRAND_NAVY = "#0B2D6B"
BRAND_ACCENT = "#D6266E"

st.set_page_config(page_title="IT WORLD Field Sales", page_icon="\U0001F310", layout="centered")

MOBILE_CSS = f"""
<style>
/* Single column, large tap targets, no horizontal scroll -- tested at 390px. */
div.block-container {{padding-top: 3.2rem; padding-bottom: 5rem; max-width: 480px;}}
button[kind], .stButton>button, .stDownloadButton>button {{
    min-height: 3rem; font-size: 1.05rem; width: 100%; border-radius: 8px;
}}
div[data-testid="stRadio"] label, div[data-testid="stSelectbox"] label {{font-size: 1rem;}}
input, select, textarea {{font-size: 1.05rem !important;}}
h1 {{color: {BRAND_NAVY} !important; font-weight: 800 !important;}}

.brand-header {{display:flex; align-items:center; gap:0.5rem; margin-bottom:0.6rem;}}
.brand-swoosh {{width:22px; height:22px; border-radius:6px; flex-shrink:0;
    background: conic-gradient(from 200deg, #D6266E, #7B3FA0, #F5821F, #1EBFAE, #D6266E);}}
.brand-name {{font-weight:800; font-size:1.05rem; color:{BRAND_NAVY}; letter-spacing:0.02em;}}
.brand-tagline {{font-size:0.78rem; color:#8892a6; margin-left:0.15rem;}}
.brand-topbar {{height:4px; border-radius:2px; margin:0 0 0.9rem 0;
    background: linear-gradient(90deg, #D6266E, #7B3FA0, #F5821F, #1EBFAE);}}

.beat-card {{border: 1px solid rgba(11,45,107,0.15); border-radius: 10px; padding: 0.9rem;
            margin-bottom: 0.6rem;}}
.badge {{display:inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.78rem;
        font-weight: 600; margin-right: 0.3rem;}}
.badge-slipping {{background:#fde2e2; color:#8a1f1f;}}
.badge-dormant-valuable {{background:#fde8cf; color:#8a4b1f;}}
.badge-dormant-low {{background:#eee; color:#555;}}
.badge-new {{background:#e2eefd; color:#1f4a8a;}}
.badge-core {{background:#e0f5e2; color:#1f6b2a;}}
.badge-dup {{background:#f3e2fd; color:#5a1f8a;}}
.section-label {{font-size:0.85rem; text-transform:uppercase; letter-spacing:0.04em;
                 color:#888; margin-top:0.8rem; margin-bottom:0.2rem;}}
footer {{visibility: hidden;}}

/* Equal-weight tab bar: My Visits / This Week / Insights. The active tab
   uses the brand accent (primaryColor in .streamlit/config.toml); the
   other two are ghost/outline via kind=secondary. */
.nav-row .stButton>button[kind="secondary"] {{
    background: transparent; border: 1px solid rgba(11,45,107,0.25); color: {BRAND_NAVY};
}}
</style>
"""
st.markdown(MOBILE_CSS, unsafe_allow_html=True)


def render_brand_header():
    st.markdown(
        '<div class="brand-topbar"></div>'
        '<div class="brand-header">'
        '<div class="brand-swoosh"></div>'
        '<span class="brand-name">IT WORLD</span>'
        '<span class="brand-tagline">Field Sales</span>'
        '</div>',
        unsafe_allow_html=True,
    )


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


NAV_TABS = [("beat", "\U0001F4CD My Visits"), ("week", "\U0001F4C5 This Week"), ("manager", "\U0001F4CA Insights")]


def main():
    conn = _conn()
    render_brand_header()

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

        # My Visits / This Week both need a rep identity; Insights does not.
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
    st.title("Field Sales Companion")
    st.caption("No login yet -- pick your name to see your visits.")
    bdms = fetch_bdms(conn)
    names = [f'{b["name"]} — {b["territory"]}' for b in bdms]
    choice = st.selectbox("Who are you?", options=range(len(bdms)), format_func=lambda i: names[i])
    if st.button("Start my day", type="primary"):
        st.session_state.bdm_code = bdms[choice]["bdm_code"]
        if st.session_state.screen not in ("beat", "week"):
            st.session_state.screen = "beat"
        st.rerun()


def render_nav_bar(active: str):
    """My Visits / This Week / Insights as three equal-weight tabs.
    Switching profile is a separate, secondary action (small button, not
    a tab) since it's rare compared to moving between these three
    sections."""
    st.markdown('<div class="nav-row">', unsafe_allow_html=True)
    cols = st.columns(3)
    for col, (key, label) in zip(cols, NAV_TABS):
        with col:
            is_active = key == active
            if st.button(label, key=f"nav_{key}", type="primary" if is_active else "secondary"):
                # My Visits/This Week need a rep identity; if none is set
                # yet, this still records the intended tab so
                # render_bdm_picker can land there right after "Start my day".
                st.session_state.screen = key
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if active in ("beat", "week") and st.session_state.get("bdm_code"):
        _, col_b = st.columns([3, 1])
        with col_b:
            if st.button("Switch Profile", key="switch_bdm"):
                st.session_state.bdm_code = None
                st.session_state.screen = "beat"
                st.rerun()
    st.divider()


main()
