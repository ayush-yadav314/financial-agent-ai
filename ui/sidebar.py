"""ui/sidebar.py
Sidebar: branding, controls, performance toggle, watchlist (logos + daily change),
recent research, popular stocks, compact footer.

Public API
    render_sidebar() -> (query | None, history_slot)
        Call inside `with st.sidebar:`. `query` is an analysis request to run (or None).
        `history_slot` is a placeholder for the "Recent research" list, so it can be
        filled AFTER an analysis finishes (a finished analysis then shows up immediately).
    render_history(slot) -> query | None
    record_history(query, ticker, sentiment)
"""
import re
import time
import uuid

import streamlit as st
import yfinance as yf

from ui.catalog import CATALOG, FEATURED, make_query
from ui.data import currency, h, time_ago
from ui.logos import logo_html, prefetch_logos
from ui.search import search_stocks

MAX_WATCH = 12
MAX_HISTORY = 8
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&\-^]{0,14}$")
_SENT = {"BULLISH": ("#10B981", "Bullish"), "NEUTRAL": ("#F59E0B", "Neutral"), "BEARISH": ("#F43F5E", "Bearish")}

# ticker -> display name, from your own catalog
_NAMES = {}
for _i, _n, _tag, _t in FEATURED:
    _NAMES[_t] = _n
for _items in CATALOG.values():
    for _n, _t, _tag in _items:
        _NAMES.setdefault(_t, _n)

_CSS = """
.sb-brand{display:flex;align-items:center;gap:.7rem;margin:.1rem 0 .9rem}
.sb-mark{width:40px;height:40px;flex:0 0 40px;border-radius:12px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent-2));box-shadow:0 8px 24px -10px var(--accent)}
.sb-bt{font-family:var(--font-display);font-weight:700;font-size:1.05rem;line-height:1.2;color:#fff}
.sb-bs{display:flex;align-items:center;gap:.4rem;margin-top:.2rem;font-size:.6rem;letter-spacing:.16em;color:var(--muted)}
.sb-sec{display:flex;align-items:center;gap:.5rem;margin:1.15rem 0 .55rem;font-size:.66rem;letter-spacing:.16em;font-weight:600;color:var(--muted)}
.sb-sec::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border-strong),transparent)}
.sb-row{display:flex;align-items:center;gap:.6rem;min-height:46px;padding:.4rem .55rem;border-radius:12px;border:1px solid var(--border);background:rgba(255,255,255,.03);transition:border-color .2s ease,background .2s ease}
.sb-row:hover{border-color:rgba(34,211,238,.4);background:rgba(34,211,238,.05)}
.sb-mid{flex:1;min-width:0;line-height:1.25}
.sb-n{font-size:.82rem;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sb-t{font-size:.66rem;color:var(--muted);letter-spacing:.04em}
.sb-px{flex:0 0 auto;text-align:right;line-height:1.25}
.sb-p{font-size:.8rem;font-weight:600;color:var(--text);font-variant-numeric:tabular-nums}
.sb-c{font-size:.7rem;font-weight:600;font-variant-numeric:tabular-nums}
.sb-c.up{color:var(--success)}.sb-c.down{color:var(--danger)}.sb-c.na{color:var(--muted);font-weight:400}
.sb-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:.35rem;vertical-align:middle}
.sb-empty{color:var(--muted);font-size:.78rem;line-height:1.55;padding:.15rem 0 .3rem}
.sb-note{color:var(--muted);font-size:.66rem;margin-top:.45rem}
.sb-foot{margin-top:1.3rem;padding-top:.8rem;border-top:1px solid var(--border);font-size:.66rem;line-height:1.75;color:var(--muted)}
[class*="st-key-sb_"] button{min-height:38px;padding:0 .35rem;border-radius:10px}
[class*="st-key-sb_"] button p{font-size:.8rem}
[class*="st-key-sb_new"] button{min-height:42px;font-weight:600}
[data-testid="stSidebar"] [data-testid="stForm"]{border:none !important;padding:0 !important;background:transparent !important}
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button{border-radius:10px;border:1px solid var(--border-strong);background:rgba(255,255,255,.04);color:var(--text);min-height:38px;transition:transform .2s ease,border-color .2s ease,background .2s ease}
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:hover{transform:translateY(-1px);border-color:var(--accent);background:linear-gradient(135deg,rgba(139,92,246,.25),rgba(34,211,238,.2));color:#fff}
"""


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())


def _md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def _section(title: str) -> None:
    _md(f'<div class="sb-sec">{h(title)}</div>')


def _cols(spec):
    """Vertically centred columns where supported (Streamlit 1.36+), plain columns otherwise."""
    try:
        return st.columns(spec, vertical_alignment="center")
    except TypeError:
        return st.columns(spec)


