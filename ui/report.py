"""ui/report.py
Report components. Everything shown here comes from real data (Yahoo Finance via
ui/data.py and ui/prices.py, the numbers your agent captured, and the AI's own text).
Nothing is invented: missing values show "N/A" and empty sections say so.

Consistency rule: the summary card, signals and fundamentals all read the SAME snapshot
the AI analyst saw (the `metrics` dict), so the page and the AI text agree. P/E is always
labelled "trailing" (last 12 months, from the snapshot) or "forward" (expected, from the profile).

Public API (called from app.py)
    inject_report_css()
    render_section(icon, title)
    compute_signals(profile, metrics, ticker) -> dict(pos, neg, risk, notes)
    bottom_line_from(report_text) -> str
    render_summary(ticker, profile, metrics, sentiment, signals, scorecard, bottom_line, ts, notices=None)
    render_key_metrics(profile, metrics, ticker, section=True)
    render_signals(signals, section=True)
    render_overview(profile, section=True)
    render_news(ticker, news, section=True)
    render_freshness(profile, ts, stats=None)
"""
import re
from urllib.parse import urlparse

import streamlit as st

from ui.data import (_num as _n, currency, fmt_cap, fmt_num, fmt_pct, fmt_ratio, h,
                     news_page_url, stamp, time_ago)
from ui.logos import logo_html

_COLORS = {"BULLISH": "#10B981", "NEUTRAL": "#F59E0B", "BEARISH": "#F43F5E"}
_LABELS = {"BULLISH": "🟢 Bullish", "NEUTRAL": "🟡 Neutral", "BEARISH": "🔴 Bearish"}
_ANGLES = {"BULLISH": 62, "NEUTRAL": 0, "BEARISH": -62}
_REC = {"strong_buy": "Strong buy", "buy": "Buy", "hold": "Hold",
        "underperform": "Underperform", "sell": "Sell", "strong_sell": "Strong sell"}

