"""ui/compare.py
Side-by-side stock comparison: rebased performance chart, key metrics table and
explainable rule-based scorecards. Everything comes from Yahoo Finance data.

Public API
    render_compare_entry()                     expander (one-click pairs + custom form) that starts a comparison
    render_compare_view(items) -> query|None   the comparison page; returns an analysis request
                                               if a "Full AI analysis" button was clicked
"""
import re

import plotly.graph_objects as go
import streamlit as st

from ui.catalog import make_query
from ui.data import _num, currency, fmt_cap, fmt_pct, fmt_ratio, get_profile, h, time_ago
from ui.logos import logo_html, prefetch_logos
from ui.prices import get_price_stats
from ui.report import _rec_label
from ui.scorecard import compute_scorecard, render_score_matrix
from ui.search import search_stocks

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&\-^]{0,14}$")
_COLORS = ["#22D3EE", "#8B5CF6", "#F59E0B"]
_RANGES = {"1M": 21, "3M": 63, "6M": 126, "1Y": None}
_PAIRS = [
    [("HDFC Bank", "HDFCBANK.NS"), ("ICICI Bank", "ICICIBANK.NS")],
    [("TCS", "TCS.NS"), ("Infosys", "INFY.NS")],
    [("NVIDIA", "NVDA"), ("AMD", "AMD")],
    [("Apple", "AAPL"), ("Microsoft", "MSFT")],
]
NA = '<span class="cp-na">N/A</span>'

_CSS = """
.cp-top{display:flex;align-items:center;gap:.7rem;margin:.2rem 0 .8rem}
.cp-title{font-family:var(--font-display);font-weight:700;font-size:1.4rem;color:#fff}
.cp-heads{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:.8rem;margin-bottom:.6rem}
.cp-hc{display:flex;align-items:center;gap:.8rem;padding:.9rem 1rem;border-radius:var(--radius);border:1px solid var(--border);border-top:2px solid var(--k);background:rgba(10,14,26,.72);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);min-width:0}
.cp-hnm{font-weight:700;color:#fff;font-size:1.02rem;line-height:1.25}
.cp-hs{font-size:.74rem;color:var(--muted);letter-spacing:.04em;margin-top:.1rem}
.cp-tbl{border:1px solid var(--border);border-radius:var(--radius);background:rgba(10,14,26,.66);overflow-x:auto}
.cp-r{display:grid;grid-template-columns:160px repeat(var(--n),minmax(130px,1fr));gap:.6rem;align-items:center;padding:.65rem .9rem;border-top:1px solid var(--border);min-width:520px;transition:background .2s ease}
.cp-r:first-child{border-top:none}
.cp-r:hover{background:rgba(34,211,238,.04)}
.cp-l{font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.cp-c{font-weight:600;color:var(--text);font-variant-numeric:tabular-nums;line-height:1.35}
.cp-c small{display:block;font-weight:400;font-size:.7rem;color:var(--muted)}
.cp-d{margin-left:.45rem;font-size:.76rem;font-weight:600}
.cp-up{color:var(--success)}.cp-down{color:var(--danger)}.cp-na{color:var(--muted);font-weight:400}
"""


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())


def _md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def _exchange(t: str) -> str:
    t = t.upper()
    return "NSE" if t.endswith(".NS") else "BSE" if t.endswith(".BO") else "US"


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[()]", "", name or "")).strip()


# ---------------------------------------------------------------------
# table cells (each returns an HTML fragment)
# ---------------------------------------------------------------------
def _t(text) -> str:
    return NA if text in (None, "", "N/A") else h(text)


def _c_price(t, s) -> str:
    if not s:
        return NA
    d = ""
    if s.get("pct") is not None:
        up = s["pct"] >= 0
        d = f'<span class="cp-d {"cp-up" if up else "cp-down"}">{"▲" if up else "▼"} {abs(s["pct"]):.2f}%</span>'
    return f'{h(currency(t))}{s["price"]:,.2f}{d}<small>last close {h(s["last_date"])}</small>'


def _c_ret(v) -> str:
    if v is None:
        return NA
    return f'<span class="{"cp-up" if v >= 0 else "cp-down"}">{v * 100:+.1f}%</span>'


def _c_range(t, s) -> str:
    if not s or s.get("pos_52") is None:
        return NA
    cur = h(currency(t))
    return f'{s["pos_52"] * 100:.0f}% of range<small>{cur}{s["low_52"]:,.0f} – {cur}{s["high_52"]:,.0f}</small>'


def _c_target(t, p, s) -> str:
    target = _num(p.get("target_mean"))
    if not target:
        return NA
    cur, price = h(currency(t)), (s or {}).get("price")
    if price:
        return f'{cur}{target:,.2f}<small>{(target - price) / price * 100:+.1f}% vs last close</small>'
    return f"{cur}{target:,.2f}"


