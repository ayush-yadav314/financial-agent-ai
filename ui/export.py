"""ui/export.py
Builds a standalone, print-friendly HTML report (open it in a browser, then Print -> Save as PDF).

Pure functions: no Streamlit and no network. Everything shown is data the app already has:
Yahoo Finance fields, the numbers the AI analyst saw, the rule-based scorecard and signals,
the AI's own text and the headlines shown in the report. Missing data is written as N/A.
All text is HTML-escaped, and only http(s) links are included.

Public API
    build_report_html(ticker, profile, metrics, sentiment, content, ts,
                      signals=None, card=None, news=None, stats=None, followups=None) -> str
    md_to_html(text) -> str
"""
import re

from ui.data import _num, currency, fmt_cap, fmt_pct, fmt_ratio, h, stamp
from ui.report import _rec_label, bottom_line_from

_VERDICT = {"BULLISH": ("Bullish", "#047857"), "NEUTRAL": ("Neutral", "#B45309"), "BEARISH": ("Bearish", "#BE123C")}

_CSS = """
:root{--ink:#0f172a;--muted:#475569;--line:#e2e8f0;--soft:#f8fafc;--accent:#0e7490}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font:15px/1.65 Inter,"Segoe UI",system-ui,-apple-system,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:28px 24px 48px}
.bar{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin-bottom:1rem;font-size:.8rem;color:var(--muted)}
.bar button{font:inherit;padding:.4rem .9rem;border:1px solid var(--line);border-radius:8px;background:var(--soft);cursor:pointer}
.bar button:hover{border-color:var(--accent);color:var(--accent)}
.head{border:1px solid var(--line);border-top:5px solid var(--c);border-radius:12px;padding:1.2rem 1.4rem;background:var(--soft)}
.eyebrow{font-size:.7rem;letter-spacing:.16em;font-weight:700;color:var(--muted)}
h1{margin:.2rem 0 .1rem;font-size:1.8rem;line-height:1.2;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:.9rem}
.verdict{display:inline-block;margin-top:.7rem;padding:.2rem .8rem;border:1.5px solid var(--c);border-radius:999px;color:var(--c);font-weight:700;font-size:.85rem}
.line{margin:.9rem 0 0;font-size:1rem}
h2{margin:1.8rem 0 .6rem;padding-bottom:.35rem;border-bottom:2px solid var(--line);font-size:1.15rem}
h3{margin:1.2rem 0 .4rem;font-size:1rem}
h4{margin:1rem 0 .3rem;font-size:.92rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:.6rem}
.st{border:1px solid var(--line);border-radius:10px;padding:.55rem .8rem;background:#fff;break-inside:avoid}
.st .l{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.st .v{font-weight:700;font-size:1.05rem}
.st .s{font-size:.74rem;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.pts{font-weight:700;white-space:nowrap}
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem}
.col{border:1px solid var(--line);border-top:3px solid var(--k);border-radius:10px;padding:.7rem .9rem;break-inside:avoid}
.col h4{margin:0 0 .3rem;color:var(--k)}
.col ul{margin:.2rem 0 0;padding-left:1.1rem;font-size:.86rem}
.col li{margin:.35rem 0}
.warn{margin-top:.8rem;padding:.6rem .9rem;border:1px solid #f59e0b;background:#fffbeb;border-radius:10px;font-size:.86rem}
.note{color:var(--muted);font-size:.8rem}
.ai p,.ai li{margin:.5rem 0}
blockquote{margin:.6rem 0;padding:.3rem .9rem;border-left:3px solid var(--accent);background:var(--soft)}
.news li{margin:.55rem 0}
.news .m{display:block;color:var(--muted);font-size:.78rem}
.qa{border:1px solid var(--line);border-radius:10px;padding:.7rem .9rem;margin:.6rem 0;break-inside:avoid}
.qa .q{font-weight:700}
a{color:var(--accent)}
.foot{margin-top:2rem;padding-top:.8rem;border-top:1px solid var(--line);color:var(--muted);font-size:.78rem;line-height:1.7}
@media (max-width:640px){.cols{grid-template-columns:1fr}}
@media print{.noprint{display:none}.wrap{padding:0;max-width:none}body{font-size:13px}a{color:inherit;text-decoration:none}h2{break-after:avoid}}
"""


# ---------------------------------------------------------------------
# markdown -> html (the small subset the AI report uses)
# ---------------------------------------------------------------------
def _inline(text: str) -> str:
    t = h(text)                                                       # escape first, then add our own tags
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<em>\1</em>", t)
    return t


