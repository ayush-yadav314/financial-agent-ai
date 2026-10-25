"""ui/overview.py
Market overview panel: market pulse, major indices, top movers and a sector heatmap.

Everything comes from Yahoo Finance daily data (via yfinance). Nothing is invented:
data that Yahoo does not return is simply missing, and failures show a notice.

Scope (stated in the panel itself)
- Indices: S&P 500, NASDAQ, Dow Jones, NIFTY 50, SENSEX (any index Yahoo does not return is skipped).
- Pulse, movers and the heatmap cover only the stocks in this app's built-in catalog, not the whole market.
- Sector groups are a simple classification made for this app (see SECTORS). A sector's figure is the
  equal-weighted average daily change of its stocks that returned data.
- Each stock's change is its own latest session vs the session before it, so US and Indian stocks can come
  from different days. The date is shown on every row and tile.
- The mood label is a plain count of stocks up vs down. It is not a prediction.

Public API
    render_overview_entry()   a toggle; the panel loads only while it is switched on
    render_overview()         the panel itself
"""
import time

import streamlit as st
import yfinance as yf

from ui.catalog import CATALOG, FEATURED, make_query
from ui.data import currency, h, time_ago
from ui.logos import logo_html, prefetch_logos
from ui.polish import refresh_data

# (Yahoo symbol, display name, region). An index Yahoo does not return is simply left out.
INDICES = [
    ("^GSPC", "S&P 500", "US"),
    ("^IXIC", "NASDAQ", "US"),
    ("^DJI", "Dow Jones", "US"),
    ("^NSEI", "NIFTY 50", "India"),
    ("^BSESN", "SENSEX", "India"),
]

# simple groups made for this app (each ticker appears once). Edit freely.
SECTORS = {
    "US tech & internet": ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX", "AMD", "INTC",
                           "AVGO", "ORCL", "CRM", "ADBE", "PLTR", "TSM", "ASML", "SAP"],
    "India IT": ["INFY.NS", "TCS.NS", "WIPRO.NS"],
    "Banks & finance": ["JPM", "V", "MA", "BRK-B", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
                        "AXISBANK.NS", "KOTAKBANK.NS", "BAJFINANCE.NS"],
    "Energy": ["XOM", "SHEL", "RELIANCE.NS"],
    "Autos": ["TSLA", "TM"],
    "Consumer & media": ["WMT", "KO", "DIS", "NKE", "ITC.NS", "HINDUNILVR.NS", "SONY", "BABA"],
    "Healthcare": ["PFE", "JNJ", "NVO"],
    "Industrials, materials & telecom": ["BA", "LT.NS", "TATASTEEL.NS", "BHARTIARTL.NS"],
}
_SECTOR_OF = {t: name for name, ts in SECTORS.items() for t in ts}

# the stocks scanned for pulse, movers and the heatmap: your featured cards plus the catalog
_NAMES = {}
for _i, _n, _tag, _t in FEATURED:
    _NAMES[_t] = _n
for _items in CATALOG.values():
    for _n, _t, _tag in _items:
        _NAMES.setdefault(_t, _n)
UNIVERSE = tuple(_NAMES)

HEAT_FULL = 4.0          # a daily move of +/- this many percent gets the strongest tile colour

