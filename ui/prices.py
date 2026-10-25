"""ui/prices.py
Daily price history and the statistics derived from it (Yahoo Finance via yfinance).
Shared by the report chart, the scorecard and the comparison view. Nothing is invented:
when Yahoo returns no history and there is no earlier copy, get_price_stats() returns {}
and callers show "N/A".

If a refresh fails but an earlier successful copy exists, that copy is used and flagged
stale=True, so the chart keeps working through brief Yahoo outages. Nothing is hidden:
the data's true age is always in fetched_at.

Prices are Yahoo's split- and dividend-adjusted daily values, so returns are
total-return style figures.

Public API
    get_price_stats(ticker) -> dict
        price, prev, pct (daily %), low_52, high_52, pos_52 (0-1),
        ret_6m, ret_1y (fractions), dates, open, high, low, close, volume (lists),
        last_date, fetched_at, stale (bool)
    price_error(ticker) -> str     why the last fetch failed ('' if it didn't)
"""
import re
import time

import streamlit as st
import yfinance as yf

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&\-^]{0,14}$")

# last successful history per ticker. Survives cache expiry and is shared by every session
# in this server process, so a brief Yahoo outage never blanks charts that worked before.
_LAST_GOOD = {}


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_history(ticker: str) -> dict:
    hist = yf.Ticker(ticker).history(period="1y")      # may raise; exceptions are never cached
    if hist is None or hist.empty:
        raise RuntimeError("Yahoo returned an empty price history")
    hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
    if len(hist) < 5:
        raise RuntimeError("Yahoo returned too little price history")
    vol = hist["Volume"] if "Volume" in hist else None
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in hist.index],
        "open": [float(x) for x in hist["Open"]],
        "close": [float(x) for x in hist["Close"]],
        "high": [float(x) for x in hist["High"]],
        "low": [float(x) for x in hist["Low"]],
        "volume": [float(x) if x == x else 0.0 for x in vol] if vol is not None else [],
        "fetched_at": time.time(),
    }


def price_error(ticker: str) -> str:
    """Why the most recent fetch for this ticker failed ('' if it hasn't)."""
    return st.session_state.get("_hist_err", {}).get((ticker or "").strip().upper(), "")


def get_price_stats(ticker: str) -> dict:
    """Statistics from one year of daily data, or {} if Yahoo can't provide it and nothing is saved."""
    t = (ticker or "").strip().upper()
    if not _TICKER_RE.match(t):
        return {}
    retry = st.session_state.setdefault("_retry_hist", {})
    errs = st.session_state.setdefault("_hist_err", {})

    stale = False
    if time.time() < retry.get(t, 0):                  # failed recently: don't hammer Yahoo
        d = _LAST_GOOD.get(t)
        stale = d is not None
    else:
        try:
            d = _fetch_history(t)
            _LAST_GOOD[t] = d
            errs.pop(t, None)
        except Exception as e:
            retry[t] = time.time() + 45
            errs[t] = f"{type(e).__name__}: {str(e)[:160]}"
            d = _LAST_GOOD.get(t)
            stale = d is not None
    if not d:
        return {}

    close, n = d["close"], len(d["close"])
    last, prev = close[-1], close[-2]
    low, high = min(d["low"]), max(d["high"])
    return {
        "price": last,
        "prev": prev,
        "pct": (last - prev) / prev * 100 if prev else None,
        "low_52": low,
        "high_52": high,
        "pos_52": (last - low) / (high - low) if high > low else None,
        "ret_6m": (last / close[-127] - 1) if n > 126 and close[-127] else None,
        "ret_1y": (last / close[0] - 1) if n >= 240 and close[0] else None,
        "dates": d["dates"],
        "open": d["open"],
        "high": d["high"],
        "low": d["low"],
        "close": close,
        "volume": d["volume"],
        "last_date": d["dates"][-1],
        "fetched_at": d["fetched_at"],
        "stale": stale,
    }