_CSS = """
.sm{position:relative;overflow:hidden;padding:1.1rem 1.2rem;border-radius:var(--radius);border:1px solid var(--border-strong);border-top:2px solid var(--c);background:linear-gradient(135deg,color-mix(in srgb,var(--c) 8%,rgba(14,20,34,.80)),rgba(14,20,34,.76) 58%);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);box-shadow:0 18px 44px -30px var(--c);margin:.1rem 0 .8rem;animation:fadeUp .5s cubic-bezier(.2,.8,.2,1) both}
.sm::after{content:"";position:absolute;top:0;bottom:0;left:-50%;width:40%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.07),transparent);animation:sheen 1.6s .25s ease-out both;pointer-events:none}
.sm-top{display:flex;align-items:center;gap:1.1rem;flex-wrap:wrap}
.sm-id{display:flex;align-items:center;gap:.85rem;min-width:0;flex:1 1 260px}
.sm-name{font-family:var(--font-display);font-weight:700;font-size:1.3rem;line-height:1.25;color:#fff}
.sm-sub{font-size:.8rem;color:var(--muted);margin-top:.1rem}
.sm-px{text-align:right;flex:0 0 auto}
.sm-price{font-family:var(--font-display);font-weight:700;font-size:1.7rem;line-height:1.1;color:#fff;font-variant-numeric:tabular-nums}
.sm-chg{font-size:.84rem;font-weight:600;font-variant-numeric:tabular-nums;margin-top:.1rem}
.sm-chg.up{color:var(--success)}.sm-chg.down{color:var(--danger)}.sm-chg.na{color:var(--muted);font-weight:400}
.sm-pill{display:inline-block;margin-top:.5rem;padding:.22rem .8rem;border-radius:999px;font-weight:600;font-size:.8rem;color:var(--c);border:1px solid var(--c);background:color-mix(in srgb,var(--c) 12%,transparent);box-shadow:0 0 18px -8px var(--c)}
.sm-gw{flex:0 0 auto;text-align:center}
.sm-gauge{position:relative;width:120px;height:62px;overflow:hidden;margin:0 auto}
.sm-gauge-arc{position:absolute;left:0;top:0;width:120px;height:120px;border-radius:50%;background:conic-gradient(from -90deg,#F43F5E 0deg,#F59E0B 90deg,#10B981 180deg,transparent 180deg 360deg);-webkit-mask:radial-gradient(circle closest-side,transparent 70%,#000 71%);mask:radial-gradient(circle closest-side,transparent 70%,#000 71%)}
.sm-gauge-needle{position:absolute;left:50%;bottom:2px;width:3px;height:48px;margin-left:-1.5px;border-radius:3px;background:linear-gradient(to top,transparent,var(--c));transform-origin:50% 100%;transform:rotate(var(--a));box-shadow:0 0 8px var(--c);animation:needleSwing 1.5s cubic-bezier(.34,1.56,.64,1) both}
.sm-gauge-hub{position:absolute;left:50%;bottom:-5px;width:11px;height:11px;margin-left:-5.5px;border-radius:50%;background:var(--text)}
.sm-gl{margin-top:.15rem;font-size:.6rem;letter-spacing:.14em;color:var(--muted)}
.sm-line{margin:.85rem 0 0;color:var(--text);font-size:.95rem;line-height:1.6}
.sm-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.6rem;margin-top:.9rem}
.sm-st{padding:.6rem .8rem;border-radius:12px;border:1px solid var(--border);background:rgba(255,255,255,.035);transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease;animation:fadeUp .5s cubic-bezier(.2,.8,.2,1) both}
.sm-st:nth-child(1){animation-delay:.08s}.sm-st:nth-child(2){animation-delay:.14s}.sm-st:nth-child(3){animation-delay:.2s}.sm-st:nth-child(4){animation-delay:.26s}.sm-st:nth-child(5){animation-delay:.32s}
.sm-st:hover,.rm:hover,.rs:hover{transform:translateY(-2px);border-color:rgba(34,211,238,.4);box-shadow:0 12px 28px -18px rgba(34,211,238,.55)}
.sm-l{font-size:.66rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.sm-v{font-weight:600;color:var(--text);font-size:1rem;margin:.12rem 0;font-variant-numeric:tabular-nums}
.sm-h{font-size:.72rem;color:var(--muted);line-height:1.4}
.sm-bar{height:4px;border-radius:4px;background:rgba(255,255,255,.1);margin:.4rem 0 .3rem;position:relative}
.sm-bar i{position:absolute;top:50%;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.sm-foot{margin-top:.8rem;font-size:.73rem;color:var(--muted);line-height:1.6}
.sm-warn{margin-top:.7rem;padding:.5rem .8rem;border-radius:10px;border:1px solid rgba(245,158,11,.4);background:rgba(245,158,11,.08);font-size:.8rem;line-height:1.5;color:var(--text)}
.rp-sec{display:flex;align-items:center;gap:.55rem;margin:1.5rem 0 .7rem;font-family:var(--font-display);font-weight:700;font-size:1.05rem;color:var(--text)}
.rp-sec::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border-strong),transparent)}
.rp-note{color:var(--muted);font-size:.76rem;line-height:1.6;margin:.5rem 0 0}
.rm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.6rem}
.rm{padding:.75rem .9rem;border-radius:12px;border:1px solid var(--border);background:rgba(255,255,255,.035);transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}
.rm-l{font-size:.66rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.rm-v{font-family:var(--font-display);font-weight:700;font-size:1.2rem;color:var(--text);margin:.15rem 0;font-variant-numeric:tabular-nums}
.rm-h{font-size:.72rem;line-height:1.45;color:var(--muted)}
.rs-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem}
@media (max-width:900px){.rs-grid{grid-template-columns:1fr}}
.rs{padding:.85rem 1rem;border-radius:12px;border:1px solid var(--border);border-top:2px solid var(--k);background:rgba(255,255,255,.03);transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}
.rs.pos{--k:#10B981}.rs.neg{--k:#F43F5E}.rs.risk{--k:#F59E0B}
.rs-t{font-weight:600;color:var(--k)}
.rs ul{margin:.45rem 0 0;padding-left:1.1rem}
.rs li{margin:.5rem 0;line-height:1.55;font-size:.86rem;color:var(--muted)}
.rs li b{color:var(--text);font-weight:600}
.rs-none{color:var(--muted);font-size:.84rem;margin-top:.45rem}
.rs-warn{margin-top:.7rem;padding:.6rem .85rem;border-radius:10px;border:1px solid rgba(245,158,11,.4);background:rgba(245,158,11,.08);font-size:.82rem;line-height:1.55;color:var(--text)}
.ro-text{color:var(--text);line-height:1.75;margin:.1rem 0 .6rem}
.ro-more summary{cursor:pointer;color:var(--accent);font-size:.84rem;margin-bottom:.5rem}
.ro-more p{color:var(--muted);line-height:1.75;font-size:.9rem}
.ro-facts{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:.6rem}
.ro-fact{padding:.2rem .7rem;border-radius:999px;border:1px solid var(--border);background:rgba(255,255,255,.03);font-size:.76rem;color:var(--muted);transition:border-color .18s ease}
.ro-fact b{color:var(--text);font-weight:600}
.stApp a.ro-fact{text-decoration:none}
.stApp a.ro-fact:hover{border-color:var(--accent);color:var(--text)}
.stApp a.rn-item{display:block;padding:.7rem .95rem;margin-bottom:.45rem;border-radius:12px;border:1px solid var(--border);background:rgba(255,255,255,.03);text-decoration:none;color:inherit;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease}
.stApp a.rn-item:hover{transform:translateX(3px);border-color:rgba(34,211,238,.45);box-shadow:0 10px 24px -18px rgba(34,211,238,.5)}
.rn-t{display:block;color:var(--text);font-weight:500;line-height:1.5}
.rn-m{display:block;margin-top:.2rem;font-size:.76rem;color:var(--muted)}
.rn-chip{margin-left:.4rem;padding:.05rem .5rem;border-radius:999px;border:1px solid rgba(34,211,238,.4);color:var(--accent);font-size:.66rem}
.stApp a.rn-more{color:var(--accent);font-size:.8rem;text-decoration:none}
.rp-foot{font-size:.76rem;color:var(--muted);line-height:1.8;margin:.2rem 0}
"""


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())


