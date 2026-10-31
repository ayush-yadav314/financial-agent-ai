"""ui/overview.py
Market overview panel: market pulse, major indices (with trend charts), top movers and a sector heatmap.

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
- Index trend charts plot daily closing prices for the chosen range (1M, 3M or 1Y).

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

# (Yahoo symbol, display name, region, one-line description). An index Yahoo does not return is left out.
# The descriptions are static text written from general knowledge, not fetched.
INDICES = [
    ("^GSPC", "S&P 500", "US", "500 large US companies"),
    ("^IXIC", "NASDAQ", "US", "Nasdaq-listed stocks, tech-heavy"),
    ("^DJI", "Dow Jones", "US", "30 large US companies"),
    ("^NSEI", "NIFTY 50", "India", "50 large companies on the NSE"),
    ("^BSESN", "SENSEX", "India", "30 large companies on the BSE"),
]

# trend-chart ranges: number of trading-day closes (None = everything fetched, about one year)
TRENDS = {"1M": 22, "3M": 64, "1Y": None}

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
.ov-head{display:flex;align-items:center;gap:.6rem;margin:.2rem 0 .1rem}
.ov-title{font-family:var(--font-display);font-weight:800;font-size:1.3rem;letter-spacing:-.02em;color:#fff}
.ov-ctl{font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;font-weight:600;color:var(--muted);margin:.2rem 0 .1rem}
.ov-fresh{display:inline-block;padding:.2rem .7rem;border-radius:999px;border:1px solid var(--border);background:rgba(255,255,255,.03);font-size:.7rem;color:var(--muted)}
.ov-t{display:flex;align-items:baseline;gap:.6rem;margin:1.5rem 0 .75rem;font-family:var(--font-display);font-weight:700;font-size:1.02rem;color:var(--text)}
.ov-ts{font-family:var(--font-body);font-weight:500;font-size:.74rem;color:var(--muted)}
.ov-t::after{content:"";flex:1;align-self:center;height:1px;background:linear-gradient(90deg,var(--border-strong),transparent)}
.ov-pulse{padding:1.1rem 1.25rem;border-radius:16px;border:1px solid var(--border-strong);border-top:2px solid var(--pc);background:linear-gradient(135deg,color-mix(in srgb,var(--pc) 8%,rgba(14,20,34,.82)),rgba(14,20,34,.78) 60%);box-shadow:0 18px 40px -30px var(--pc);animation:fadeUp .45s cubic-bezier(.2,.8,.2,1) both}
.ov-pl{font-size:.66rem;letter-spacing:.16em;font-weight:600;color:var(--muted)}
.ov-pm{font-family:var(--font-display);font-weight:800;font-size:1.55rem;line-height:1.2;color:var(--pc);margin:.2rem 0 .1rem}
.ov-ps{font-size:.84rem;color:var(--text);font-variant-numeric:tabular-nums}
.ov-bb{display:flex;height:8px;border-radius:8px;overflow:hidden;background:rgba(255,255,255,.08);margin:.75rem 0 .5rem}
.ov-bb i{display:block;height:100%}
.ov-bb i.up{background:linear-gradient(90deg,rgba(16,185,129,.55),#10B981)}
.ov-bb i.fl{background:rgba(255,255,255,.22)}
.ov-bb i.dn{background:linear-gradient(270deg,rgba(244,63,94,.55),#F43F5E)}
.ov-pg{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.6rem;margin-top:.85rem}
.ov-px2{padding:.55rem .75rem;border-radius:10px;border:1px solid var(--border);background:rgba(255,255,255,.03)}
.ov-pk{font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.ov-pv{font-weight:600;font-size:.86rem;color:var(--text);margin-top:.1rem;line-height:1.35}
.ov-idx{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:.9rem}
.ov-card{position:relative;overflow:hidden;padding:1.05rem 1.15rem 1rem;border-radius:16px;border:1px solid var(--border);border-top:2px solid var(--k);background:linear-gradient(160deg,color-mix(in srgb,var(--k) 7%,rgba(14,20,34,.84)),rgba(12,17,29,.8) 58%);transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease;animation:fadeUp .5s cubic-bezier(.2,.8,.2,1) both}
.ov-card::after{content:"";position:absolute;top:0;bottom:0;left:-60%;width:40%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.05),transparent);transition:left .7s ease;pointer-events:none}
.ov-card:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--k) 45%,transparent);box-shadow:0 18px 36px -22px var(--k)}
.ov-card:hover::after{left:120%}
.ov-card:hover .ov-sp polyline{stroke-width:2.6}
.ov-ct{display:flex;align-items:flex-start;justify-content:space-between;gap:.5rem}
.ov-n{font-family:var(--font-display);font-weight:700;font-size:.95rem;letter-spacing:.02em;color:var(--text)}
.ov-d{font-size:.72rem;color:var(--muted);margin-top:.1rem;line-height:1.35}
.ov-chip{flex:0 0 auto;padding:.1rem .55rem;border-radius:999px;border:1px solid var(--border);font-size:.62rem;color:var(--muted)}
.ov-lv{font-family:var(--font-display);font-weight:800;font-size:1.75rem;letter-spacing:-.02em;line-height:1.15;color:#fff;margin:.5rem 0 .3rem;font-variant-numeric:tabular-nums}
.ov-chrow{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.ov-pill{display:inline-block;padding:.15rem .6rem;border-radius:999px;font-size:.8rem;font-weight:700;font-variant-numeric:tabular-nums}
.ov-pill.up{color:var(--success);background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.35)}
.ov-pill.down{color:var(--danger);background:rgba(244,63,94,.12);border:1px solid rgba(244,63,94,.35)}
.ov-vs{font-size:.68rem;color:var(--muted)}
.ov-spw{position:relative;margin:.75rem 0 .25rem}
.ov-sp{display:block;width:100%;height:56px}
.ov-dot{position:absolute;right:2px;width:9px;height:9px;margin-top:-4.5px;border-radius:50%;background:var(--dc);box-shadow:0 0 10px var(--dc)}
.ov-dot::after{content:"";position:absolute;inset:-4px;border-radius:50%;border:1px solid var(--dc);opacity:0;animation:ovPing 2.4s ease-out infinite}
@keyframes ovPing{0%{transform:scale(.6);opacity:.7}100%{transform:scale(1.6);opacity:0}}
.ov-axis{display:flex;justify-content:space-between;font-size:.66rem;color:var(--muted);font-variant-numeric:tabular-nums}
.ov-lh{font-size:.68rem;color:var(--muted);margin-top:.15rem;font-variant-numeric:tabular-nums}
.ov-rets{display:flex;gap:.35rem;margin:.7rem 0 .15rem;flex-wrap:wrap}
.ov-rc{display:inline-flex;align-items:baseline;gap:.35rem;padding:.12rem .55rem;border-radius:8px;border:1px solid var(--border);background:rgba(255,255,255,.03);font-size:.72rem;font-weight:700;font-variant-numeric:tabular-nums}
.ov-rc em{font-style:normal;font-weight:500;font-size:.62rem;letter-spacing:.06em;color:var(--muted)}
.ov-rc.sel{border-color:color-mix(in srgb,var(--accent) 55%,transparent);background:rgba(34,211,238,.08)}
.ov-pos{position:relative;height:4px;border-radius:4px;background:rgba(255,255,255,.1);margin:.7rem 0 .25rem}
.ov-pos i{position:absolute;top:50%;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.ov-rl{display:flex;justify-content:space-between;font-size:.64rem;color:var(--muted);font-variant-numeric:tabular-nums}
.ov-m{font-size:.68rem;color:var(--muted);margin-top:.5rem}
.ov-up{color:var(--success)}.ov-down{color:var(--danger)}.ov-na{color:var(--muted);font-weight:400}
.ov-row{display:flex;align-items:center;gap:.6rem;min-height:46px;padding:.35rem .55rem;border-radius:12px;border:1px solid var(--border);background:rgba(255,255,255,.03);transition:border-color .2s ease,transform .2s ease}
.ov-row:hover{border-color:rgba(34,211,238,.4);transform:translateX(2px)}
.ov-mid{flex:1;min-width:0;line-height:1.25}
.ov-rn{font-size:.82rem;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-rs{font-size:.66rem;color:var(--muted);letter-spacing:.03em}
.ov-pxr{flex:0 0 auto;text-align:right;line-height:1.25}
.ov-p{font-size:.8rem;font-weight:600;color:var(--text);font-variant-numeric:tabular-nums}
.ov-c{font-size:.72rem;font-weight:600;font-variant-numeric:tabular-nums}
.ov-c.up{color:var(--success)}.ov-c.down{color:var(--danger)}
.ov-h{font-size:.78rem;font-weight:600;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:.2rem 0 .1rem}
.ov-sh{display:flex;align-items:center;gap:.7rem;margin:1.1rem 0 .5rem}
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
.ov-gl{margin-top:1.3rem;padding:.7rem 1rem;border-radius:12px;border:1px solid var(--border);background:rgba(255,255,255,.025)}
.ov-gl summary{cursor:pointer;color:var(--accent);font-size:.84rem;font-weight:600}
.ov-gl ul{margin:.6rem 0 .2rem;padding-left:1.1rem}
.ov-gl li{margin:.4rem 0;font-size:.8rem;line-height:1.6;color:var(--muted)}
.ov-gl li b{color:var(--text);font-weight:600}
.ov-note{color:var(--muted);font-size:.74rem;line-height:1.6;margin:.9rem 0 0}
@media (max-width:640px){.ov-track{display:none}.ov-tile{min-width:64px}.ov-lv{font-size:1.5rem}}
[class*="st-key-ov_g_"] button,[class*="st-key-ov_l_"] button{min-height:34px;padding:.15rem .5rem}
[class*="st-key-ov_g_"] button p,[class*="st-key-ov_l_"] button p{font-size:.78rem}
"""


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())


