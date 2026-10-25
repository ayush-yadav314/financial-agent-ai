"""ui/search.py
Smart stock search: logos, names, tickers and exchanges, backed by your own catalog
plus Yahoo Finance's live search. Selecting a result returns a query that the
existing LangGraph workflow handles unchanged.

Public API
    render_search(key="stock_search") -> (query | None, active: bool)
        query:  the analysis request to run if the user clicked a result, else None
        active: True while the search box has text (so the caller can hide other content)
    search_stocks(text, limit=8) -> list[dict]   (name, ticker, exch, source)
"""
import html
import re
import time

import streamlit as st

from ui.catalog import CATALOG, FEATURED, make_query
from ui.logos import logo_row_html, prefetch_logos

_CSS = """
[class*="st-key-sx_"] button {
    min-height: 40px; padding: .3rem .9rem; border-radius: 12px;
    background: rgba(10,14,26,.72);
    backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
}
[class*="st-key-sx_"] button p { font-size: .85rem; }
[class*="st-key-sx_"] { animation: fadeUp .35s cubic-bezier(.2,.8,.2,1) both; }
.sx-note { color: var(--muted); font-size: .74rem; margin: .5rem 0 .6rem; }
.sx-empty { text-align: center; color: var(--muted); font-size: .86rem; padding: .9rem 0 .4rem; }
"""


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _supported(ticker: str) -> bool:
    """US tickers (no dot) and Indian NSE/BSE only: the price labels handle $ and ₹."""
    t = ticker.upper()
    return "." not in t or t.endswith((".NS", ".BO"))


def _exchange(ticker: str, yahoo_exch: str = "") -> str:
    t = ticker.upper()
    if t.endswith(".NS"):
        return "NSE"
    if t.endswith(".BO"):
        return "BSE"
    return yahoo_exch or "US"


def _clean_name(name: str) -> str:
    # brackets are reserved for the "(TICKER)" marker that the agent looks for
    return re.sub(r"\s+", " ", re.sub(r"[()]", "", name or "")).strip()


# ---------------------------------------------------------------------
# local index (your featured cards + catalog)
# ---------------------------------------------------------------------
_LOCAL = None


def _local_index() -> list:
    global _LOCAL
    if _LOCAL is None:
        seen, out = set(), []
        rows = [(n, t) for _i, n, _tag, t in FEATURED]
        for items in CATALOG.values():
            rows += [(n, t) for n, t, _tag in items]
        for name, ticker in rows:
            if ticker in seen:
                continue
            seen.add(ticker)
            out.append({"name": _clean_name(name), "ticker": ticker,
                        "exch": _exchange(ticker), "source": "catalog"})
        _LOCAL = out
    return _LOCAL


def _score(q: str, name: str, ticker: str):
    """Lower is better; None means no match."""
    n, t = name.lower(), ticker.lower()
    base = t.split(".")[0]
    if q == t or q == base:
        return 0
    if t.startswith(q):
        return 1
    if n.startswith(q):
        return 2
    if any(w.startswith(q) for w in re.split(r"[\s&.\-]+", n) if w):
        return 3
    if q in n or q in t:
        return 4
    return None


def _search_local(q: str) -> list:
    ranked = []
    for item in _local_index():
        s = _score(q, item["name"], item["ticker"])
        if s is not None:
            ranked.append((s, item["name"], item))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in ranked]


# ---------------------------------------------------------------------
# Yahoo Finance live search (cached; failures are never cached)
# ---------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def _yahoo_cached(q: str) -> list:
    import yfinance as yf

    try:
        s = yf.Search(q, max_results=10, news_count=0, timeout=5)
    except TypeError:                      # older yfinance without those arguments
        s = yf.Search(q, max_results=10)
    quotes = getattr(s, "quotes", None)
    if quotes is None:
        raise RuntimeError("Yahoo search returned no quote list")

    out = []
    for r in quotes:
        ticker = str(r.get("symbol") or "").upper()
        if not ticker or str(r.get("quoteType") or "").upper() != "EQUITY":
            continue
        if not _supported(ticker):
            continue
        name = _clean_name(r.get("longname") or r.get("shortname") or ticker)
        out.append({"name": name, "ticker": ticker,
                    "exch": _exchange(ticker, str(r.get("exchDisp") or "")),
                    "source": "yahoo"})
    return out


def _search_yahoo(q: str) -> list:
    # after a failure, don't retry for 60 seconds so a dead service never stalls the page
    if time.time() < st.session_state.get("_ysearch_retry_at", 0):
        return []
    try:
        return _yahoo_cached(q)
    except Exception:
        st.session_state["_ysearch_retry_at"] = time.time() + 60
        return []


# ---------------------------------------------------------------------
# public search
# ---------------------------------------------------------------------
def search_stocks(text: str, limit: int = 8) -> list:
    """Catalog matches first, then live Yahoo matches. Deduplicated by ticker."""
    q = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not q:
        return []
    results = _search_local(q)[:limit]
    if len(results) < limit and len(q) >= 2:
        have = {r["ticker"] for r in results}
        for item in _search_yahoo(q):
            if item["ticker"] not in have:
                results.append(item)
                have.add(item["ticker"])
            if len(results) >= limit:
                break
    return results


# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------
def _cols(spec):
    """Vertically centred columns where supported (Streamlit 1.36+), plain columns otherwise."""
    try:
        return st.columns(spec, vertical_alignment="center")
    except TypeError:
        return st.columns(spec)


def render_search(key: str = "stock_search",
                  placeholder: str = "🔍  Search any company or ticker, then press Enter (e.g. HDFC, MSFT, Zomato)"):
    """Search box + results panel. Returns (query_or_None, active)."""
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)
    raw = st.text_input("Search stocks", key=key, label_visibility="collapsed", placeholder=placeholder)
    q = re.sub(r"[^\w .&\-]", "", raw or "").strip()[:50]
    if not q:
        return None, False

    results = search_stocks(q)
    prefetch_logos([r["ticker"] for r in results])

    picked = None
    if results:
        for i, r in enumerate(results):
            c1, c2 = _cols([5, 1.4])
            c1.markdown(logo_row_html(r["ticker"], r["name"], r["exch"], size=40), unsafe_allow_html=True)
            if c2.button("Analyse →", key=f"sx_{i}", use_container_width=True):
                picked = make_query(r["name"], r["ticker"])
        st.markdown('<div class="sx-note">Matches from the built-in catalog and Yahoo Finance search '
                    '(US and Indian listings).</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="sx-empty">No listed match found for <b>{html.escape(q)}</b>. '
                    'You can still send it to the analyst:</div>', unsafe_allow_html=True)

    if st.button(f"🔎  Analyse \u201c{q}\u201d anyway", key="sx_any", use_container_width=True):
        picked = f"Give me a full analysis of {q}"
    return picked, True