def inject_report_css() -> None:
    """Inject the report stylesheet once per run (call right after inject_theme())."""
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)


def _md(html_str: str) -> None:
    st.markdown(html_str, unsafe_allow_html=True)


def render_section(icon: str, title: str) -> None:
    _md(f'<div class="rp-sec"><span>{h(icon)}</span><span>{h(title)}</span></div>')


def _rec_label(rec: str) -> str:
    rec = (rec or "").lower()
    return _REC.get(rec, rec.replace("_", " ").title()) if rec and rec != "none" else "N/A"


def _exchange_fallback(ticker: str) -> str:
    t = ticker.upper()
    return "NSE" if t.endswith(".NS") else "BSE" if t.endswith(".BO") else "US"


# ---------------------------------------------------------------------
# rule-based signals (every row quotes the number it is based on)
# ---------------------------------------------------------------------
def compute_signals(profile: dict, metrics: dict, ticker: str) -> dict:
    p, m = profile or {}, metrics or {}
    cur = currency(ticker)
    pos, neg, risk, notes = [], [], [], []

    price, prev = _n(m.get("price")), _n(m.get("prev_close"))
    low, high = _n(m.get("low_52")), _n(m.get("high_52"))
    pe = _n(m.get("pe"))
    margin, growth, roe = _n(p.get("profit_margin")), _n(p.get("revenue_growth")), _n(p.get("roe"))
    beta, pb = _n(p.get("beta")), _n(p.get("price_to_book"))
    target, n_an = _n(p.get("target_mean")), _n(p.get("analysts"))
    rec, cap = (p.get("recommendation") or "").lower(), _n(p.get("market_cap"))

    # ---- price behaviour ----
    if price and low is not None and high and high > low:
        position = (price - low) / (high - low)
        where = f"{position * 100:.0f}%"
        if position >= 0.8:
            pos.append(("Near its 52-week high", f"price sits at {where} of its yearly range, which points to strong recent momentum."))
        elif position <= 0.2:
            neg.append(("Near its 52-week low", f"price sits at {where} of its yearly range, which points to weak recent momentum."))
    if price and prev:
        chg = (price - prev) / prev
        if chg >= 0.03:
            pos.append((f"Up {chg * 100:.1f}% vs previous close", "a strong move in a single session."))
        elif chg <= -0.03:
            neg.append((f"Down {abs(chg) * 100:.1f}% vs previous close", "a sharp drop in a single session."))

    # ---- business quality ----
    if margin is not None:
        if margin < 0:
            neg.append((f"Loss-making (margin {fmt_pct(margin)})", "the company currently spends more than it earns."))
        elif margin < 0.05:
            neg.append((f"Thin profit margin ({fmt_pct(margin)})", "little of each unit of revenue is kept as profit."))
        elif margin >= 0.20:
            pos.append((f"High profit margin ({fmt_pct(margin)})", "the company keeps a large share of revenue as profit."))
    if growth is not None:
        if growth > 0.6:
            notes.append(f"Reported revenue growth of {fmt_pct(growth)} is unusually high. Yahoo's figure may reflect "
                         "one quarter or a one-off effect, so check the company's filings before relying on it.")
        elif growth >= 0.10:
            pos.append((f"Revenue growing {fmt_pct(growth)} year over year", "sales are expanding at a healthy pace."))
        elif growth < 0:
            neg.append((f"Revenue shrinking ({fmt_pct(growth)})", "sales fell compared with a year earlier."))
    if roe is not None:
        if roe >= 0.15:
            pos.append((f"Strong return on equity ({fmt_pct(roe)})", "the company earns a good profit on shareholders' money."))
        elif roe < 0.08:
            neg.append((f"Low return on equity ({fmt_pct(roe)})", "the company earns little profit on shareholders' money."))

    # ---- analysts (Yahoo's aggregate) ----
    if rec and n_an and n_an >= 5:
        label = _rec_label(rec)
        if rec in ("buy", "strong_buy"):
            pos.append((f"Analysts lean positive ({label})", f"Yahoo lists the view of {int(n_an)} analysts."))
        elif rec in ("sell", "underperform", "strong_sell"):
            neg.append((f"Analysts lean negative ({label})", f"Yahoo lists the view of {int(n_an)} analysts."))
    if price and target:
        up = (target - price) / price
        if up >= 0.10:
            pos.append((f"Average analyst target is {up * 100:.0f}% above the price", f"target {cur}{target:,.2f} vs price {cur}{price:,.2f}."))
        elif up <= -0.05:
            neg.append((f"Price is above the average analyst target ({abs(up) * 100:.0f}%)", f"target {cur}{target:,.2f} vs price {cur}{price:,.2f}."))

    # ---- risks ----
    if beta is not None and beta >= 1.3:
        risk.append((f"Higher volatility than the market (beta {beta:.2f})", "the price tends to swing more than the overall market."))
    if pe is not None and pe >= 40:
        risk.append((f"Expensive on earnings (trailing P/E {pe:.1f})", "investors are paying a lot for each unit of profit, so expectations are high."))
    if pb is not None and pb >= 10:
        risk.append((f"Very high price-to-book ({pb:.1f})", "the price is far above the value of the company's net assets."))
    if cap is not None and cap > 0 and cap < (5e10 if cur == "₹" else 2e9):
        risk.append(("Smaller company", "smaller companies can be more volatile and harder to trade."))
    if n_an is not None and n_an < 5:
        risk.append((f"Few analysts cover it ({int(n_an)})", "less professional scrutiny means less information to cross-check."))

    return {"pos": pos, "neg": neg, "risk": risk, "notes": notes}