def _md(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def _title(text: str, sub: str = "") -> None:
    sub_html = f'<span class="ov-ts">{h(sub)}</span>' if sub else ""
    _md(f'<div class="ov-t">{h(text)}{sub_html}</div>')


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


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_indices() -> dict:
    syms = [s for s, _n, _r, _d in INDICES]
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
        out[sym] = {
            "level": closes[-1],
            "prev": prev,
            "pct": (closes[-1] - prev) / prev * 100,
            "closes": closes,                                              # about one year of daily closes
            "labels": [d.strftime("%d %b") for d in s.index],              # "22 Sep", parallel to closes
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


def _ret(closes, k):
    """Percent change from k sessions ago to the latest close (None if there is not enough history)."""
    if len(closes) >= k and closes[-k]:
        return (closes[-1] / closes[-k] - 1) * 100
    return None


def _window(closes, labels, key):
    """(closes, labels, enough_history) for one trend range. 1Y needs about 240 sessions to count as a full year."""
    k = TRENDS[key]
    if k is None:
        return closes, labels, len(closes) >= 240
    if len(closes) < k:
        return closes, labels, False
    return closes[-k:], labels[-k:], True


# ---------------------------------------------------------------------
# html pieces
# ---------------------------------------------------------------------
def _fmt_ret(v) -> str:
    if v is None:
        return '<span class="ov-na">n/a</span>'
    return f'<span class="{"ov-up" if v >= 0 else "ov-down"}">{v:+.1f}%</span>'


def _spark(series, up: bool):
    """(svg, y of the latest point as a percent of the chart height)."""
    if len(series) < 2:
        return "", 50.0
    w, ht, pad = 160, 56, 5
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1.0

    def y(v):
        return pad + (hi - v) / span * (ht - 2 * pad)

    pts = [(i * w / (len(series) - 1), y(v)) for i, v in enumerate(series)]
    line = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in pts)
    area = f"0,{ht} {line} {w},{ht}"
    base = y(series[0])                                          # where the period started
    color, fill = ("#10B981", "rgba(16,185,129,.16)") if up else ("#F43F5E", "rgba(244,63,94,.16)")
    svg = (f'<svg class="ov-sp" viewBox="0 0 {w} {ht}" preserveAspectRatio="none" aria-hidden="true">'
           f'<line x1="0" y1="{base:.1f}" x2="{w}" y2="{base:.1f}" stroke="rgba(255,255,255,.22)" '
           'stroke-width="1" stroke-dasharray="3 3"/>'
           f'<polygon points="{area}" fill="{fill}"/>'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" '
           'stroke-linejoin="round" stroke-linecap="round"/></svg>')
    return svg, pts[-1][1] / ht * 100


def _index_cards(items: dict, region: str, trend: str = "3M"):
    """(html, names of indices that returned no data)."""
    cards, missing = [], []
    for i, (sym, name, reg, desc) in enumerate(INDICES):
        if region != "All" and reg != region:
            continue
        it = items.get(sym)
        if not it or not it.get("closes"):
            missing.append(name)
            continue
        closes = it["closes"]
        labels = it.get("labels") or [""] * len(closes)
        series, slabels, enough = _window(closes, labels, trend)
        up = it["pct"] >= 0
        color = "#10B981" if up else "#F43F5E"
        diff = it["level"] - it["prev"]

        svg, dot_y = _spark(series, series[-1] >= series[0])
        dot_color = "#10B981" if series[-1] >= series[0] else "#F43F5E"
        lo_w, hi_w = min(series), max(series)
        note = "" if enough else f' · only {len(series)} sessions of data available'
        chart = (f'<div class="ov-spw">{svg}<i class="ov-dot" style="top:{dot_y:.1f}%;--dc:{dot_color}"></i></div>'
                 f'<div class="ov-axis"><span>{h(slabels[0])}</span><span>{h(slabels[-1])}</span></div>'
                 f'<div class="ov-lh">Low {lo_w:,.2f} · High {hi_w:,.2f}{h(note)}</div>')

        chips = []
        for key in TRENDS:
            s_k, _l, ok_k = _window(closes, labels, key)
            val = (s_k[-1] / s_k[0] - 1) * 100 if ok_k and s_k[0] else None
            chips.append(f'<span class="ov-rc{" sel" if key == trend else ""}"><em>{key}</em>{_fmt_ret(val)}</span>')

        lo_all, hi_all = min(closes), max(closes)
        pos_html = ""
        if hi_all > lo_all:
            pos = (it["level"] - lo_all) / (hi_all - lo_all) * 100
            span_label = "1-year" if len(closes) >= 240 else f"{len(closes)}-session"
            pos_html = (f'<div class="ov-pos"><i style="left:{pos:.0f}%"></i></div>'
                        f'<div class="ov-rl"><span>{lo_all:,.0f}</span><span>{pos:.0f}% of its {span_label} range</span>'
                        f'<span>{hi_all:,.0f}</span></div>')

        cards.append(
            f'<div class="ov-card" style="--k:{color};animation-delay:{i * 0.06:.2f}s">'
            f'<div class="ov-ct"><div><div class="ov-n">{h(name)}</div><div class="ov-d">{h(desc)}</div></div>'
            f'<span class="ov-chip">{h(reg)}</span></div>'
            f'<div class="ov-lv">{it["level"]:,.2f}</div>'
            f'<div class="ov-chrow"><span class="ov-pill {"up" if up else "down"}">{"▲" if up else "▼"} '
            f'{abs(diff):,.2f} ({abs(it["pct"]):.2f}%)</span><span class="ov-vs">vs previous close</span></div>'
            f'{chart}'
            f'<div class="ov-rets">{"".join(chips)}</div>'
            f'{pos_html}'
            f'<div class="ov-m">Last close {h(it["date"])} · closing prices, Yahoo Finance</div></div>'
        )
    return '<div class="ov-idx">' + "".join(cards) + "</div>", missing


def _index_summary(items: dict, region: str) -> str:
    """A live one-liner such as '4 of 5 rose at their last close' (empty if nothing to count)."""
    shown = [items[s] for s, _n, reg, _d in INDICES
             if (region == "All" or reg == region) and s in items and items[s].get("closes")]
    if not shown:
        return ""
    up = sum(1 for it in shown if it["pct"] > 0)
    return f"{up} of {len(shown)} rose at their last close"


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
    share = up / n
    if n < 5:
        mood, color = "Too few stocks for a read", "#8B93A7"
    elif share >= 0.65:
        mood, color = "Broadly positive", "#10B981"
    elif share <= 0.35:
        mood, color = "Broadly negative", "#F43F5E"
    elif share >= 0.55 and avg > 0:
        mood, color = "Leaning positive", "#34D399"
    elif share <= 0.45 and avg < 0:
        mood, color = "Leaning negative", "#FB7185"
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
        f'<div class="ov-ps">{up} up · {dn} down{f" · {fl} flat" if fl else ""} · {share * 100:.0f}% rose · average {avg:+.2f}% across {n} stocks</div>'
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


_GLOSSARY = (
    '<details class="ov-gl"><summary>How to read this panel</summary><ul>'
    '<li><b>▲ / ▼ and the percentage:</b> how much the latest close differs from the close before it. '
    'It is not a live price, and the close can be hours or days old.</li>'
    '<li><b>Trend chart:</b> daily closing prices over the chosen range. The dashed line marks where the period '
    'started, and the glowing dot is the latest close.</li>'
    '<li><b>1M / 3M / 1Y:</b> change from the close about one month, three months or one year ago to the latest '
    'close. A one-year figure needs about a year of data.</li>'
    '<li><b>Range bar:</b> where the latest close sits between the lowest and highest close of the past year '
    '(0% is the lowest, 100% is the highest).</li>'
    '<li><b>Market pulse:</b> how many catalog stocks rose or fell in their latest session. "Broadly" means about '
    'two thirds or more moved the same way, "Leaning" means a modest majority with the average change pointing '
    'the same way, and "Mixed" means close to even. It is a count of one day, not a forecast.</li>'
    '<li><b>Heatmap:</b> each tile is a stock. Green means up, red means down, and a deeper colour means a '
    'bigger move.</li>'
    '</ul></details>'
)


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

    stamps = [d["fetched_at"] for d in (idx, mov) if d]

    top = _cols([4.2, 2.4, 1.4])
    top[0].markdown('<div class="ov-head"><span class="ov-title">🌐 Market overview</span></div>',
                    unsafe_allow_html=True)
    if stamps:
        top[1].markdown(f'<span class="ov-fresh">Data fetched {h(time_ago(min(stamps)))}</span>',
                        unsafe_allow_html=True)
    top[2].button("↻ Refresh", key="ov_refresh", use_container_width=True, on_click=_refresh_overview,
                  help="Re-download the overview data now")

    if idx is None and mov is None:
        st.warning("The market overview is unavailable right now (Yahoo Finance may be rate-limiting). "
                   "Try again in a minute.")
        st.button("↻ Retry", key="ov_retry", on_click=refresh_data)
        return

    c1, c2, c3 = st.columns([2, 1.7, 1.5])
    c1.markdown('<div class="ov-ctl">Region</div>', unsafe_allow_html=True)
    region = c1.radio("Region", ["All", "US", "India"], horizontal=True, key="ov_region",
                      label_visibility="collapsed")
    c2.markdown('<div class="ov-ctl">Index chart range</div>', unsafe_allow_html=True)
    trend = c2.radio("Index chart range", list(TRENDS), index=1, horizontal=True, key="ov_trend",
                     label_visibility="collapsed")
    c3.markdown('<div class="ov-ctl">Movers shown</div>', unsafe_allow_html=True)
    count = c3.radio("Movers shown", ["Top 5", "Top 10"], horizontal=True, key="ov_n",
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
    _title("Major indices", _index_summary(idx["items"], region) if idx else "How the big markets did at their last close")
    if idx:
        html_cards, missing = _index_cards(idx["items"], region, trend)
        if html_cards.count("ov-card") or not missing:
            _md(html_cards)
        if missing:
            st.caption("No data returned right now for: " + ", ".join(missing) + ".")
    else:
        st.caption("Index data is unavailable right now.")

    # ---- movers ----
    _title("Top movers", "Biggest gainers and losers in the built-in catalog")
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
    _title("Sector heatmap", "Every stock in the catalog, grouped by sector")
    if rows:
        _md(_heatmap_html(rows))
    else:
        st.caption("Not enough data to build the heatmap right now.")

    # ---- how to read + freshness and honesty notes ----
    _md(_GLOSSARY)
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