def md_to_html(text: str) -> str:
    """Headings, bullet and numbered lists, bold, italics, quotes and rules. Everything is escaped."""
    out, para, lst = [], [], None

    def flush_para():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    def close_list():
        nonlocal lst
        if lst:
            out.append(f"</{lst}>")
            lst = None

    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            flush_para()
            close_list()
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", s)
        if m:
            flush_para()
            close_list()
            level = 2 if len(m.group(1)) <= 2 else min(len(m.group(1)), 4)
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            continue
        if re.fullmatch(r"[-*_]{3,}", s):
            flush_para()
            close_list()
            out.append("<hr>")
            continue
        b = re.match(r"^[-*•]\s+(.+)$", s)
        n = re.match(r"^\d+[.)]\s+(.+)$", s)
        if b or n:
            flush_para()
            kind = "ul" if b else "ol"
            if lst != kind:
                close_list()
                out.append(f"<{kind}>")
                lst = kind
            out.append("<li>" + _inline((b or n).group(1)) + "</li>")
            continue
        if s.startswith(">"):
            flush_para()
            close_list()
            out.append("<blockquote>" + _inline(s.lstrip("> ").strip()) + "</blockquote>")
            continue
        close_list()
        para.append(s)
    flush_para()
    close_list()
    return "\n".join(out)


# ---------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------
def _exchange(ticker: str, profile: dict) -> str:
    t = ticker.upper()
    return profile.get("exchange") or ("NSE" if t.endswith(".NS") else "BSE" if t.endswith(".BO") else "US")


def _stat(label: str, value: str, hint: str = "") -> str:
    hint_html = f'<div class="s">{h(hint)}</div>' if hint else ""
    return f'<div class="st"><div class="l">{h(label)}</div><div class="v">{h(value)}</div>{hint_html}</div>'


def _snapshot_html(ticker: str, profile: dict, metrics: dict) -> str:
    p, m = profile or {}, metrics or {}
    cur = currency(ticker)
    price, prev = _num(m.get("price")), _num(m.get("prev_close"))
    low, high = _num(m.get("low_52")), _num(m.get("high_52"))
    target, n_an = _num(p.get("target_mean")), _num(p.get("analysts"))

    if price is not None:
        hint = ""
        if prev:
            diff = price - prev
            hint = f"{'▲' if diff >= 0 else '▼'} {abs(diff):,.2f} ({abs(diff / prev * 100):.2f}%) vs previous close"
        stats = [_stat("Price at analysis", f"{cur}{price:,.2f}", hint)]
    else:
        stats = [_stat("Price at analysis", "N/A", "A live quote was not captured")]

    stats += [
        _stat("Market cap", fmt_cap(p.get("market_cap"), ticker)),
        _stat("P/E (trailing)", fmt_ratio(m.get("pe")), "Price ÷ last 12 months' earnings"),
        _stat("Forward P/E", fmt_ratio(p.get("forward_pe")), "Price ÷ expected earnings"),
        _stat("Price / Book", fmt_ratio(p.get("price_to_book"))),
        _stat("Beta", fmt_ratio(p.get("beta")), "Swings vs. the market"),
        _stat("Profit margin", fmt_pct(p.get("profit_margin"))),
        _stat("Revenue growth", fmt_pct(p.get("revenue_growth")), "Year over year, per Yahoo"),
        _stat("Return on equity", fmt_pct(p.get("roe"))),
    ]
    if low is not None and high is not None and high > low and price is not None:
        pos = max(0.0, min(1.0, (price - low) / (high - low))) * 100
        stats.append(_stat("52-week range", f"{cur}{low:,.0f} – {cur}{high:,.0f}", f"{pos:.0f}% of range"))
    else:
        stats.append(_stat("52-week range", "N/A"))
    stats.append(_stat("Analyst target", f"{cur}{target:,.2f}" if target else "N/A", "Average of analyst targets"))
    stats.append(_stat("Analyst view", _rec_label(p.get("recommendation")),
                       f"{int(n_an)} analysts (Yahoo)" if n_an else ""))
    return '<div class="grid">' + "".join(stats) + "</div>"


def _scorecard_html(card: dict) -> str:
    if not card or not card.get("items"):
        return ""
    big = (f'{card["points"]}/{card["max"]} · {h(card["tier"])}' if card.get("pct") is not None
           else "Not enough data for a score")
    rows = "".join(
        f'<tr><td><b>{h(i["name"])}</b><br><span class="note">{h(i["metric"])}</span></td>'
        f'<td>{h(i["value"])}</td><td class="pts">{"N/A" if i["points"] is None else str(i["points"]) + "/2"}</td>'
        f'<td class="note">{h(i["rule"])}</td></tr>'
        for i in card["items"]
    )
    return ('<h2>Research scorecard</h2>'
            f'<p><b>{big}</b> <span class="note">({card.get("covered", 0)} of {card.get("total", 7)} checks had data)</span></p>'
            '<table><tr><th>Check</th><th>Value</th><th>Points</th><th>Rule</th></tr>' + rows + '</table>'
            '<p class="note">Seven simple, generic checks on Yahoo Finance data. They ignore industry norms, are not '
            'predictions and are not advice. A missing value is N/A, not zero.</p>')