def _c_view(p) -> str:
    label = _rec_label(p.get("recommendation"))
    if label == "N/A":
        return NA
    n = _num(p.get("analysts"))
    return f'{h(label)}<small>{int(n)} analysts</small>' if n else h(label)


# ---------------------------------------------------------------------
# performance chart
# ---------------------------------------------------------------------
def _perf_chart(tickers, stats, days):
    fig = go.Figure()
    added = 0
    for i, t in enumerate(tickers):
        s = stats.get(t)
        if not s:
            continue
        k = len(s["close"]) if days is None else min(days + 1, len(s["close"]))
        close, dates = s["close"][-k:], s["dates"][-k:]
        if len(close) < 2 or not close[0]:
            continue
        y = [v / close[0] * 100 for v in close]
        fig.add_trace(go.Scatter(
            x=dates, y=y, mode="lines", name=f"{t} ({y[-1] - 100:+.1f}%)",
            line=dict(color=_COLORS[i % 3], width=2.4),
            hovertemplate=t + ": %{y:.1f}<extra></extra>",
        ))
        added += 1
    if not added:
        return None
    fig.add_hline(y=100, line=dict(color="rgba(255,255,255,.18)", dash="dot"))
    fig.update_layout(
        template="plotly_dark", height=380,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified",
        font=dict(family="Inter, sans-serif", color="#8B93A7"),
        title=dict(text="Performance, rebased to 100 at the start of the range", x=0.01,
                   font=dict(family="Space Grotesk, sans-serif", size=15, color="#E6EAF2")),
        legend=dict(orientation="h", x=1, xanchor="right", y=1.14),
        hoverlabel=dict(bgcolor="rgba(10,14,26,.94)", bordercolor="rgba(34,211,238,.45)",
                        font=dict(family="Inter, sans-serif", size=12, color="#E6EAF2")),
    )
    fig.update_xaxes(showgrid=False, showspikes=True, spikemode="across", spikethickness=1,
                     spikedash="dot", spikecolor="rgba(34,211,238,.55)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.06)", zeroline=False)
    return fig


