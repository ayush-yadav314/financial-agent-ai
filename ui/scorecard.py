"""ui/scorecard.py
Explainable, rule-based research scorecard.

Seven simple checks, each worth 0-2 points, each with a visible rule. Missing data is
"N/A" (never counted as zero). With fewer than 3 usable criteria no score is shown.
The thresholds are generic and ignore industry norms: this is a transparent snapshot,
not a prediction and not advice. Edit RULES / compute_scorecard to change the rules.

Public API
    compute_scorecard(profile, stats, ticker="") -> dict
    render_scorecard(sc)                  one stock, with a full breakdown (used in reports)
    render_score_matrix(cards)            several stocks side by side; cards = [(label, ticker, sc), ...]
"""
import streamlit as st

from ui.data import _num, h
from ui.report import _rec_label, render_section

# (criterion, metric, rule)
RULES = [
    ("Valuation", "Forward P/E", "≤ 20 → 2 pts · ≤ 35 → 1 pt · higher → 0"),
    ("Profitability", "Profit margin", "≥ 20% → 2 · ≥ 8% → 1 · lower → 0"),
    ("Growth", "Revenue growth (YoY)", "≥ 10% → 2 · ≥ 0% → 1 · shrinking → 0"),
    ("Efficiency", "Return on equity", "≥ 15% → 2 · ≥ 8% → 1 · lower → 0"),
    ("Momentum", "6-month price change", "≥ +10% → 2 · ≥ −5% → 1 · lower → 0"),
    ("Analyst view", "Yahoo consensus (5+ analysts)", "Buy → 2 · Hold → 1 · Sell → 0"),
    ("Volatility", "Beta (lower is calmer)", "≤ 1.0 → 2 · ≤ 1.5 → 1 · higher → 0"),
]
_WHY = [
    "Lower means you pay less for each unit of expected profit.",
    "How much of each unit of revenue the company keeps as profit.",
    "How fast sales are growing compared with a year ago.",
    "How much profit the company earns on shareholders' money.",
    "How the share price has moved over roughly the last six months.",
    "What the professional analysts tracked by Yahoo recommend on balance.",
    "How much the price swings compared with the overall market.",
]
_POS = {"buy", "strong_buy"}
_NEG = {"sell", "underperform", "strong_sell"}

_CSS = """
.sc{padding:1rem 1.1rem;border-radius:var(--radius);border:1px solid var(--border);border-top:2px solid var(--k);background:rgba(10,14,26,.66)}
.sc-top{display:flex;align-items:center;gap:1rem;flex-wrap:wrap}
.sc-big{font-family:var(--font-display);font-weight:700;font-size:2.2rem;line-height:1;color:var(--k)}
.sc-big span{font-size:1rem;color:var(--muted);font-weight:500}
.sc-tier{font-weight:600;color:var(--k)}
.sc-sub{font-size:.76rem;color:var(--muted)}
.sc-bar{height:6px;border-radius:6px;background:rgba(255,255,255,.08);margin:.8rem 0 .5rem;overflow:hidden}
.sc-bar div{height:100%;border-radius:6px;background:linear-gradient(90deg,var(--accent-2),var(--k))}
.sc-row{display:grid;grid-template-columns:1.25fr .8fr .55fr 2.4fr;gap:.7rem;align-items:center;padding:.55rem 0;border-top:1px solid var(--border)}
@media (max-width:800px){.sc-row{grid-template-columns:1fr 1fr}}
.sc-n{font-weight:600;color:var(--text);font-size:.86rem}
.sc-n span{display:block;font-weight:400;font-size:.68rem;color:var(--muted)}
.sc-v{font-size:.86rem;color:var(--text);font-variant-numeric:tabular-nums}
.sc-p{display:inline-block;min-width:2.6rem;text-align:center;padding:.1rem .5rem;border-radius:999px;font-size:.74rem;font-weight:600;border:1px solid var(--pc);color:var(--pc);background:color-mix(in srgb,var(--pc) 12%,transparent)}
.sc-p.p2{--pc:#10B981}.sc-p.p1{--pc:#F59E0B}.sc-p.p0{--pc:#F43F5E}.sc-p.na{--pc:#8B93A7}
.sc-w{font-size:.76rem;line-height:1.5;color:var(--muted)}
.sc-w i{display:block;font-style:normal;opacity:.8}
.sc-w b{color:#F59E0B;font-weight:600}
.sc-legend{padding-left:1.1rem}
.sc-legend li{font-size:.8rem;color:var(--muted);margin:.35rem 0;line-height:1.5}
.sc-legend b{color:var(--text)}
.scm{border:1px solid var(--border);border-radius:var(--radius);background:rgba(10,14,26,.66);overflow-x:auto}
.scm-r{display:grid;grid-template-columns:170px repeat(var(--n),minmax(130px,1fr));gap:.6rem;align-items:center;padding:.6rem .9rem;border-top:1px solid var(--border);min-width:520px}
.scm-r:first-child{border-top:none}
.scm-h{font-weight:600;color:var(--text);font-size:.86rem}
.scm-c{display:flex;flex-direction:column;gap:.25rem;align-items:flex-start}
.scm-v{font-size:.72rem;color:var(--muted)}
.scm-tot .sc-big{font-size:1.6rem}
"""