def _signals_html(signals: dict) -> str:
    if not signals:
        return ""

    def col(title, color, rows):
        if rows:
            body = "<ul>" + "".join(f"<li><b>{h(a)}</b>: {h(b)}</li>" for a, b in rows) + "</ul>"
        else:
            body = '<p class="note">Nothing flagged by the available data.</p>'
        return f'<div class="col" style="--k:{color}"><h4>{title}</h4>{body}</div>'

    notes = "".join(f'<div class="warn">⚠ {h(n)}</div>' for n in signals.get("notes", []))
    return ('<h2>Signals &amp; risks</h2><div class="cols">'
            + col("▲ Bullish factors", "#047857", signals.get("pos", []))
            + col("▼ Bearish factors", "#BE123C", signals.get("neg", []))
            + col("⚠ Risks to watch", "#B45309", signals.get("risk", [])) + "</div>" + notes
            + '<p class="note">Fixed thresholds on Yahoo Finance data. Not predictions or advice.</p>')


def _news_html(news: list) -> str:
    items = []
    for n in news or []:
        if not isinstance(n, dict) or not n.get("title") or not n.get("url"):
            continue
        when = stamp(n.get("published"))
        meta = " · ".join(x for x in (n.get("publisher") or "Unknown source", when) if x)
        items.append(f'<li><a href="{h(n["url"])}" target="_blank" rel="noopener noreferrer">{h(n["title"])}</a>'
                     f'<span class="m">{h(meta)}</span></li>')
    if not items:
        return '<h2>Recent news</h2><p class="note">No recent headlines were available from Yahoo Finance.</p>'
    return ('<h2>Recent news</h2><ul class="news">' + "".join(items) + "</ul>"
            '<p class="note">Headlines come from Yahoo Finance and are tagged to this stock by Yahoo, so some mention '
            'it only in passing.</p>')


def _followups_html(followups: list) -> str:
    items = [f for f in (followups or []) if isinstance(f, dict) and f.get("q") and f.get("a")]
    if not items:
        return ""
    blocks = "".join(f'<div class="qa"><div class="q">{h(f["q"])}</div>{md_to_html(f["a"])}</div>' for f in items)
    return ('<h2>Follow-up questions</h2>' + blocks +
            '<p class="note">AI answers based only on this report\'s saved data. They can be wrong.</p>')


# ---------------------------------------------------------------------
# the whole document
# ---------------------------------------------------------------------
def build_report_html(ticker, profile, metrics, sentiment, content, ts,
                      signals=None, card=None, news=None, stats=None, followups=None) -> str:
    t = (ticker or "").upper()
    p = profile or {}
    name = p.get("name") or t
    label, color = _VERDICT.get(sentiment, ("No AI verdict", "#475569"))
    sub = " · ".join(h(x) for x in (t, _exchange(t, p), p.get("sector")) if x)
    line = bottom_line_from(content)
    line_html = f'<p class="line"><b>Bottom line:</b> {h(line)}</p>' if line else ""

    generated = stamp(ts) if ts else "time not recorded"
    trade = stamp(p.get("price_time"), p.get("tz") or "")
    chart_through = (stats or {}).get("last_date")
    foot = [f"Generated {h(generated)}. The price, change, trailing P/E and 52-week range come from the snapshot "
            "the AI analyst read when it wrote the report."]
    if trade:
        foot.append(f"Last trade: {h(trade)}.")
    if chart_through:
        foot.append(f"Chart data ran through {h(chart_through)}.")
    foot.append("Market data and headlines: Yahoo Finance. AI analysis: Gemini, using the data above and, when "
                "available, a Tavily news search. AI can make mistakes.")
    foot.append("Educational research only. This is not financial advice.")

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{h(name)} ({h(t)}) · Research report</title><style>{_CSS}</style></head><body><div class="wrap">'
        '<div class="bar noprint"><span>Open the browser print dialog (Ctrl+P) and choose "Save as PDF" to make a PDF.</span>'
        '<button onclick="window.print()">Print / Save as PDF</button></div>'
        f'<div class="head" style="--c:{color}"><div class="eyebrow">AI RESEARCH REPORT</div>'
        f'<h1>{h(name)}</h1><div class="sub">{sub}</div>'
        f'<div class="verdict">{h(label)}</div>{line_html}</div>'
        '<h2>Market snapshot</h2>' + _snapshot_html(t, p, metrics)
        + '<h2>AI analyst report</h2><div class="ai">' + md_to_html(content) + '</div>'
        + _scorecard_html(card) + _signals_html(signals) + _followups_html(followups) + _news_html(news)
        + '<div class="foot">' + "<br>".join(foot) + '</div></div></body></html>'
    )