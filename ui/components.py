"""ui/components.py
Reusable HTML components. Each function renders one UI piece.
"""
import streamlit as st


def render_hero(title_plain: str, title_gradient: str, subtitle: str, chips: list) -> None:
    """Animated hero header at the top of the page."""
    chips_html = "".join(f'<span class="hero-chip">{c}</span>' for c in chips)
    html = "".join([
        '<div class="hero">',
        '<div class="hero-eyebrow"><span class="pulse-dot"></span>LIVE MULTI-AGENT RESEARCH</div>',
        f'<div class="hero-title" role="heading" aria-level="1">{title_plain} <span class="gradient-text">{title_gradient}</span></div>',
        f'<div class="hero-sub">{subtitle}</div>',
        f'<div class="hero-chips">{chips_html}</div>',
        '</div>',
    ])
    st.markdown(html, unsafe_allow_html=True)


def currency_symbol(ticker: str) -> str:
    """Indian listings (.NS / .BO) trade in rupees; everything else defaults to $.
    '$' is written as an HTML entity so Streamlit never treats it as a LaTeX delimiter."""
    return "₹" if (ticker or "").upper().endswith((".NS", ".BO")) else "&#36;"


def _counter(value, decimals: int = 2, prefix: str = "") -> str:
    """A number that counts up from zero using pure CSS (no JavaScript)."""
    if not isinstance(value, (int, float)):
        return "N/A"
    v = round(float(value), decimals)
    whole = int(v)
    frac = int(round((v - whole) * 10 ** decimals)) if decimals else 0
    cls = "cnt cnt-dec" if decimals else "cnt"
    return f'<span class="{cls}" data-p="{prefix}" style="--i:{whole};--f:{frac};"></span>'


def render_metric_cards(metrics: dict, ticker: str = "") -> None:
    """Animated glass metric cards: price (+ day change), P/E, and 52-week range bar."""
    if not metrics:
        st.caption("⚠️ Financial metrics unavailable for this ticker right now (data source may be temporarily rate-limited).")
        return
    try:
        sym = currency_symbol(ticker)
        price, pe = metrics.get("price"), metrics.get("pe")
        low, high, prev = metrics.get("low_52"), metrics.get("high_52"), metrics.get("prev_close")

        delta = ""
        if price and prev:
            diff = price - prev
            pct = diff / prev * 100
            cls, arrow = ("up", "▲") if diff >= 0 else ("down", "▼")
            delta = f'<div class="mc-delta {cls}">{arrow} {abs(diff):.2f} ({abs(pct):.2f}%) today</div>'

        range_val, bar = "N/A", ""
        if low and high:
            range_val = (_counter(low, 0, sym) + '<span class="mc-sep"> – </span>' + _counter(high, 0, sym))
            if price and high > low:
                pos = max(0.0, min(100.0, (price - low) / (high - low) * 100))
                bar = (f'<div class="mc-range"><div class="mc-range-fill" style="--w:{pos:.1f}%"></div>'
                       f'<div class="mc-range-dot" style="--w:{pos:.1f}%"></div></div>')

        html = "".join([
            '<div class="mc-grid">',
            f'<div class="mc"><div class="mc-label">Price</div><div class="mc-value">{_counter(price, 2, sym)}</div>{delta}</div>',
            f'<div class="mc"><div class="mc-label">P/E Ratio</div><div class="mc-value">{_counter(pe, 2)}</div>'
            '<div class="mc-sub">price ÷ yearly earnings</div></div>',
            f'<div class="mc"><div class="mc-label">52-Week Range</div><div class="mc-value mc-value-sm">{range_val}</div>{bar}</div>',
            '</div>',
        ])
        st.markdown(html, unsafe_allow_html=True)
    except Exception:
        pass