def _css() -> str:
    # strip indentation + blank lines so Streamlit's markdown parser never treats it as code
    return "\n".join(line.strip() for line in _CSS.splitlines() if line.strip())


def _md(s: str) -> None:
    st.markdown(f"<style>{_css()}</style>{s}", unsafe_allow_html=True)


def compute_scorecard(profile: dict, stats: dict, ticker: str = "") -> dict:
    p, s = profile or {}, stats or {}
    vals = []                                      # (value_text, points|None, note)

    pe = _num(p.get("forward_pe"))
    if pe is not None and pe > 0:
        vals.append((f"{pe:.1f}", 2 if pe <= 20 else 1 if pe <= 35 else 0, ""))
    else:
        vals.append(("N/A", None, "Forward P/E is missing or negative"))

    margin = _num(p.get("profit_margin"))
    if margin is None:
        vals.append(("N/A", None, ""))
    else:
        vals.append((f"{margin * 100:.1f}%", 2 if margin >= 0.20 else 1 if margin >= 0.08 else 0, ""))

    growth = _num(p.get("revenue_growth"))
    if growth is None:
        vals.append(("N/A", None, ""))
    else:
        note = "Unusually high: verify before relying on it" if growth > 0.6 else ""
        vals.append((f"{growth * 100:.1f}%", 2 if growth >= 0.10 else 1 if growth >= 0 else 0, note))

    roe = _num(p.get("roe"))
    if roe is None:
        vals.append(("N/A", None, ""))
    else:
        vals.append((f"{roe * 100:.1f}%", 2 if roe >= 0.15 else 1 if roe >= 0.08 else 0, ""))

    ret = _num(s.get("ret_6m"))
    if ret is None:
        vals.append(("N/A", None, "Not enough price history"))
    else:
        vals.append((f"{ret * 100:+.1f}%", 2 if ret >= 0.10 else 1 if ret >= -0.05 else 0, ""))

    rec, n_an = (p.get("recommendation") or "").lower(), _num(p.get("analysts"))
    if n_an is not None and n_an >= 5 and rec in _POS | _NEG | {"hold"}:
        pts = 2 if rec in _POS else 0 if rec in _NEG else 1
        vals.append((f"{_rec_label(rec)} ({int(n_an)})", pts, ""))
    else:
        vals.append(("N/A", None, "Fewer than 5 analysts, or no consensus"))

    beta = _num(p.get("beta"))
    if beta is None:
        vals.append(("N/A", None, ""))
    else:
        vals.append((f"{beta:.2f}", 2 if beta <= 1.0 else 1 if beta <= 1.5 else 0, ""))

    items = []
    for (name, metric, rule), why, (value, points, note) in zip(RULES, _WHY, vals):
        items.append({"name": name, "metric": metric, "rule": rule, "why": why,
                      "value": value, "points": points, "note": note})

    scored = [i for i in items if i["points"] is not None]
    covered, total = len(scored), len(items)
    points = sum(i["points"] for i in scored)
    max_pts = 2 * covered
    pct = points / max_pts if covered >= 3 else None
    if pct is None:
        tier, color = "Not enough data", "#8B93A7"
    elif pct >= 0.70:
        tier, color = "Strong on these checks", "#10B981"
    elif pct >= 0.45:
        tier, color = "Mixed on these checks", "#F59E0B"
    else:
        tier, color = "Weak on these checks", "#F43F5E"
    return {"items": items, "points": points, "max": max_pts, "pct": pct,
            "covered": covered, "total": total, "tier": tier, "color": color}


