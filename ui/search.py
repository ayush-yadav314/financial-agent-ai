"""ui/search.py
Global stock search: logos, names, tickers and exchanges, backed by your own catalog
plus Yahoo Finance's live search. Picking a result starts your existing analysis workflow.

Streamlit's text box updates on Enter (not on every keystroke), so results appear when
the user presses Enter.

Public API
    render_search(key="stock_search") -> bool     True while the box has text
    search_stocks(text, limit=8) -> list[dict]    (name, ticker, exch, source)
"""
import html
import re
import time

import streamlit as st

from ui.catalog import CATALOG, FEATURED, make_query
from ui.logos import logo_row_html, prefetch_logos

_CSS = """
[class*="st-key-sx_panel"]{padding:.5rem .7rem;border-radius:12px;border:1px solid var(--border-strong);background:rgba(15,20,32,.92);margin:.1rem 0 .8rem}
[class*="st-key-sx_row_"] button{min-height:36px;padding:.2rem .8rem}
[class*="st-key-sx_row_"] button p{font-size:.84rem}
.sx-note{color:var(--muted);font-size:.74rem;margin:.4rem 0 .5rem}
.sx-empty{color:var(--muted);font-size:.86rem;padding:.5rem .1rem}
"""

# extra well-known listings (display name, Yahoo ticker): typed from memory, not verified one by one
_EXTRA = [
    ("Tata Motors (Passenger Vehicles)", "TMPV.NS"), ("Tata Motors (Commercial Vehicles)", "TMCV.NS"),
    ("Tata Power", "TATAPOWER.NS"), ("Adani Enterprises", "ADANIENT.NS"), ("Maruti Suzuki", "MARUTI.NS"),
    ("Sun Pharma", "SUNPHARMA.NS"), ("Asian Paints", "ASIANPAINT.NS"), ("Titan Company", "TITAN.NS"),
    ("Nestle India", "NESTLEIND.NS"), ("UltraTech Cement", "ULTRACEMCO.NS"), ("ONGC", "ONGC.NS"),
    ("NTPC", "NTPC.NS"), ("HCL Technologies", "HCLTECH.NS"), ("Tech Mahindra", "TECHM.NS"),
    ("Coal India", "COALINDIA.NS"), ("Power Grid", "POWERGRID.NS"),
    ("Costco", "COST"), ("Home Depot", "HD"), ("McDonald's", "MCD"), ("Starbucks", "SBUX"),
    ("PepsiCo", "PEP"), ("Procter & Gamble", "PG"), ("UnitedHealth", "UNH"), ("Eli Lilly", "LLY"),
    ("Bank of America", "BAC"), ("Goldman Sachs", "GS"), ("Qualcomm", "QCOM"), ("Cisco", "CSCO"),
    ("IBM", "IBM"), ("Uber", "UBER"), ("PayPal", "PYPL"), ("Shopify", "SHOP"), ("Airbnb", "ABNB"),
    ("Coinbase", "COIN"), ("Micron", "MU"), ("Snowflake", "SNOW"), ("CrowdStrike", "CRWD"),
]

# extra words people search for, mapped to the ticker they mean
_ALT = {
    "TCS.NS": "tata consultancy services", "RELIANCE.NS": "reliance industries jio",
    "INFY.NS": "infosys", "HDFCBANK.NS": "hdfc bank", "SBIN.NS": "sbi state bank of india",
    "GOOGL": "alphabet google", "META": "meta platforms facebook instagram",
    "BRK-B": "berkshire hathaway warren buffett", "TMPV.NS": "tata motors jaguar land rover jlr",
    "TMCV.NS": "tata motors trucks buses", "ADANIENT.NS": "adani", "LT.NS": "l&t larsen and toubro",
    "HINDUNILVR.NS": "hul hindustan unilever", "BHARTIARTL.NS": "airtel", "TSM": "taiwan semiconductor",
    "NVDA": "nvidia geforce", "TSLA": "tesla elon musk", "AMZN": "amazon aws",
}


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
# local index (your featured cards + catalog + extras)
# ---------------------------------------------------------------------
_LOCAL = None


def _local_index() -> list:
    global _LOCAL
    if _LOCAL is None:
        seen, out = set(), []
        rows = [(n, t) for _i, n, _tag, t in FEATURED]
        for items in CATALOG.values():
            rows += [(n, t) for n, t, _tag in items]
        rows += _EXTRA
        for name, ticker in rows:
            if ticker in seen:
                continue
            seen.add(ticker)
            out.append({"name": _clean_name(name), "ticker": ticker, "exch": _exchange(ticker),
                        "source": "catalog", "alt": _ALT.get(ticker, "")})
        _LOCAL = out
    return _LOCAL


def _score(q: str, name: str, ticker: str, alt: str = ""):
    """Lower is better; None means no match."""
    n, t, a = name.lower(), ticker.lower(), alt.lower()
    base = t.split(".")[0]
    if q == t or q == base:
        return 0
    if t.startswith(q):
        return 1
    if n.startswith(q):
        return 2
    if any(w.startswith(q) for w in re.split(r"[\s&.\-/]+", f"{n} {a}") if w):
        return 3
    if q in n or q in t or q in a:
        return 4
    return None


def _search_local(q: str) -> list:
    ranked = []
    for item in _local_index():
        s = _score(q, item["name"], item["ticker"], item["alt"])
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


def _pick(query: str, key: str) -> None:
    """Button callback: start the analysis and clear the search box.
    Callbacks run before widgets are rebuilt, so it is allowed to reset the text box here."""
    st.session_state.pending_query = query
    st.session_state.compare_items = None
    st.session_state[key] = ""


def render_search(key: str = "stock_search") -> bool:
    """Search bar + results panel. Returns True while the box has text."""
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)
    raw = st.text_input(
        "Search stocks", key=key, label_visibility="collapsed",
        placeholder="🔍  Search a company or ticker, then press Enter (e.g. HDFC, MSFT, Tata, Zomato)",
    )
    q = re.sub(r"[^\w .&\-]", "", raw or "").strip()[:50]
    if not q:
        return False

    results = search_stocks(q)
    prefetch_logos([r["ticker"] for r in results])

    with st.container(key="sx_panel"):
        if results:
            for i, r in enumerate(results):
                c1, c2 = _cols([5, 1.4])
                c1.markdown(logo_row_html(r["ticker"], r["name"], r["exch"], size=36), unsafe_allow_html=True)
                c2.button("Analyse", key=f"sx_row_{i}", use_container_width=True,
                          on_click=_pick, args=(make_query(r["name"], r["ticker"]), key))
            st.markdown('<div class="sx-note">Matches from the built-in catalog and Yahoo Finance search '
                        '(US and Indian listings).</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="sx-empty">No listed match found for <b>{html.escape(q)}</b>. '
                        'You can still send it to the analyst:</div>', unsafe_allow_html=True)
        st.button(f"🔎  Analyse “{q}” anyway", key="sx_row_any", use_container_width=True,
                  on_click=_pick, args=(f"Give me a full analysis of {q}", key))
    return True