def bottom_line_from(report_text: str) -> str:
    """The AI's own one-line takeaway (the prompt asks for '**Bottom line: ...**')."""
    m = re.search(r"\*\*\s*(Bottom line[^*\n]{3,260}?)\s*\*\*", report_text or "", re.IGNORECASE)
    if not m:
        return ""
    line = re.sub(r"^bottom line:?\s*", "", m.group(1), flags=re.IGNORECASE).strip()
    return (line[:1].upper() + line[1:]) if line else ""


# ---------------------------------------------------------------------
# compact summary card (the top of every report)
# ---------------------------------------------------------------------
def _stat(label: str, value_html: str, hint_html: str = "") -> str:
    return (f'<div class="sm-st"><div class="sm-l">{h(label)}</div>'
            f'<div class="sm-v">{value_html}</div><div class="sm-h">{hint_html}</div></div>')


def render_summary(ticker, profile, metrics, sentiment, signals, scorecard, bottom_line, ts, notices=None) -> None:
    t = (ticker or "").upper()
    p, m = profile or {}, metrics or {}
    name = p.get("name") or t
    cur = currency(t)
    color = _COLORS.get(sentiment, "#22D3EE")

    sub_bits = [t, p.get("exchange") or _exchange_fallback(t)]
    if p.get("sector"):
        sub_bits.append(p["sector"])
    sub = " · ".join(h(b) for b in sub_bits)

    # ---- price + change (the snapshot the AI analyst saw) ----
    price, prev = _n(m.get("price")), _n(m.get("prev_close"))
    if price is not None:
        px = f"{h(cur)}{price:,.2f}"
        if prev:
            diff = price - prev
            pct = diff / prev * 100
            up = diff >= 0
            chg = (f'<div class="sm-chg {"up" if up else "down"}">{"▲" if up else "▼"} '
                   f'{abs(diff):,.2f} ({abs(pct):.2f}%) vs previous close</div>')
        else:
            chg = '<div class="sm-chg na">Previous close not available</div>'
    else:
        px = "N/A"
        chg = '<div class="sm-chg na">Live quote unavailable</div>'

    pill = (f'<div class="sm-pill" style="--c:{color};">{_LABELS[sentiment]}</div>' if sentiment in _LABELS
            else '<div class="sm-pill" style="--c:#8B93A7;">⚪ No AI verdict</div>')

    # compact verdict gauge (only when there is a verdict)
    gauge = ""
    if sentiment in _ANGLES:
        gauge = (f'<div class="sm-gw"><div class="sm-gauge" style="--c:{color};--a:{_ANGLES[sentiment]}deg;">'
                 '<div class="sm-gauge-arc"></div><div class="sm-gauge-needle"></div><div class="sm-gauge-hub"></div></div>'
                 '<div class="sm-gl">AI VERDICT</div></div>')

    line = bottom_line or "Open the AI analyst report below for the full analysis."

    # ---- five key stats ----
    stats = [_stat("Market cap", h(fmt_cap(p.get("market_cap"), t)), "Total value of all shares")]
    stats.append(_stat("P/E (trailing)", h(fmt_ratio(m.get("pe"))), "Price ÷ last 12 months' earnings"))

    low, high = _n(m.get("low_52")), _n(m.get("high_52"))
    if low is not None and high and high > low and price is not None:
        pos = max(0.0, min(1.0, (price - low) / (high - low))) * 100
        stats.append(_stat("52-week range", f"{h(cur)}{low:,.0f} – {h(cur)}{high:,.0f}",
                           f'<div class="sm-bar"><i style="left:{pos:.0f}%"></i></div>{pos:.0f}% of range'))
    else:
        stats.append(_stat("52-week range", "N/A", "Not available"))

    rec, n_an = _rec_label(p.get("recommendation")), _n(p.get("analysts"))
    stats.append(_stat("Analyst view", h(rec),
                       f"{int(n_an)} analysts (Yahoo)" if n_an else "Number of analysts not provided"))

    if scorecard and scorecard.get("pct") is not None:
        stats.append(_stat("Scorecard", f'{scorecard["points"]}/{scorecard["max"]}', h(scorecard["tier"])))
    else:
        stats.append(_stat("Scorecard", "N/A", "Not enough data"))

    # ---- footer + notices ----
    foot = []
    if ts:
        foot.append(f"Snapshot of this analysis: {h(stamp(ts))} ({h(time_ago(ts))})")
    trade = stamp(p.get("price_time"), p.get("tz") or "")
    if trade:
        foot.append(f"Last trade: {h(trade)}")
    foot_html = f'<div class="sm-foot">{" · ".join(foot)}</div>' if foot else ""
    warn_html = "".join(f'<div class="sm-warn">⚠️ {h(n)}</div>' for n in (notices or []))

    _md("".join([
        f'<div class="sm" style="--c:{color};">',
        '<div class="sm-top">',
        '<div class="sm-id">',
        logo_html(t, name, size=52, website=p.get("website") or ""),
        f'<div style="min-width:0;"><div class="sm-name">{h(name)}</div><div class="sm-sub">{sub}</div></div>',
        '</div>',
        f'<div class="sm-px"><div class="sm-price">{px}</div>{chg}{pill}</div>',
        gauge,
        '</div>',
        f'<div class="sm-line">{h(line)}</div>',
        f'<div class="sm-stats">{"".join(stats)}</div>',
        foot_html,
        warn_html,
        '</div>',
    ]))