def _pill(points) -> str:
    if points is None:
        return '<span class="sc-p na">N/A</span>'
    return f'<span class="sc-p p{points}">{points}/2</span>'


def render_scorecard(sc: dict, section: bool = True) -> None:
    """Full breakdown for one stock (used inside reports)."""
    if section:
        render_section("🧾", "Research scorecard")
    big = "—" if sc["pct"] is None else f'{sc["points"]}<span>/{sc["max"]}</span>'
    width = 0 if sc["pct"] is None else round(sc["pct"] * 100)
    rows = "".join(
        f'<div class="sc-row"><div class="sc-n">{h(i["name"])}<span>{h(i["metric"])}</span></div>'
        f'<div class="sc-v">{h(i["value"])}</div><div>{_pill(i["points"])}</div>'
        f'<div class="sc-w">{h(i["why"])}<i>{h(i["rule"])}</i>'
        f'{"<b>" + h(i["note"]) + "</b>" if i["note"] else ""}</div></div>'
        for i in sc["items"]
    )
    _md(
        f'<div class="sc" style="--k:{sc["color"]};">'
        f'<div class="sc-top"><div class="sc-big">{big}</div><div>'
        f'<div class="sc-tier">{h(sc["tier"])}</div>'
        f'<div class="sc-sub">{sc["covered"]} of {sc["total"]} checks had data</div></div></div>'
        f'<div class="sc-bar"><div style="width:{width}%"></div></div>{rows}</div>'
        '<div class="rp-note">Seven simple, transparent checks on Yahoo Finance data. Thresholds are generic '
        'and ignore industry norms (for example, banks and software companies are valued differently). '
        'This is a snapshot, not a prediction and not financial advice.</div>'
    )


def render_score_matrix(cards: list) -> None:
    """Side-by-side scorecards. cards = [(label, ticker, scorecard), ...]."""
    n = len(cards)
    head = ('<div class="scm-r"><div class="scm-h">Criterion</div>'
            + "".join(f'<div class="scm-h">{h(label)}</div>' for label, _t, _sc in cards) + "</div>")
    rows = []
    for idx, (name, metric, _rule) in enumerate(RULES):
        cells = "".join(
            f'<div class="scm-c">{_pill(sc["items"][idx]["points"])}'
            f'<span class="scm-v">{h(sc["items"][idx]["value"])}</span></div>'
            for _l, _t, sc in cards
        )
        rows.append(f'<div class="scm-r"><div class="sc-n">{h(name)}<span>{h(metric)}</span></div>{cells}</div>')
    totals = "".join(
        f'<div class="scm-c" style="--k:{sc["color"]};">'
        f'<div class="sc-big">{"—" if sc["pct"] is None else str(sc["points"]) + "<span>/" + str(sc["max"]) + "</span>"}</div>'
        f'<div class="sc-tier" style="font-size:.78rem;">{h(sc["tier"])}</div>'
        f'<span class="scm-v">{sc["covered"]} of {sc["total"]} checks had data</span></div>'
        for _l, _t, sc in cards
    )
    legend = "".join(f"<li><b>{h(a)}</b> ({h(b)}): {h(c)}</li>" for a, b, c in RULES)
    _md(
        f'<div class="scm" style="--n:{n};">{head}{"".join(rows)}'
        f'<div class="scm-r scm-tot"><div class="scm-h">Total score</div>{totals}</div></div>'
        '<details class="ro-more" style="margin-top:.6rem;"><summary>How the scores work</summary>'
        f'<ul class="sc-legend">{legend}</ul></details>'
        '<div class="rp-note">A snapshot from seven generic, transparent rules. It ignores industry norms, '
        'is not a prediction, and is not financial advice. A missing value is N/A, not zero.</div>'
    )