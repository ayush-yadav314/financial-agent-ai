"""ui/landing.py
Empty-state landing screen: featured one-click cards, a searchable stock catalog,
and a "how it works" strip.

Public API:
    render_landing() -> str | None     returns the query of the clicked card, else None
"""
import re

import streamlit as st

from ui.catalog import CATALOG, FEATURED, make_query, search_catalog

_LANDING_CSS = """
.land { text-align: center; margin: .2rem 0 1rem; animation: fadeUp .8s .1s cubic-bezier(.2,.8,.2,1) both; }
.land-eyebrow { font-size: .7rem; letter-spacing: .18em; font-weight: 600; color: var(--muted); }
.land-title { font-family: var(--font-display); font-size: 1.4rem; font-weight: 600; margin: .3rem 0 0; color: var(--text); }
.land-sub { margin-top: 1.8rem; }

/* featured cards: st.button elements whose key starts with "ex_" (needs Streamlit 1.39+) */
[class*="st-key-ex_"] { animation: fadeUp .6s cubic-bezier(.2,.8,.2,1) both; }
.st-key-ex_0 { animation-delay: .15s; }
.st-key-ex_1 { animation-delay: .22s; }
.st-key-ex_2 { animation-delay: .29s; }
.st-key-ex_3 { animation-delay: .36s; }
.st-key-ex_4 { animation-delay: .43s; }
.st-key-ex_5 { animation-delay: .50s; }
[class*="st-key-ex_"] button {
    position: relative; overflow: hidden; width: 100%; min-height: 76px;
    justify-content: flex-start; text-align: left; padding: .9rem 1.1rem;
    border-radius: 16px; border: 1px solid var(--border-strong);
    background: linear-gradient(135deg, rgba(14,20,36,.78), rgba(10,14,26,.72));
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
}
[class*="st-key-ex_"] button p { font-size: .95rem; line-height: 1.45; }
[class*="st-key-ex_"] button::before {
    content: ""; position: absolute; top: 0; bottom: 0; left: -60%; width: 40%;
    background: linear-gradient(100deg, transparent, rgba(255,255,255,.12), transparent);
    transition: left .7s ease; pointer-events: none;
}
[class*="st-key-ex_"] button:hover::before { left: 120%; }
[class*="st-key-ex_"] button:hover { transform: translateY(-4px); }

/* catalog + search chips */
[class*="st-key-cat_"] button, [class*="st-key-sr_"] button {
    width: 100%; min-height: 48px; padding: .5rem .8rem; border-radius: 12px;
    background: rgba(10,14,26,.72);
    backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
}
[class*="st-key-cat_"] button p, [class*="st-key-sr_"] button p { font-size: .85rem; }
[class*="st-key-sr_"] button { animation: fadeUp .35s cubic-bezier(.2,.8,.2,1) both; }
[data-baseweb="tab-list"] { gap: .3rem; }
[data-baseweb="tab-list"] button { font-family: var(--font-body); }
.land-hint { text-align: center; color: var(--muted); font-size: .8rem; margin: .4rem 0; }

/* how it works */
.how { display: grid; grid-template-columns: repeat(3, 1fr); gap: .9rem; margin: 1.3rem 0 .4rem; animation: fadeUp .8s .55s cubic-bezier(.2,.8,.2,1) both; }
@media (max-width: 700px) { .how { grid-template-columns: 1fr; } }
.how-step { position: relative; padding: 1rem 1.2rem; border: 1px solid var(--border); border-radius: var(--radius); background: rgba(10,14,26,.72); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); transition: transform .25s ease, border-color .25s ease; }
.how-step:hover { transform: translateY(-3px); border-color: rgba(34,211,238,.4); }
.how-n { font-family: var(--font-display); font-weight: 700; font-size: 1.5rem; background: linear-gradient(120deg, var(--accent), var(--accent-2)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.how-t { font-weight: 600; margin: .1rem 0 .25rem; color: var(--text); }
.how-d { color: var(--muted); font-size: .82rem; line-height: 1.55; }
.land-note { text-align: center; color: var(--muted); font-size: .74rem; margin: .9rem 0 0; }
"""

_HEADER_HTML = (
    '<div class="land">'
    '<div class="land-eyebrow">ONE-CLICK ANALYSIS</div>'
    '<div class="land-title">Pick a company, or ask anything below</div>'
    '</div>'
)

_EXPLORE_HTML = (
    '<div class="land land-sub">'
    '<div class="land-eyebrow">EXPLORE MORE</div>'
    '<div class="land-title">Browse by category or search any stock</div>'
    '</div>'
)

_HOW_HTML = (
    '<div class="how">'
    '<div class="how-step"><div class="how-n">01</div><div class="how-t">Ask</div>'
    '<div class="how-d">Name any listed stock in plain English. The ticker is resolved for you.</div></div>'
    '<div class="how-step"><div class="how-n">02</div><div class="how-t">Research</div>'
    '<div class="how-d">Yahoo Finance fundamentals and fresh news are fetched in parallel.</div></div>'
    '<div class="how-step"><div class="how-n">03</div><div class="how-t">Report</div>'
    '<div class="how-d">Gemini writes a plain-English report with a bullish, neutral or bearish verdict.</div></div>'
    '</div>'
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

    # ---- searchable catalog ----
    st.markdown(_EXPLORE_HTML, unsafe_allow_html=True)
    raw = st.text_input(
        "Search stocks", key="stock_search", label_visibility="collapsed",
        placeholder="🔍  Search any company or ticker, then press Enter (e.g. HDFC, MSFT, Zomato)",
    )
    q = re.sub(r"[^\w .&\-]", "", raw or "").strip()[:50]

    if q:
        hits = search_catalog(q)
        if hits:
            result = _chip_grid(hits, "sr")
            picked = result or picked
        else:
            st.markdown('<div class="land-hint">Not in the catalog. You can still analyse it:</div>',
                        unsafe_allow_html=True)
        if st.button(f"🔎  Analyse \u201c{q}\u201d anyway", key="sr_any", use_container_width=True):
            picked = f"Give me a full analysis of {q}"
    else:
        tabs = st.tabs(list(CATALOG.keys()))
        for ci, (tab, items) in enumerate(zip(tabs, CATALOG.values())):
            with tab:
                result = _chip_grid(items, f"cat{ci}")
                picked = result or picked

    st.markdown(_HOW_HTML, unsafe_allow_html=True)
    return picked