# ---------------------------------------------------------------------
# fundamentals grid
# ---------------------------------------------------------------------
def render_key_metrics(profile: dict, metrics: dict, ticker: str, section: bool = True) -> None:
    if section:
        render_section("🧮", "Fundamentals & analyst view")
    p, m = profile or {}, metrics or {}
    if not p:
        st.caption("⚠️ Company fundamentals from Yahoo Finance are unavailable right now.")
        return
    cur = currency(ticker)
    price = _n(m.get("price"))
    target = _n(p.get("target_mean"))
    t_hint = f"{(target - price) / price * 100:+.1f}% vs price at analysis" if (price and target) \
        else "Average of analyst price targets"
    n_an = _n(p.get("analysts"))
    avg_vol = _n(p.get("avg_volume"))

    items = [
        ("Market cap", fmt_cap(p.get("market_cap"), ticker), "Total value of all the company's shares"),
        ("P/E (trailing)", fmt_ratio(m.get("pe")), "Price ÷ last 12 months' earnings"),
        ("Forward P/E", fmt_ratio(p.get("forward_pe")), "Price ÷ expected earnings. Lower often means cheaper"),
        ("Price / Book", fmt_ratio(p.get("price_to_book")), "Price compared with the company's net assets"),
        ("Beta", fmt_ratio(p.get("beta")), "Swings vs. the market. Above 1 means more volatile"),
        ("Profit margin", fmt_pct(p.get("profit_margin")), "Share of revenue kept as profit"),
        ("Revenue growth", fmt_pct(p.get("revenue_growth")), "Year over year, as reported by Yahoo"),
        ("Return on equity", fmt_pct(p.get("roe")), "Profit earned on shareholders' money"),
        ("Volume", fmt_num(p.get("volume")), f"Average: {fmt_num(avg_vol)}" if avg_vol else "Shares traded in the latest session"),
        ("Analyst target", f"{cur}{fmt_ratio(target)}" if target else "N/A", t_hint),
        ("Analyst view", _rec_label(p.get("recommendation")),
         f"{int(n_an)} analysts (Yahoo's aggregate)" if n_an else "Number of analysts not provided"),
    ]
    cards = "".join(
        f'<div class="rm"><div class="rm-l">{h(l)}</div><div class="rm-v">{h(v)}</div><div class="rm-h">{h(hint)}</div></div>'
        for l, v, hint in items
    )
    _md(f'<div class="rm-grid">{cards}</div>')