_CSS = """
.ov-head{display:flex;align-items:center;gap:.6rem;margin:.2rem 0 .3rem}
.ov-title{font-family:var(--font-display);font-weight:800;font-size:1.25rem;color:#fff}
.ov-t{display:flex;align-items:center;gap:.5rem;margin:1.3rem 0 .6rem;font-family:var(--font-display);font-weight:700;font-size:1rem;color:var(--text)}
.ov-t::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border-strong),transparent)}
.ov-pulse{padding:1rem 1.2rem;border-radius:16px;border:1px solid var(--border-strong);border-top:2px solid var(--pc);background:linear-gradient(135deg,color-mix(in srgb,var(--pc) 8%,rgba(14,20,34,.82)),rgba(14,20,34,.78) 60%);box-shadow:0 18px 40px -30px var(--pc);animation:fadeUp .45s cubic-bezier(.2,.8,.2,1) both}
.ov-pl{font-size:.66rem;letter-spacing:.16em;font-weight:600;color:var(--muted)}
.ov-pm{font-family:var(--font-display);font-weight:800;font-size:1.5rem;line-height:1.2;color:var(--pc);margin:.2rem 0 .1rem}
.ov-ps{font-size:.84rem;color:var(--text);font-variant-numeric:tabular-nums}
.ov-bb{display:flex;height:8px;border-radius:8px;overflow:hidden;background:rgba(255,255,255,.08);margin:.7rem 0 .5rem}
.ov-bb i{display:block;height:100%}
.ov-bb i.up{background:linear-gradient(90deg,rgba(16,185,129,.55),#10B981)}
.ov-bb i.fl{background:rgba(255,255,255,.22)}
.ov-bb i.dn{background:linear-gradient(270deg,rgba(244,63,94,.55),#F43F5E)}
.ov-pg{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.55rem;margin-top:.8rem}
.ov-px2{padding:.5rem .7rem;border-radius:10px;border:1px solid var(--border);background:rgba(255,255,255,.03)}
.ov-pk{font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.ov-pv{font-weight:600;font-size:.86rem;color:var(--text);margin-top:.1rem;line-height:1.35}
.ov-idx{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.7rem}
.ov-card{padding:.85rem 1rem;border-radius:14px;border:1px solid var(--border);background:rgba(12,17,29,.72);transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease;animation:fadeUp .45s cubic-bezier(.2,.8,.2,1) both}
.ov-card:hover{transform:translateY(-2px);border-color:rgba(34,211,238,.4);box-shadow:0 12px 28px -18px rgba(34,211,238,.5)}
.ov-ct{display:flex;align-items:center;justify-content:space-between;gap:.5rem}
.ov-n{font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.ov-chip{padding:.05rem .5rem;border-radius:999px;border:1px solid var(--border);font-size:.62rem;color:var(--muted)}
.ov-lv{font-family:var(--font-display);font-weight:700;font-size:1.4rem;color:#fff;margin:.15rem 0;font-variant-numeric:tabular-nums}
.ov-pc{font-size:.86rem;font-weight:600;font-variant-numeric:tabular-nums}
.ov-sp{display:block;width:100%;height:40px;margin:.45rem 0 .3rem}
.ov-rets{font-size:.72rem;color:var(--muted);font-variant-numeric:tabular-nums}
.ov-pos{position:relative;height:4px;border-radius:4px;background:rgba(255,255,255,.1);margin:.55rem 0 .25rem}
.ov-pos i{position:absolute;top:50%;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.ov-m{font-size:.7rem;color:var(--muted)}
.ov-up{color:var(--success)}.ov-down{color:var(--danger)}.ov-na{color:var(--muted);font-weight:400}
.ov-row{display:flex;align-items:center;gap:.6rem;min-height:46px;padding:.35rem .55rem;border-radius:12px;border:1px solid var(--border);background:rgba(255,255,255,.03);transition:border-color .2s ease}
.ov-row:hover{border-color:rgba(34,211,238,.4)}
.ov-mid{flex:1;min-width:0;line-height:1.25}
.ov-rn{font-size:.82rem;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-rs{font-size:.66rem;color:var(--muted);letter-spacing:.03em}
.ov-pxr{flex:0 0 auto;text-align:right;line-height:1.25}
.ov-p{font-size:.8rem;font-weight:600;color:var(--text);font-variant-numeric:tabular-nums}
.ov-c{font-size:.72rem;font-weight:600;font-variant-numeric:tabular-nums}
.ov-c.up{color:var(--success)}.ov-c.down{color:var(--danger)}
.ov-h{font-size:.78rem;font-weight:600;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:.2rem 0 .1rem}
.ov-sh{display:flex;align-items:center;gap:.7rem;margin:1rem 0 .45rem}
.ov-sn{font-size:.86rem;font-weight:700;color:var(--text);flex:0 0 auto}
.ov-track{position:relative;flex:1;max-width:180px;height:7px;border-radius:7px;background:rgba(255,255,255,.07)}
.ov-track::after{content:"";position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:rgba(255,255,255,.25)}
.ov-track i{position:absolute;top:0;bottom:0;border-radius:7px}
.ov-track i.up{background:linear-gradient(90deg,rgba(16,185,129,.5),#10B981)}
.ov-track i.down{background:linear-gradient(270deg,rgba(244,63,94,.5),#F43F5E)}
.ov-sv{font-size:.82rem;font-weight:700;font-variant-numeric:tabular-nums}
.ov-sc{font-size:.7rem;color:var(--muted)}
.ov-heat{display:flex;flex-wrap:wrap;gap:.35rem}
.ov-tile{min-width:76px;padding:.4rem .55rem;border-radius:9px;border:1px solid rgba(255,255,255,.08);text-align:center;font-size:.7rem;line-height:1.3;color:#fff;cursor:default;transition:transform .15s ease,border-color .15s ease}
.ov-tile:hover{transform:translateY(-2px);border-color:rgba(255,255,255,.4)}
.ov-tile b{display:block;font-size:.8rem;font-variant-numeric:tabular-nums}
.ov-leg{display:flex;align-items:center;gap:.5rem;margin-top:.9rem;font-size:.7rem;color:var(--muted)}
.ov-leg i{display:block;width:150px;height:8px;border-radius:8px;background:linear-gradient(90deg,rgba(244,63,94,.64),rgba(255,255,255,.08),rgba(16,185,129,.64))}
.ov-note{color:var(--muted);font-size:.74rem;line-height:1.6;margin:.8rem 0 0}
@media (max-width:640px){.ov-track{display:none}.ov-tile{min-width:64px}}
[class*="st-key-ov_g_"] button,[class*="st-key-ov_l_"] button{min-height:34px;padding:.15rem .5rem}
[class*="st-key-ov_g_"] button p,[class*="st-key-ov_l_"] button p{font-size:.78rem}
"""


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())


