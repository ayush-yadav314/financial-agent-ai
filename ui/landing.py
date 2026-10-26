"""ui/landing.py
Empty-state landing screen: featured one-click cards and a collapsed category browser.
(Search lives in ui/search.py and is shown on every screen.)

Public API:
    render_landing() -> str | None     returns the query of the clicked card, else None
"""
import streamlit as st

from ui.catalog import CATALOG, FEATURED, make_query

_LANDING_CSS = """
.land { text-align: center; margin: .4rem 0 1rem; animation: fadeUp .4s ease both; }
.land-eyebrow { font-size: .68rem; letter-spacing: .16em; font-weight: 600; color: var(--muted); }
.land-title { font-family: var(--font-display); font-size: 1.3rem; font-weight: 700; margin: .25rem 0 0; color: var(--text); }
[class*="st-key-ex_"] button {
    width: 100%; min-height: 68px; justify-content: flex-start; text-align: left;
    padding: .8rem 1rem; border-radius: 12px; border: 1px solid var(--border-strong);
    background: rgba(255,255,255,.04);
}
[class*="st-key-ex_"] button p { font-size: .92rem; line-height: 1.45; }
[class*="st-key-ex_"] button:hover { border-color: var(--accent); background: rgba(34,211,238,.07); }
[class*="st-key-cat_"] button { width: 100%; min-height: 44px; padding: .4rem .7rem; border-radius: 10px; }
[class*="st-key-cat_"] button p { font-size: .84rem; }
.land-how { text-align: center; color: var(--muted); font-size: .82rem; margin: 1rem 0 .2rem; line-height: 1.6; }
.land-note { text-align: center; color: var(--muted); font-size: .72rem; margin: .2rem 0 0; }
"""

_HEADER_HTML = (
    '<div class="land">'
    '<div class="land-eyebrow">ONE-CLICK ANALYSIS</div>'
    '<div class="land-title">Start with a company, or search above</div>'
    '</div>'
)

_HOW_HTML = (
    '<div class="land-how"><b>Ask</b> in plain English &nbsp;→&nbsp; <b>Research</b> from Yahoo Finance and recent news '
    '&nbsp;→&nbsp; <b>Report</b> with an AI verdict and sources</div>'
    '<div class="land-note">Educational research only. This is not financial advice.</div>'
)


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _LANDING_CSS.splitlines() if line.strip())


def _chip_grid(items: list, prefix: str, cols_n: int = 4):
    """Render catalog items as a grid of compact buttons. Returns the clicked query or None."""
    picked = None
    for start in range(0, len(items), cols_n):
        cols = st.columns(cols_n)
        for k, (name, ticker, tag) in enumerate(items[start:start + cols_n]):
            label = f"**{name}** · {ticker.replace('.NS', '')}"
            if cols[k].button(label, key=f"{prefix}_{start + k}", use_container_width=True, help=tag):
                picked = make_query(name, ticker)
    return picked


def render_landing():
    """Render the landing screen. Returns the query string of the clicked card, else None."""
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)
    st.markdown(_HEADER_HTML, unsafe_allow_html=True)

    picked = None

    # ---- featured one-click cards ----
    for start in range(0, len(FEATURED), 3):
        cols = st.columns(3)
        for k, (icon, name, tag, ticker) in enumerate(FEATURED[start:start + 3]):
            i = start + k
            label = f"{icon}  **{name}**  ·  {tag}"
            if cols[k].button(label, key=f"ex_{i}", use_container_width=True, help="Run a full analysis"):
                picked = make_query(name, ticker)

    # ---- categories (collapsed to save space) ----
    with st.expander("Browse more stocks by category", expanded=False):
        tabs = st.tabs(list(CATALOG.keys()))
        for ci, (tab, items) in enumerate(zip(tabs, CATALOG.values())):
            with tab:
                result = _chip_grid(items, f"cat_{ci}")
                picked = result or picked

    st.markdown(_HOW_HTML, unsafe_allow_html=True)
    return picked