# ---------------------------------------------------------------------
# bullish / bearish / risks
# ---------------------------------------------------------------------
def render_signals(signals: dict, section: bool = True) -> None:
    if section:
        render_section("⚖️", "Signals & risks")
    s = signals or {"pos": [], "neg": [], "risk": [], "notes": []}

    def col(cls, title, rows):
        if rows:
            body = "<ul>" + "".join(f"<li><b>{h(a)}</b>: {h(b)}</li>" for a, b in rows) + "</ul>"
        else:
            body = '<div class="rs-none">Nothing flagged by the available data.</div>'
        return f'<div class="rs {cls}"><div class="rs-t">{title}</div>{body}</div>'

    _md('<div class="rs-grid">' + col("pos", "▲ Bullish factors", s["pos"])
        + col("neg", "▼ Bearish factors", s["neg"]) + col("risk", "⚠ Risks to watch", s["risk"]) + '</div>')
    if s.get("notes"):
        _md("".join(f'<div class="rs-warn">⚠️ {h(n)}</div>' for n in s["notes"]))
    _md('<div class="rp-note">These checks use fixed thresholds on Yahoo Finance data. They are not predictions or '
        'advice and ignore context such as industry norms (for example, banks are normally valued differently '
        'from software companies).</div>')


# ---------------------------------------------------------------------
# company overview
# ---------------------------------------------------------------------
def _site(url: str) -> str:
    if not url:
        return ""
    u = url if "://" in url else "https://" + url
    pr = urlparse(u)
    return u if pr.scheme in ("http", "https") and pr.netloc else ""