def _md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def _cols(spec):
    """Vertically centred columns where supported, plain columns otherwise."""
    try:
        return st.columns(spec, vertical_alignment="center")
    except TypeError:
        return st.columns(spec)


def _region(ticker: str) -> str:
    return "India" if ticker.upper().endswith((".NS", ".BO")) else "US"


def _short(ticker: str) -> str:
    return ticker.replace(".NS", "").replace(".BO", "")


# ---------------------------------------------------------------------
# data
# ---------------------------------------------------------------------
def _closes(data, sym):
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


def _ret(closes, k):
    """Percent change from k sessions ago to the latest close (None if there is not enough history)."""
    if len(closes) >= k and closes[-k]:
        return (closes[-1] / closes[-k] - 1) * 100
    return None


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_indices() -> dict:
    syms = [s for s, _n, _r in INDICES]
    data = yf.download(syms, period="1y", interval="1d", group_by="ticker",
                       progress=False, threads=True, auto_adjust=True, timeout=10)
    out = {}
    for sym in syms:
        s = _closes(data, sym)
        if s is None:
            continue
        closes = [float(x) for x in s]
        prev = closes[-2]
        if not prev:
            continue
        lo, hi = min(closes), max(closes)
        out[sym] = {
            "level": closes[-1],
            "pct": (closes[-1] - prev) / prev * 100,
            "ret_1m": _ret(closes, 22),
            "ret_3m": _ret(closes, 64),
            "ret_1y": (closes[-1] / closes[0] - 1) * 100 if len(closes) >= 240 and closes[0] else None,
            "series": closes[-64:],                              # about three months for the sparkline
            "pos": (closes[-1] - lo) / (hi - lo) if hi > lo else None,
            "date": s.index[-1].strftime("%d %b %Y"),
        }
    if not out:
        raise RuntimeError("Yahoo returned no index data")        # failures are never cached
    return {"items": out, "fetched_at": time.time()}


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_movers(tickers: tuple) -> dict:
    data = yf.download(list(tickers), period="7d", interval="1d", group_by="ticker",
                       progress=False, threads=True, auto_adjust=True, timeout=12)
    out = {}
    for t in tickers:
        s = _closes(data, t)
        if s is None:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        if prev:
            out[t] = {"price": last, "pct": (last - prev) / prev * 100, "date": s.index[-1].strftime("%d %b")}
    if not out:
        raise RuntimeError("Yahoo returned no stock data")
    return {"items": out, "fetched_at": time.time()}


