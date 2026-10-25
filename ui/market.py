"""ui/market.py
Live market data for the scrolling ticker strip.
One batched Yahoo Finance request, cached for 5 minutes, and it fails quietly
(returns an empty list) so a data hiccup can never break the app.
After a failure it also waits 90 seconds before retrying, so a dead API
can never stall every rerun of the page.
"""
import time

import streamlit as st
import yfinance as yf

# (Yahoo symbol, label shown on the strip, currency symbol or "" for indices)
TAPE_SYMBOLS = [
    ("^GSPC", "S&P 500", ""),
    ("^IXIC", "NASDAQ", ""),
    ("^NSEI", "NIFTY 50", ""),
    ("^BSESN", "SENSEX", ""),
    ("AAPL", "AAPL", "&#36;"),
    ("NVDA", "NVDA", "&#36;"),
    ("TSLA", "TSLA", "&#36;"),
    ("RELIANCE.NS", "RELIANCE", "₹"),
]


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_tape(symbols: tuple) -> list:
    try:
        data = yf.download(
            list(symbols), period="7d", interval="1d",
            group_by="ticker", progress=False, threads=True,
            auto_adjust=True, timeout=6,
        )
    except Exception:
        return []

    meta = {sym: (label, cur) for sym, label, cur in TAPE_SYMBOLS}
    out = []
    for sym in symbols:
        try:
            closes = data[sym]["Close"].dropna()
            if len(closes) < 2:
                continue
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            if prev == 0:
                continue
            label, cur = meta[sym]
            out.append({"label": label, "price": last, "pct": (last - prev) / prev * 100, "cur": cur})
        except Exception:
            continue
    return out


def get_ticker_data() -> list:
    """Returns [{label, price, pct, cur}, ...]; empty list if Yahoo is unavailable."""
    # After a failure, don't retry for 90 seconds so the page never stalls on a dead API
    if time.time() < st.session_state.get("_tape_retry_at", 0):
        return []
    items = _fetch_tape(tuple(sym for sym, _, _ in TAPE_SYMBOLS))
    if not items:
        _fetch_tape.clear()   # don't keep a failed result cached for 5 minutes
        st.session_state["_tape_retry_at"] = time.time() + 90
    return items