# ---------------------------------------------------------------------
# the comparison page
# ---------------------------------------------------------------------
def render_compare_view(items):
    items = [i for i in (items or []) if i.get("ticker")][:3]
    if len(items) < 2:
        st.session_state.compare_items = None
        return None
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)

    tickers = [i["ticker"] for i in items]
    prefetch_logos(tickers)
    with st.spinner("Loading comparison data…"):
        profiles = {t: get_profile(t) for t in tickers}
        stats = {t: get_price_stats(t) for t in tickers}
    names = {i["ticker"]: _clean_name(profiles[i["ticker"]].get("name") or i.get("name") or i["ticker"])
             for i in items}
    n = len(tickers)

    top, close = st.columns([5, 1.4])
    top.markdown(f'<div class="cp-top"><div class="cp-title">⚖️ {h(" vs ".join(names[t] for t in tickers))}</div></div>',
                 unsafe_allow_html=True)
    if close.button("✕ Close comparison", key="cmp_close", use_container_width=True):
        st.session_state.compare_items = None
        st.rerun()

    if not any(profiles[t] or stats[t] for t in tickers):
        st.error("Couldn't load data for these stocks right now (Yahoo Finance may be rate-limiting). "
                 "Wait a minute, use ⟳ Refresh data in the sidebar, and try again.")
        return None
    for t in tickers:
        if not profiles[t] and not stats[t]:
            st.warning(f"No data found for {t}. Check the ticker symbol.")
        elif not profiles[t]:
            st.caption(f"⚠️ Company fundamentals for {t} are unavailable right now; only price data is shown.")

    # ---- header cards ----
    heads = "".join(
        f'<div class="cp-hc" style="--k:{_COLORS[i % 3]};">'
        f'{logo_html(t, names[t], 44, profiles[t].get("website") or "")}'
        f'<div style="min-width:0;"><div class="cp-hnm">{h(names[t])}</div>'
        f'<div class="cp-hs">{" · ".join(h(x) for x in (t, profiles[t].get("exchange") or _exchange(t), profiles[t].get("sector")) if x)}</div></div></div>'
        for i, t in enumerate(tickers)
    )
    _md(f'<div class="cp-heads" style="--n:{n};">{heads}</div>')

    picked = None
    for col, t in zip(st.columns(n), tickers):
        if col.button(f"🧠 Full AI analysis · {names[t]}", key=f"cmp_run_{t}", use_container_width=True):
            picked = make_query(names[t], t)

    # ---- performance chart ----
    st.markdown("###### Performance")
    rng = st.radio("Range", list(_RANGES), index=2, horizontal=True, key="cmp_range", label_visibility="collapsed")
    fig = _perf_chart(tickers, stats, _RANGES[rng])
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
    else:
        st.caption("Price history is unavailable right now, so the chart can't be drawn.")

    # ---- metrics table ----
    st.markdown("###### Key metrics")
    spec = [
        ("Last price", lambda t: _c_price(t, stats[t])),
        ("Market cap", lambda t: _t(fmt_cap(profiles[t].get("market_cap"), t))),
        ("Forward P/E", lambda t: _t(fmt_ratio(profiles[t].get("forward_pe")))),
        ("Price / Book", lambda t: _t(fmt_ratio(profiles[t].get("price_to_book")))),
        ("Beta", lambda t: _t(fmt_ratio(profiles[t].get("beta")))),
        ("Profit margin", lambda t: _t(fmt_pct(profiles[t].get("profit_margin")))),
        ("Revenue growth", lambda t: _t(fmt_pct(profiles[t].get("revenue_growth")))),
        ("Return on equity", lambda t: _t(fmt_pct(profiles[t].get("roe")))),
        ("6-month return", lambda t: _c_ret(stats[t].get("ret_6m"))),
        ("1-year return", lambda t: _c_ret(stats[t].get("ret_1y"))),
        ("52-week position", lambda t: _c_range(t, stats[t])),
        ("Analyst target", lambda t: _c_target(t, profiles[t], stats[t])),
        ("Analyst view", lambda t: _c_view(profiles[t])),
    ]
    rows = "".join(
        f'<div class="cp-r"><div class="cp-l">{h(label)}</div>'
        + "".join(f'<div class="cp-c">{fn(t)}</div>' for t in tickers) + "</div>"
        for label, fn in spec
    )
    _md(f'<div class="cp-tbl" style="--n:{n};">{rows}</div>')
    if len({currency(t) for t in tickers}) > 1:
        st.caption("These stocks trade in different currencies. Compare ratios and returns, not absolute "
                   "prices or market caps.")

    # ---- scorecards ----
    st.markdown("###### Research scorecard")
    render_score_matrix([(names[t], t, compute_scorecard(profiles[t], stats[t], t)) for t in tickers])

    # ---- freshness ----
    lines = []
    for t in tickers:
        s, p = stats[t], profiles[t]
        bits = []
        if s:
            bits.append(f"last close {s['last_date']} (fetched {time_ago(s['fetched_at'])})")
        if p.get("fetched_at"):
            bits.append(f"fundamentals fetched {time_ago(p['fetched_at'])}")
        lines.append(f"<b>{h(t)}:</b> " + (h(" · ".join(bits)) if bits else "no data"))
    _md('<div class="rp-foot">' + "<br>".join(lines) +
        "<br>Source: Yahoo Finance daily data (adjusted for splits and dividends), cached up to 10-15 minutes. "
        "Educational research only. Not financial advice.</div>")
    return picked


# ---------------------------------------------------------------------
# the entry point: one-click pairs + custom form
# ---------------------------------------------------------------------
def _resolve(text):
    q = re.sub(r"[^\w .&\-^]", "", text or "").strip()[:40]
    if not q:
        return None
    found = search_stocks(q, limit=1)
    if found:
        return {"ticker": found[0]["ticker"], "name": found[0]["name"]}
    if _TICKER_RE.match(q.upper()):
        return {"ticker": q.upper(), "name": q.upper()}
    return None


def render_compare_entry() -> None:
    with st.expander("⚖️  Compare stocks side by side", expanded=False):
        st.caption("Pick a popular pair, or enter two or three stocks by name or ticker.")
        cols = st.columns(len(_PAIRS))
        for i, (col, pair) in enumerate(zip(cols, _PAIRS)):
            if col.button(" vs ".join(n for n, _t in pair), key=f"cmp_pair_{i}", use_container_width=True):
                st.session_state.compare_items = [{"ticker": t, "name": n} for n, t in pair]
                st.rerun()

        with st.form("cmp_form", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            a = c1.text_input("First stock", placeholder="e.g. Reliance", key="cmp_a")
            b = c2.text_input("Second stock", placeholder="e.g. NVIDIA", key="cmp_b")
            c = c3.text_input("Third (optional)", placeholder="optional", key="cmp_c")
            submitted = st.form_submit_button("Compare →", use_container_width=True)

        if submitted:
            items, seen, bad = [], set(), []
            for text in (a, b, c):
                if not (text or "").strip():
                    continue
                r = _resolve(text)
                if r is None:
                    bad.append(text.strip())
                elif r["ticker"] not in seen:
                    seen.add(r["ticker"])
                    items.append(r)
            if bad:
                st.warning("Couldn't find: " + ", ".join(bad) + ". Try a ticker like AAPL or HDFCBANK.NS.")
            elif len(items) < 2:
                st.warning("Enter at least two different stocks.")
            else:
                st.session_state.compare_items = items
                st.rerun()