_LAST_GOOD = {}          # last successful result per data set (shared by all sessions)


def _load(kind: str, fn, *args):
    """(data | None, stale). After a failure, wait 60 s before retrying and fall back to the
    last good copy (flagged stale) so a brief Yahoo outage never blanks the panel."""
    retry = st.session_state.setdefault("_retry_overview", {})
    if time.time() < retry.get(kind, 0):
        d = _LAST_GOOD.get(kind)
        return d, d is not None
    try:
        d = fn(*args)
        _LAST_GOOD[kind] = d
        return d, False
    except Exception:
        retry[kind] = time.time() + 60
        d = _LAST_GOOD.get(kind)
        return d, d is not None


def _refresh_overview() -> None:
    """Button callback: re-download the overview data now."""
    _fetch_indices.clear()
    _fetch_movers.clear()
    st.session_state.pop("_retry_overview", None)


# ---------------------------------------------------------------------
# html pieces
# ---------------------------------------------------------------------
def _fmt_ret(v) -> str:
    if v is None:
        return '<span class="ov-na">n/a</span>'
    return f'<span class="{"ov-up" if v >= 0 else "ov-down"}">{v:+.1f}%</span>'


def _spark(series, up: bool) -> str:
    if len(series) < 2:
        return ""
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1.0
    w, ht = 140, 40
    pts = [(i * w / (len(series) - 1), ht - 3 - (v - lo) / span * (ht - 6)) for i, v in enumerate(series)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{ht} {line} {w},{ht}"
    color, fill = ("#10B981", "rgba(16,185,129,.16)") if up else ("#F43F5E", "rgba(244,63,94,.16)")
    return (f'<svg class="ov-sp" viewBox="0 0 {w} {ht}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polygon points="{area}" fill="{fill}"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.8" '
            'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def _index_cards(items: dict, region: str):
    """(html, names of indices that returned no data)."""
    cards, missing = [], []
    for i, (sym, name, reg) in enumerate(INDICES):
        if region != "All" and reg != region:
            continue
        it = items.get(sym)
        if not it:
            missing.append(name)
            continue
        up = it["pct"] >= 0
        pos_html = ""
        if it["pos"] is not None:
            pos_html = (f'<div class="ov-pos"><i style="left:{it["pos"] * 100:.0f}%"></i></div>'
                        f'<div class="ov-m">{it["pos"] * 100:.0f}% of its 1-year range (closing prices)</div>')
        cards.append(
            f'<div class="ov-card" style="animation-delay:{i * 0.05:.2f}s">'
            f'<div class="ov-ct"><span class="ov-n">{h(name)}</span><span class="ov-chip">{h(reg)}</span></div>'
            f'<div class="ov-lv">{it["level"]:,.2f}</div>'
            f'<div class="ov-pc {"ov-up" if up else "ov-down"}">{"▲" if up else "▼"} {abs(it["pct"]):.2f}% vs previous close</div>'
            f'{_spark(it["series"], it["series"][-1] >= it["series"][0])}'
            f'<div class="ov-rets">1M {_fmt_ret(it["ret_1m"])} · 3M {_fmt_ret(it["ret_3m"])} · 1Y {_fmt_ret(it["ret_1y"])}</div>'
            f'{pos_html}'
            f'<div class="ov-m">Last close {h(it["date"])}</div></div>'
        )
    return '<div class="ov-idx">' + "".join(cards) + "</div>", missing


def _sector_rows(items: dict) -> list:
    groups = {}
    for t, q in items.items():
        groups.setdefault(_SECTOR_OF.get(t, "Other"), []).append((t, q))
    rows = []
    for name, lst in groups.items():
        lst.sort(key=lambda tq: tq[1]["pct"], reverse=True)
        rows.append({"name": name, "avg": sum(q["pct"] for _t, q in lst) / len(lst), "stocks": lst,
                     "total": len(SECTORS.get(name, [])) or len(lst)})
    rows.sort(key=lambda r: r["avg"], reverse=True)
    return rows


def _pulse_html(items: dict, rows: list) -> str:
    pcts = [q["pct"] for q in items.values()]
    n = len(pcts)
    up = sum(1 for p in pcts if p > 0)
    dn = sum(1 for p in pcts if p < 0)
    fl = n - up - dn
    avg = sum(pcts) / n
    if n < 5:
        mood, color = "Too few stocks for a read", "#8B93A7"
    elif up / n >= 0.65:
        mood, color = "Broadly positive", "#10B981"
    elif up / n <= 0.35:
        mood, color = "Broadly negative", "#F43F5E"
    else:
        mood, color = "Mixed", "#F59E0B"

    best = max(items.items(), key=lambda kv: kv[1]["pct"])
    worst = min(items.items(), key=lambda kv: kv[1]["pct"])
    multi = [r for r in rows if len(r["stocks"]) >= 2 and r["name"] != "Other"]

    def box(label, value):
        return f'<div class="ov-px2"><div class="ov-pk">{h(label)}</div><div class="ov-pv">{value}</div></div>'

    stats = [
        box("Best stock", f'{h(_NAMES.get(best[0], best[0]))} <span class="ov-up">{best[1]["pct"]:+.2f}%</span>'),
        box("Worst stock", f'{h(_NAMES.get(worst[0], worst[0]))} <span class="ov-down">{worst[1]["pct"]:+.2f}%</span>'),
    ]
    if multi:
        s_hi, s_lo = multi[0], multi[-1]
        stats.append(box("Strongest sector", f'{h(s_hi["name"])} <span class="ov-{"up" if s_hi["avg"] >= 0 else "down"}">{s_hi["avg"]:+.2f}%</span>'))
        stats.append(box("Weakest sector", f'{h(s_lo["name"])} <span class="ov-{"up" if s_lo["avg"] >= 0 else "down"}">{s_lo["avg"]:+.2f}%</span>'))

    return (
        f'<div class="ov-pulse" style="--pc:{color};">'
        '<div class="ov-pl">MARKET PULSE · CATALOG BREADTH</div>'
        f'<div class="ov-pm">{h(mood)}</div>'
        f'<div class="ov-ps">{up} up · {dn} down{f" · {fl} flat" if fl else ""} · average {avg:+.2f}% across {n} stocks</div>'
        f'<div class="ov-bb"><i class="up" style="width:{up / n * 100:.1f}%"></i>'
        f'<i class="fl" style="width:{fl / n * 100:.1f}%"></i><i class="dn" style="width:{dn / n * 100:.1f}%"></i></div>'
        f'<div class="ov-pg">{"".join(stats)}</div></div>'
    )


def _tile_style(p: float) -> str:
    if abs(p) < 0.05:
        return "background:rgba(255,255,255,.07)"
    k = min(abs(p) / HEAT_FULL, 1.0)
    rgb = "16,185,129" if p > 0 else "244,63,94"
    return f"background:rgba({rgb},{0.14 + 0.5 * k:.2f})"


def _heatmap_html(rows: list) -> str:
    max_abs = max((abs(r["avg"]) for r in rows), default=0) or 1.0
    out = []
    for r in rows:
        half = abs(r["avg"]) / max_abs * 50                      # percent of the track, from the centre
        up = r["avg"] >= 0
        pos = f"left:50%;width:{half:.1f}%" if up else f"left:{50 - half:.1f}%;width:{half:.1f}%"
        n = len(r["stocks"])
        avg_html = (f'<span class="ov-sv {"ov-up" if up else "ov-down"}">{r["avg"]:+.2f}%</span>'
                    if n >= 2 else "")
        tiles = "".join(
            f'<div class="ov-tile" style="{_tile_style(q["pct"])}" '
            f'title="{h(_NAMES.get(t, t))} · {h(t)} · {h(q["date"])}">{h(_short(t))}<b>{q["pct"]:+.1f}%</b></div>'
            for t, q in r["stocks"]
        )
        out.append(f'<div class="ov-sh"><span class="ov-sn">{h(r["name"])}</span>'
                   f'<div class="ov-track"><i class="{"up" if up else "down"}" style="{pos}"></i></div>'
                   f'{avg_html}<span class="ov-sc">{n} of {r["total"]} stocks</span></div>'
                   f'<div class="ov-heat">{tiles}</div>')
    legend = (f'<div class="ov-leg"><span>−{HEAT_FULL:g}%</span><i></i><span>+{HEAT_FULL:g}%</span>'
              '<span>· hover a tile for the company name and date</span></div>')
    return "".join(out) + legend


def _mover_row(t: str, q: dict) -> str:
    name = _NAMES.get(t, t)
    up = q["pct"] >= 0
    return (f'<div class="ov-row">{logo_html(t, name, 30)}'
            f'<div class="ov-mid"><div class="ov-rn">{h(name)}</div>'
            f'<div class="ov-rs">{h(t)} · {h(q["date"])}</div></div>'
            f'<div class="ov-pxr"><div class="ov-p">{h(currency(t))}{q["price"]:,.2f}</div>'
            f'<div class="ov-c {"up" if up else "down"}">{"▲" if up else "▼"} {abs(q["pct"]):.2f}%</div></div></div>')


# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------
def _pick(query: str) -> None:
    """Button callback: start the analysis workflow for the chosen stock."""
    st.session_state.pending_query = query
    st.session_state.compare_items = None


def render_overview() -> None:
    _md(f"<style>{_css()}</style>")
    with st.spinner("Loading market overview…"):
        idx, idx_stale = _load("indices", _fetch_indices)
        mov, mov_stale = _load("movers", _fetch_movers, UNIVERSE)

    top = _cols([5, 1.4])
    top[0].markdown('<div class="ov-head"><span class="ov-title">🌐 Market overview</span></div>', unsafe_allow_html=True)
    top[1].button("↻ Refresh", key="ov_refresh", use_container_width=True, on_click=_refresh_overview,
                  help="Re-download the overview data now")

    if idx is None and mov is None:
        st.warning("The market overview is unavailable right now (Yahoo Finance may be rate-limiting). "
                   "Try again in a minute.")
        st.button("↻ Retry", key="ov_retry", on_click=refresh_data)
        return

    c1, c2 = st.columns([2, 1.4])
    region = c1.radio("Region", ["All", "US", "India"], horizontal=True, key="ov_region",
                      label_visibility="collapsed")
    count = c2.radio("Movers shown", ["Top 5", "Top 10"], horizontal=True, key="ov_n",
                     label_visibility="collapsed")
    n_show = 5 if count == "Top 5" else 10

    all_items = (mov or {}).get("items", {})
    items = {t: q for t, q in all_items.items() if region == "All" or _region(t) == region}
    rows = _sector_rows(items) if items else []

    # ---- market pulse ----
    if items:
        _md(_pulse_html(items, rows))
    else:
        st.caption("Stock data is unavailable right now, so the market pulse can't be shown.")

    # ---- indices ----
    _md('<div class="ov-t">Major indices</div>')
    if idx:
        html_cards, missing = _index_cards(idx["items"], region)
        if html_cards.count("ov-card") or not missing:
            _md(html_cards)
        if missing:
            st.caption("No data returned right now for: " + ", ".join(missing) + ".")
    else:
        st.caption("Index data is unavailable right now.")

    # ---- movers ----
    _md('<div class="ov-t">Top movers · built-in catalog</div>')
    if items:
        ranked = sorted(items.items(), key=lambda kv: kv[1]["pct"], reverse=True)
        gainers = [(t, q) for t, q in ranked if q["pct"] > 0][:n_show]
        losers = [(t, q) for t, q in reversed(ranked) if q["pct"] < 0][:n_show]
        prefetch_logos([t for t, _q in gainers + losers])

        head = st.columns([5, 1.2, 5, 1.2])
        head[0].markdown('<div class="ov-h">▲ Gainers</div>', unsafe_allow_html=True)
        head[2].markdown('<div class="ov-h">▼ Losers</div>', unsafe_allow_html=True)
        for i in range(max(len(gainers), len(losers))):
            row = _cols([5, 1.2, 5, 1.2])
            if i < len(gainers):
                t, q = gainers[i]
                row[0].markdown(_mover_row(t, q), unsafe_allow_html=True)
                row[1].button("Analyse", key=f"ov_g_{i}", use_container_width=True,
                              on_click=_pick, args=(make_query(_NAMES.get(t, t), t),))
            if i < len(losers):
                t, q = losers[i]
                row[2].markdown(_mover_row(t, q), unsafe_allow_html=True)
                row[3].button("Analyse", key=f"ov_l_{i}", use_container_width=True,
                              on_click=_pick, args=(make_query(_NAMES.get(t, t), t),))
        if not gainers and not losers:
            st.caption("No stock in this selection moved in the latest session.")
    else:
        st.caption("Stock data is unavailable right now.")

    # ---- sector heatmap ----
    _md('<div class="ov-t">Sector heatmap · built-in catalog</div>')
    if rows:
        _md(_heatmap_html(rows))
    else:
        st.caption("Not enough data to build the heatmap right now.")

    # ---- freshness and honesty notes ----
    stamps = [d["fetched_at"] for d in (idx, mov) if d]
    notes = []
    if stamps:
        notes.append(f"Data fetched {h(time_ago(min(stamps)))} · cached for up to 5 minutes · "
                     "Source: Yahoo Finance daily data.")
    if idx_stale or mov_stale:
        notes.append("⚠️ Yahoo did not answer the latest refresh, so some of this is saved data (see the age above).")
    notes.append(f"The pulse, movers and heatmap cover only the {len(UNIVERSE)} stocks in this app's built-in catalog, "
                 "not the whole market. Sector groups are a simple classification made for this app, and a sector's "
                 "figure is the equal-weighted average daily change of its stocks that returned data. Every change "
                 "compares a stock's latest session with the one before it, so US and Indian stocks can be from "
                 "different days (the date is on each row and tile). The mood label is a plain count of stocks up "
                 "versus down, not a prediction. Educational only, not financial advice.")
    _md('<div class="ov-note">' + "<br>".join(notes) + "</div>")


def render_overview_entry() -> None:
    """A toggle. Nothing is downloaded while it is off (an expander would still run its body)."""
    if st.toggle("🌐 Market overview", key="ov_open",
                 help="Pulse, indices, top movers and a sector heatmap from Yahoo Finance data"):
        render_overview()