def render_overview(profile: dict, section: bool = True) -> None:
    if section:
        render_section("🏢", "About the company")
    p = profile or {}
    summary = p.get("summary")
    if not p or not summary:
        st.caption("Company description from Yahoo Finance is not available right now.")
        return

    short = summary if len(summary) <= 420 else summary[:420].rsplit(" ", 1)[0] + "…"
    more = ""
    if len(summary) > 420:
        more = f'<details class="ro-more"><summary>Read the full description</summary><p>{h(summary)}</p></details>'

    facts = []
    for label, key in (("Sector", "sector"), ("Industry", "industry"), ("Country", "country")):
        if p.get(key):
            facts.append(f'<span class="ro-fact">{label}: <b>{h(p[key])}</b></span>')
    emp = _n(p.get("employees"))
    if emp:
        facts.append(f'<span class="ro-fact">Employees: <b>{int(emp):,}</b></span>')
    site = _site(p.get("website") or "")
    if site:
        host = urlparse(site).netloc
        facts.append(f'<a class="ro-fact" href="{h(site)}" target="_blank" rel="noopener noreferrer">🌐 {h(host)}</a>')

    _md(f'<p class="ro-text">{h(short)}</p>{more}<div class="ro-facts">{"".join(facts)}</div>'
        '<div class="rp-note">Description and facts are from Yahoo Finance, not written by the AI.</div>')


# ---------------------------------------------------------------------
# news
# ---------------------------------------------------------------------
def render_news(ticker: str, news: list, section: bool = True) -> None:
    if section:
        render_section("📰", "Recent news")
    more = news_page_url(ticker)
    more_link = (f'<a class="rn-more" href="{h(more)}" target="_blank" rel="noopener noreferrer">'
                 'More on Yahoo Finance ↗</a>') if more else ""
    if not news:
        _md(f'<div class="rp-note">No recent headlines were returned for {h(ticker.upper())} by Yahoo Finance '
            f'right now. {more_link}</div>')
        return

    rows = []
    for n in news:
        meta = " · ".join(x for x in (h(n.get("publisher") or "Unknown source"), h(time_ago(n.get("published")))) if x)
        chip = '<span class="rn-chip">names company</span>' if n.get("direct") else ""
        # spans (not divs) inside the link, and a block-level wrapper around the list:
        # a string that starts with an inline <a> gets split by the HTML parser
        rows.append(f'<a class="rn-item" href="{h(n["url"])}" target="_blank" rel="noopener noreferrer">'
                    f'<span class="rn-t">{h(n["title"])}</span><span class="rn-m">{meta}{chip}</span></a>')
    _md('<div class="rn-list">' + "".join(rows) + "</div>")
    _md('<div class="rp-note">Headlines come from Yahoo Finance and are tagged to this stock by Yahoo, so some '
        f'mention it only in passing. Open the source to read the full story. {more_link}</div>')


# ---------------------------------------------------------------------
# freshness + sources
# ---------------------------------------------------------------------
def render_freshness(profile: dict, ts, stats: dict = None) -> None:
    p, s = profile or {}, stats or {}
    lines = []
    if ts:
        lines.append(f"<b>Analysis snapshot:</b> {h(stamp(ts))} ({h(time_ago(ts))}). The price, daily change, "
                     "trailing P/E and 52-week range in the summary come from this snapshot, the same data the AI read.")
    trade = stamp(p.get("price_time"), p.get("tz") or "")
    lines.append(f"<b>Last trade:</b> {h(trade)}." if trade else "<b>Last trade:</b> exchange timestamp not provided.")
    if p.get("fetched_at"):
        lines.append(f"<b>Fundamentals:</b> Yahoo Finance, fetched {h(time_ago(p['fetched_at']))} (cached up to 15 minutes).")
    if s.get("last_date"):
        lines.append(f"<b>Chart data:</b> daily closes through {h(s['last_date'])}, adjusted for splits and dividends.")
    lines.append("<b>Headlines:</b> Yahoo Finance (cached up to 10 minutes).")
    if ts:
        lines.append("<b>AI analysis:</b> Gemini, from the market data above and, when available, a Tavily news search "
                     "plus Yahoo headlines that name the company. AI can make mistakes.")
    lines.append("Educational research only. Not financial advice.")
    _md('<div class="rp-foot">' + "<br>".join(lines) + "</div>")