def _init_state() -> None:
    st.session_state.setdefault("watchlist", [])
    st.session_state.setdefault("wl_names", {})
    st.session_state.setdefault("history", [])


def _name_for(ticker: str) -> str:
    return st.session_state.get("wl_names", {}).get(ticker) or _NAMES.get(ticker) or ticker


# ---------------------------------------------------------------------
# watchlist prices: last close vs previous close (daily data from Yahoo)
# ---------------------------------------------------------------------
def _extract_close(data, sym):
    """Close-price Series for one symbol, whatever column layout yfinance returned."""
    for getter in (lambda: data[sym]["Close"], lambda: data["Close"][sym], lambda: data["Close"]):
        try:
            s = getter()
            if getattr(s, "ndim", 0) == 1:
                s = s.dropna()
                if len(s) >= 2:
                    return s
        except Exception:
            continue
    return None


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_quotes(tickers: tuple) -> dict:
    data = yf.download(list(tickers), period="7d", interval="1d", group_by="ticker",
                       progress=False, threads=True, auto_adjust=True, timeout=6)
    out = {}
    for t in tickers:
        s = _extract_close(data, t)
        if s is None:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        if prev:
            out[t] = {"price": last, "pct": (last - prev) / prev * 100}
    if not out:
        raise RuntimeError("no quotes returned")      # never cache a failure
    return {"quotes": out, "fetched_at": time.time()}


def get_quotes(tickers):
    """({ticker: {price, pct}}, fetched_at_epoch). ({}, None) when Yahoo can't provide them."""
    tickers = tuple(tickers)
    if not tickers or time.time() < st.session_state.get("_quotes_retry_at", 0):
        return {}, None
    try:
        res = _fetch_quotes(tickers)
        return res["quotes"], res["fetched_at"]
    except Exception:
        st.session_state["_quotes_retry_at"] = time.time() + 60
        return {}, None


# ---------------------------------------------------------------------
# row rendering
# ---------------------------------------------------------------------
def _quote_row(ticker: str, name: str, quote) -> str:
    if quote:
        up = quote["pct"] >= 0
        px = f'{h(currency(ticker))}{quote["price"]:,.2f}'
        chg = f'<div class="sb-c {"up" if up else "down"}">{"▲" if up else "▼"} {abs(quote["pct"]):.2f}%</div>'
    else:
        px, chg = "—", '<div class="sb-c na">n/a</div>'
    return (f'<div class="sb-row">{logo_html(ticker, name, size=30)}'
            f'<div class="sb-mid"><div class="sb-n">{h(name)}</div><div class="sb-t">{h(ticker)}</div></div>'
            f'<div class="sb-px"><div class="sb-p">{px}</div>{chg}</div></div>')


def _simple_row(ticker: str, name: str, sub_html: str) -> str:
    return (f'<div class="sb-row">{logo_html(ticker, name, size=30)}'
            f'<div class="sb-mid"><div class="sb-n">{h(name)}</div><div class="sb-t">{sub_html}</div></div></div>')


# ---------------------------------------------------------------------
# watchlist add
# ---------------------------------------------------------------------
def _add_to_watchlist(text: str) -> None:
    q = re.sub(r"[^\w .&\-^]", "", text or "").strip()[:40]
    if not q:
        return
    wl = st.session_state.watchlist
    if len(wl) >= MAX_WATCH:
        st.toast(f"Watchlist is full ({MAX_WATCH} stocks). Remove one first.", icon="⚠️")
        return
    found = search_stocks(q, limit=1)
    if found:
        ticker, name = found[0]["ticker"], found[0]["name"]
    elif _TICKER_RE.match(q.upper()):
        ticker, name = q.upper(), q.upper()
    else:
        st.toast(f"Couldn't find “{q}”. Try a ticker like AAPL or HDFCBANK.NS.", icon="⚠️")
        return
    if ticker in wl:
        st.toast(f"{name} is already on your watchlist.", icon="ℹ️")
        return
    wl.append(ticker)
    st.session_state.wl_names[ticker] = name
    st.toast(f"Added {name} ({ticker})", icon="✅")


# ---------------------------------------------------------------------
# history
# ---------------------------------------------------------------------
def record_history(query: str, ticker: str, sentiment) -> None:
    """Remember a finished analysis (one entry per ticker, newest first)."""
    if not ticker:
        return
    hist = st.session_state.setdefault("history", [])
    hist[:] = [x for x in hist if x["ticker"] != ticker]
    hist.insert(0, {"query": query, "ticker": ticker, "name": _NAMES.get(ticker) or ticker,
                    "sentiment": sentiment, "ts": time.time()})
    del hist[MAX_HISTORY:]


