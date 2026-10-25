"""ui/store.py
Saves the watchlist, the recent-research list and the Performance-mode switch to a small
JSON file, and restores them when the app starts in a new browser session.

Single-user by design: everyone who uses this server shares the same file. For a public
deployment set the environment variable FIN_PERSIST=0 (saving is then switched off).
Optional: FIN_DATA_DIR to choose another folder (default: ./data next to the project).

Public API
    load_state()      call once near the top of app.py, right after st.set_page_config()
    persist_state()   call at the end of a run; writes only when something changed
"""
import json
import os
import re
import threading
from pathlib import Path

import streamlit as st

from ui.sidebar import MAX_HISTORY, MAX_WATCH

ENABLED = os.getenv("FIN_PERSIST", "1").strip().lower() not in ("0", "false", "no", "off")
_DIR = Path(os.getenv("FIN_DATA_DIR") or (Path(__file__).resolve().parent.parent / "data"))
_PATH = _DIR / "user_state.json"
_MAX_BYTES = 200_000
_LOCK = threading.Lock()

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&\-^]{0,14}$")
_SENTIMENTS = {"BULLISH", "NEUTRAL", "BEARISH"}


def _txt(value, limit: int) -> str:
    """A safe, single-line string (control characters removed, length capped)."""
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _clean(raw) -> dict:
    """Validate and normalise saved data. Anything unexpected is dropped, never trusted."""
    raw = raw if isinstance(raw, dict) else {}

    watchlist, seen = [], set()
    items = raw.get("watchlist")
    for t in (items if isinstance(items, list) else []):
        t = _txt(t, 15).upper()
        if _TICKER_RE.match(t) and t not in seen:
            seen.add(t)
            watchlist.append(t)
        if len(watchlist) >= MAX_WATCH:
            break

    names_raw = raw.get("names") if isinstance(raw.get("names"), dict) else {}
    names = {}
    for t in watchlist:
        n = _txt(names_raw.get(t), 80)
        if n:
            names[t] = n

    history, seen_h = [], set()
    items = raw.get("history")
    for it in (items if isinstance(items, list) else []):
        if not isinstance(it, dict):
            continue
        ticker = _txt(it.get("ticker"), 15).upper()
        query = _txt(it.get("query"), 200)
        ts = it.get("ts")
        if (not _TICKER_RE.match(ticker) or not query or ticker in seen_h
                or isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts <= 0):
            continue
        sentiment = it.get("sentiment")
        sentiment = sentiment if isinstance(sentiment, str) and sentiment in _SENTIMENTS else None
        seen_h.add(ticker)
        history.append({"query": query, "ticker": ticker, "name": _txt(it.get("name"), 80) or ticker,
                        "sentiment": sentiment, "ts": float(ts)})
        if len(history) >= MAX_HISTORY:
            break

    return {"v": 1, "watchlist": watchlist, "names": names, "history": history, "perf": bool(raw.get("perf"))}


def _read():
    try:
        if not _PATH.is_file() or _PATH.stat().st_size > _MAX_BYTES:
            return None
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        try:                                            # keep a copy of an unreadable file, then start clean
            _PATH.replace(_PATH.with_name("user_state.corrupt.json"))
        except Exception:
            pass
        return None


def _write(snapshot: dict) -> bool:
    with _LOCK:
        try:
            _DIR.mkdir(parents=True, exist_ok=True)
            tmp = _PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, _PATH)                      # atomic: a crash never leaves half a file
            return True
        except Exception:
            return False


def _snapshot() -> dict:
    ss = st.session_state
    return _clean({
        "watchlist": ss.get("watchlist"),
        "names": ss.get("wl_names"),
        "history": ss.get("history"),
        "perf": ss.get("perf_mode", False),
    })


def load_state() -> None:
    """Restore saved data once per browser session. Call right after st.set_page_config()."""
    ss = st.session_state
    if ss.get("_store_loaded"):
        return
    ss["_store_loaded"] = True
    if not ENABLED:
        return
    data = _clean(_read())
    ss["watchlist"] = data["watchlist"]
    ss["wl_names"] = data["names"]
    ss["history"] = data["history"]
    if "perf_mode" not in ss:
        ss["perf_mode"] = data["perf"]
    ss["_store_last"] = json.dumps(data, sort_keys=True)   # so loading never triggers a pointless write


def persist_state() -> None:
    """Write the saved data if (and only if) it changed since the last write."""
    ss = st.session_state
    if not ENABLED or not ss.get("_store_loaded"):
        return
    snap = _snapshot()
    key = json.dumps(snap, sort_keys=True)
    if key == ss.get("_store_last"):
        return
    ss["_store_last"] = key                               # remember even on failure: no retry loop
    if not _write(snap) and not ss.get("_store_warned"):
        ss["_store_warned"] = True
        st.toast("Couldn't save your watchlist to disk. It will be forgotten when you close the app.", icon="⚠️")