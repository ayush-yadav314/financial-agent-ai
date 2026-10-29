"""ui/diagnostics.py
A small, hidden diagnostics panel for finding out WHY market data shows N/A on a deployment.
Open the app with ?debug=1 at the end of its address to show it. Normal visitors never see it.

It shows only non-secret facts: the saved-state setting, library versions, whether the API keys are
SET (never their values), recorded data errors, active back-off timers, and a live Yahoo Finance test
that reports the real exception text for each endpoint.
"""
import os
import platform
import re
import time
from importlib.metadata import PackageNotFoundError, version

import streamlit as st
import yfinance as yf

from ui import store


def _ver(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def _backoffs() -> list:
    """Data sources that are currently paused after a failure (and for how many more seconds)."""
    now, out = time.time(), []
    for key, val in st.session_state.items():
        if key.startswith("_retry") and isinstance(val, dict):
            out += [f"{key}[{t}]: {int(until - now)}s left"
                    for t, until in val.items() if isinstance(until, (int, float)) and until > now]
        elif key.endswith("_retry_at") and isinstance(val, (int, float)) and val > now:
            out.append(f"{key}: {int(val - now)}s left")
    return out


def _probe(symbol: str) -> list:
    """Run each Yahoo call on its own and report success or the exact exception."""
    calls = [
        ("history (chart endpoint)", lambda: len(yf.Ticker(symbol).history(period="5d"))),
        ("info (price, P/E, profile)", lambda: len(yf.Ticker(symbol).info or {})),
        ("download (batch endpoint)", lambda: len(yf.download(symbol, period="5d", progress=False, timeout=8))),
    ]
    rows = []
    for label, fn in calls:
        t0 = time.time()
        try:
            n = fn()
            rows.append((label, "ok" if n else "EMPTY RESULT", f"{n} rows/fields returned", time.time() - t0))
        except Exception as e:
            rows.append((label, "FAILED", f"{type(e).__name__}: {str(e)[:300]}", time.time() - t0))
    return rows


def render_diagnostics() -> None:
    if str(st.query_params.get("debug", "")) != "1":
        return
    with st.expander("🛠 Data diagnostics (debug mode)", expanded=True):
        st.markdown(
            f"- **FIN_PERSIST (environment):** `{os.environ.get('FIN_PERSIST')!r}` → saving is "
            f"**{'ON' if store.ENABLED else 'OFF'}**\n"
            f"- **Python** {platform.python_version()} · **streamlit** {_ver('streamlit')} · "
            f"**yfinance** {_ver('yfinance')}\n"
            f"- **API keys set:** GOOGLE_API_KEY = {bool(os.getenv('GOOGLE_API_KEY'))}, "
            f"TAVILY_API_KEY = {bool(os.getenv('TAVILY_API_KEY'))} (values are never shown)"
        )
        errs = st.session_state.get("_hist_err", {})
        st.markdown("**Recorded price-history errors:** "
                    + (", ".join(f"{k}: {v}" for k, v in errs.items()) or "none"))
        paused = _backoffs()
        st.markdown("**Paused data sources (back-off):** " + (", ".join(paused) or "none"))

        symbol = st.text_input("Symbol to test", value="AAPL", key="dbg_symbol").strip().upper()
        if st.button("Run live Yahoo Finance test", key="dbg_run"):
            if not re.fullmatch(r"[A-Z0-9.^-]{1,15}", symbol):
                st.warning("Enter a valid symbol such as AAPL or TCS.NS.")
            else:
                with st.spinner("Calling Yahoo Finance…"):
                    rows = _probe(symbol)
                for label, status, detail, secs in rows:
                    st.markdown(f"{'✅' if status == 'ok' else '❌'} **{label}**: {status} ({secs:.1f}s)")
                    st.code(detail)
                st.caption("If history is ok but info FAILED (often a 429 or 'Too Many Requests' message), Yahoo is "
                           "throttling the quote endpoint for this server: prices and fundamentals go missing "
                           "while charts can still load.")