def render_history(slot):
    """Draw 'Recent research' into the placeholder. Returns a query if a row was clicked."""
    picked = None
    with slot.container():
        hist = st.session_state.get("history", [])
        if not hist:
            _md('<div class="sb-empty">Your finished analyses will appear here.</div>')
            return None
        prefetch_logos([x["ticker"] for x in hist])
        for item in hist:
            color, label = _SENT.get(item.get("sentiment"), ("#8B93A7", "No verdict"))
            sub = (f'<span class="sb-dot" style="background:{color}"></span>{h(label)} · '
                   f'{h(time_ago(item["ts"]))}')
            c1, c2 = _cols([6, 1.3])
            c1.markdown(_simple_row(item["ticker"], item["name"], sub), unsafe_allow_html=True)
            if c2.button("↻", key=f"sb_h_{item['ticker']}", help=f"Open {item['ticker']} again"):
                picked = item["query"]
    return picked


# ---------------------------------------------------------------------
# the sidebar
# ---------------------------------------------------------------------
_MARK = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" '
         'stroke-linecap="round" stroke-linejoin="round"><polyline points="3 17 9 11 13 15 21 6"/>'
         '<polyline points="15 6 21 6 21 12"/></svg>')


def render_sidebar():
    _init_state()
    _md(f"<style>{_css()}</style>")
    picked = None

    # ---- branding ----
    _md('<div class="sb-brand"><div class="sb-mark">' + _MARK + '</div><div>'
        '<div class="sb-bt">Agentic Finance</div>'
        '<div class="sb-bs"><span class="pulse-dot"></span>AI RESEARCH TERMINAL</div></div></div>')

    # ---- controls ----
    if st.button("🔄  New conversation", key="sb_new", use_container_width=True):
        st.session_state.messages = []
        st.session_state.compare_items = None
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()
    c1, c2 = st.columns(2)
    if c1.button("🧹 Clear history", key="sb_clear", use_container_width=True,
                 help="Forget the recent-research list (your watchlist is kept)"):
        st.session_state.history = []
        st.rerun()
    if c2.button("⟳ Refresh data", key="sb_refresh", use_container_width=True,
                 help="Drop cached market data and retry any data source that failed"):
        st.cache_data.clear()
        for k in [k for k in st.session_state if k.startswith("_retry") or k.endswith("_retry_at")]:
            del st.session_state[k]
        st.toast("Market data cache cleared", icon="🔄")
        st.rerun()

    st.toggle("⚡ Performance mode", key="perf_mode",
              help="Turns off the 3D globe, the typing animation and blur effects. Use it on slower computers.")

    # ---- watchlist ----
    _section("WATCHLIST")
    with st.form("sb_wl_form", clear_on_submit=True):
        typed = st.text_input("Add a stock", label_visibility="collapsed",
                              placeholder="Add by name or ticker",
                              help="For example: HDFC, AAPL, Zomato, TCS.NS")
        submitted = st.form_submit_button("➕  Add to watchlist", use_container_width=True)
    if submitted:
        _add_to_watchlist(typed)

    wl = st.session_state.watchlist
    if not wl:
        _md('<div class="sb-empty">No stocks saved yet. Add one above to track its daily move.</div>')
    else:
        prefetch_logos(wl)
        quotes, fetched = get_quotes(wl)
        for t in list(wl):
            name = _name_for(t)
            a, b, c = _cols([6, 1.15, 1.15])
            a.markdown(_quote_row(t, name, quotes.get(t)), unsafe_allow_html=True)
            if b.button("▶", key=f"sb_wlrun_{t}", help=f"Analyse {name}"):
                picked = make_query(name, t)
            if c.button("✕", key=f"sb_wlrm_{t}", help="Remove from watchlist"):
                wl.remove(t)
                st.rerun()
        note = (f"Daily change = last close vs previous close · prices updated {time_ago(fetched)}"
                if fetched else "Prices unavailable right now (Yahoo Finance). Try Refresh data in a minute.")
        _md(f'<div class="sb-note">{h(note)}</div>')

    # ---- recent research (filled later, after an analysis finishes) ----
    _section("RECENT RESEARCH")
    history_slot = st.empty()

    # ---- popular stocks ----
    _section("POPULAR STOCKS")
    with st.expander("Show popular stocks", expanded=False):
        prefetch_logos([t for _i, _n, _tag, t in FEATURED])
        for i, (_icon, name, tag, ticker) in enumerate(FEATURED):
            a, b = _cols([6, 1.3])
            a.markdown(_simple_row(ticker, name, h(tag)), unsafe_allow_html=True)
            if b.button("▶", key=f"sb_pop_{i}", help=f"Analyse {name}"):
                picked = make_query(name, ticker)

    # ---- footer ----
    _md('<div class="sb-foot">Educational research only. Not financial advice.<br>'
        'Data: Yahoo Finance · AI: Gemini · News: Tavily</div>')

    return picked, history_slot