def render_sentiment_badge(sentiment: str) -> None:
    """Verdict pill + animated gauge whose needle swings to bearish / neutral / bullish."""
    styles = {
        "BULLISH": ("#10B981", "🟢 Bullish", 62),
        "NEUTRAL": ("#F59E0B", "🟡 Neutral", 0),
        "BEARISH": ("#F43F5E", "🔴 Bearish", -62),
    }
    color, label, angle = styles.get(sentiment, ("#8B93A7", "⚪ Unclear", None))
    gauge = ""
    if angle is not None:
        gauge = ('<div class="gauge"><div class="gauge-arc"></div>'
                 f'<div class="gauge-needle" style="--a:{angle}deg;--c:{color};"></div>'
                 '<div class="gauge-hub"></div></div>')
    html = (
        '<div class="verdict">'
        f'<div class="verdict-pill" style="--c:{color};">{label}</div>'
        f'{gauge}</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# Yahoo Finance ticker suffix -> exchange label shown in the report header
_EXCHANGES = {
    ".NS": "NSE · INDIA", ".BO": "BSE · INDIA", ".L": "LSE · LONDON",
    ".DE": "XETRA · GERMANY", ".T": "TSE · TOKYO", ".HK": "HKEX · HONG KONG",
    ".TO": "TSX · TORONTO", ".AX": "ASX · SYDNEY", ".SI": "SGX · SINGAPORE",
    ".SS": "SSE · SHANGHAI", ".SZ": "SZSE · SHENZHEN", ".SA": "B3 · BRAZIL",
}


def render_report_header(ticker: str, sentiment: str = None) -> None:
    """Glowing banner above each report: ticker, exchange, and the sentiment color."""
    import html as _html

    colors = {"BULLISH": "#10B981", "NEUTRAL": "#F59E0B", "BEARISH": "#F43F5E"}
    color = colors.get(sentiment, "#22D3EE")
    t = (ticker or "").upper()
    exchange = "US MARKETS"
    for suffix, name in _EXCHANGES.items():
        if t.endswith(suffix):
            exchange = name
            break
    html = "".join([
        f'<div class="rh" style="--c:{color};">',
        '<div>',
        '<div class="rh-eyebrow">AI RESEARCH REPORT</div>',
        f'<div class="rh-ticker">{_html.escape(t)}</div>',
        f'<div class="rh-ex">{exchange}</div>',
        '</div>',
        '<div class="rh-chips">',
        '<span class="rh-chip">✓ 3-agent pipeline</span>',
        '<span class="rh-chip">✓ Live market data</span>',
        '<span class="rh-chip">✓ News sentiment</span>',
        '</div>',
        '</div>',
    ])
    st.markdown(html, unsafe_allow_html=True)


_PIPE_STEPS = [
    ("🔎", "Identify"),
    ("📡", "Research"),
    ("🧠", "Analyze"),
    ("📄", "Report"),
]


def render_pipeline(stage: int, ticker: str = "") -> str:
    """Glowing agent-pipeline tracker. Returns HTML (pass it to st.markdown).

    stage: 0 = identifying ticker, 1 = researching, 2 = analyzing, 3 = report ready.
    """
    import html as _html

    subs = {
        0: "Resolving ticker…",
        2: "Gemini writes the report",
        3: "Chart · metrics · verdict",
    }
    parts = ['<div class="pipe">']
    for i, (icon, title) in enumerate(_PIPE_STEPS):
        done = i < stage or stage >= 3
        active = (i == stage) and stage < 3
        state = "done" if done else ("active" if active else "")
        if i == 0 and ticker and (done or active):
            sub = f"Resolved: {_html.escape(ticker)}"
        elif i == 1:
            sub = '<span class="pipe-chip">Yahoo Finance</span><span class="pipe-chip">Tavily</span>'
        else:
            sub = subs.get(i, "")
        parts.append(
            f'<div class="pipe-node {state}"><div class="pipe-icon">{"✓" if done else icon}</div>'
            f'<div class="pipe-title">{title}</div><div class="pipe-sub">{sub}</div></div>'
        )
        if i < len(_PIPE_STEPS) - 1:
            parts.append(f'<div class="pipe-link {state}"></div>')
    parts.append("</div>")
    return "".join(parts)


def render_market_tape(items: list) -> None:
    """Scrolling live-market ticker strip. items: [{label, price, pct, cur}, ...]."""
    if not items:
        return
    import html as _html

    def chip(it: dict) -> str:
        up = it["pct"] >= 0
        return (
            '<span class="tape-item">'
            f'<span class="tape-sym">{_html.escape(it["label"])}</span>'
            f'<span class="tape-px">{it.get("cur", "")}{it["price"]:,.2f}</span>'
            f'<span class="tape-chg {"up" if up else "down"}">{"▲" if up else "▼"} {abs(it["pct"]):.2f}%</span>'
            '</span>'
        )

    row = "".join(chip(i) for i in items)
    # the row is repeated twice so the scroll loops seamlessly
    st.markdown(f'<div class="tape"><div class="tape-track">{row}{row}</div></div>', unsafe_allow_html=True)