import time
import uuid
import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from langchain_core.messages import HumanMessage, AIMessage
from agent import financial_agent_app
from ui.theme import inject_theme
from ui.components import render_hero, render_pipeline, render_market_tape
from ui.market import get_ticker_data
from ui.background import inject_3d_background, set_scene_mode as _set_scene
from ui.chart3d import render_chart_3d
from ui.motion import scroll_to_latest, animate_chat_placeholder
from ui.landing import render_landing
from ui.search import render_search
from ui.data import get_profile, get_news, stamp, currency, time_ago
from ui.report import (inject_report_css, compute_signals, bottom_line_from, render_summary,
                       render_key_metrics, render_signals, render_overview, render_news,
                       render_freshness)
from ui.sidebar import render_sidebar, render_history, record_history
from ui.prices import get_price_stats, price_error
from ui.scorecard import compute_scorecard, render_scorecard
from ui.compare import render_compare_entry, render_compare_view
from ui.overview import render_overview_entry
from ui.polish import perf_enabled, inject_polish_css, disable_3d_background, refresh_data
from ui.followup import render_followups
from ui.store import load_state, persist_state          # NEW

# Example questions that type themselves into the chat box
PROMPTS = [
    "Is Nvidia a good buy right now?",
    "Give me a full analysis of Infosys",
    "Should I invest in Apple?",
    "What's the outlook for Reliance?",
    "Analyse TCS for a long-term investor",
]

# =====================================================================
# PAGE CONFIG (must be the first Streamlit call, and only called once)
# =====================================================================
st.set_page_config(page_title="Agentic Finance Analyst", page_icon="📈", layout="wide")

# Restore the saved watchlist / recent research / performance setting (once per browser session)
load_state()                                             # NEW

# Performance mode (sidebar toggle): no 3D globe, no typing animation, no blur effects
PERF = perf_enabled()

inject_theme()
inject_report_css()
inject_polish_css(PERF)
if PERF:
    disable_3d_background()
else:
    inject_3d_background()


def set_scene_mode(mode: str = "idle", ticker: str = "") -> None:
    """Drive the 3D scene, unless Performance mode has switched it off."""
    if not PERF:
        _set_scene(mode, ticker)

# =====================================================================
# HEADER
# =====================================================================
render_hero(
    title_plain="Agentic",
    title_gradient="Finance Analyst",
    subtitle="Autonomous multi-agent research that turns live market data and news into plain-English investment reports.",
    chips=["LangGraph", "Gemini 2.5 Flash", "Tavily Search", "Yahoo Finance"],
)
render_market_tape(get_ticker_data())

# =====================================================================
# HELPERS
# =====================================================================
def render_report(content: str, sentiment: str = None, animate: bool = False, uid: str = "r"):
    """Renders the AI report text.
    The container key becomes a CSS class (st-key-rpt_<tone>_<anim|still>_<uid>) that the theme
    uses to tint the left edge by sentiment and to reveal fresh answers section by section.
    Escapes bare '$' signs first, since Streamlit's markdown treats single $ as LaTeX
    math-mode delimiters, which mangles currency figures in the same paragraph."""
    safe_content = re.sub(r'(?<!\\)\$', r'\\$', content)
    tone = sentiment.lower() if sentiment in ("BULLISH", "NEUTRAL", "BEARISH") else "none"
    with st.container(key=f"rpt_{tone}_{'anim' if animate else 'still'}_{uid}"):
        st.markdown(safe_content)


# ---- price chart (uses the cached daily history, so replaying old messages costs no downloads) ----
_RANGE_DAYS = {"1M": 21, "3M": 63, "6M": 126, "1Y": None}


def _price_figure(ticker: str, s: dict, kind: str, days):
    cur = currency(ticker)
    n = len(s["close"])
    k = n if days is None else min(days + 1, n)
    x = s["dates"][-k:]
    o, hi, lo, c = (s[key][-k:] for key in ("open", "high", "low", "close"))
    vol = (s.get("volume") or [])[-k:]
    has_vol = bool(vol) and any(v > 0 for v in vol)
    ma20 = pd.Series(s["close"]).rolling(20).mean().iloc[-k:].tolist()
    line_color = "#10B981" if c[-1] >= c[0] else "#F43F5E"

    fig = make_subplots(rows=2 if has_vol else 1, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.78, 0.22] if has_vol else [1.0])
    if kind == "Candles":
        fig.add_trace(go.Candlestick(
            x=x, open=o, high=hi, low=lo, close=c, name="Price", showlegend=False,
            increasing=dict(line=dict(color="#10B981", width=1), fillcolor="rgba(16,185,129,.55)"),
            decreasing=dict(line=dict(color="#F43F5E", width=1), fillcolor="rgba(244,63,94,.55)"),
        ), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(
            x=x, y=c, mode="lines", name="Close", line=dict(color=line_color, width=2.2),
            hovertemplate=f"Close: {cur}%{{y:,.2f}}<extra></extra>",
        ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=ma20, mode="lines", name="20-day average", line=dict(color="#A78BFA", width=1.4, dash="dot"),
        hovertemplate=f"20-day avg: {cur}%{{y:,.2f}}<extra></extra>",
    ), row=1, col=1)
    if has_vol:
        colors = ["rgba(16,185,129,.45)" if cc >= oo else "rgba(244,63,94,.45)" for oo, cc in zip(o, c)]
        fig.add_trace(go.Bar(x=x, y=vol, marker_color=colors, name="Volume", showlegend=False,
                             hovertemplate="Volume: %{y:,.0f}<extra></extra>"), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", height=340 if has_vol else 300,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified",
        font=dict(family="Inter, sans-serif", color="#9AA3B8", size=12),
        legend=dict(orientation="h", x=1, xanchor="right", y=1.1, font=dict(size=11)),
        hoverlabel=dict(bgcolor="rgba(10,14,23,.95)", bordercolor="rgba(255,255,255,.2)",
                        font=dict(family="Inter, sans-serif", size=12, color="#E8ECF4")),
    )
    fig.update_xaxes(type="date", showgrid=False, rangeslider_visible=False,
                     rangebreaks=[dict(bounds=["sat", "mon"])],      # no weekend gaps
                     showspikes=True, spikemode="across", spikethickness=1,
                     spikedash="dot", spikecolor="rgba(255,255,255,.35)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,.06)", zeroline=False)
    fig.update_yaxes(tickprefix=cur, row=1, col=1)
    return fig


def render_price_chart(ticker: str, uid: str, s: dict):
    """Chart with Line / Candles / 3D views and a 1M-1Y range. `uid` keeps each message's controls separate.
    Changing the type or range only reruns the script: the answer itself lives in session state."""
    c1, c2 = st.columns([1.3, 1.7])
    kind = c1.radio("Chart type", ["Line", "Candles", "3D"], horizontal=True,
                    key=f"ck_{uid}", label_visibility="collapsed")
    # always created (just disabled in 3D), so the chosen range survives switching to 3D and back
    rng = c2.radio("Range", list(_RANGE_DAYS), index=2, horizontal=True,
                   key=f"cr_{uid}", label_visibility="collapsed", disabled=(kind == "3D"))
    if kind == "3D":
        render_chart_3d(ticker)
        return
    if not s or not s.get("open"):
        reason = price_error(ticker)
        st.caption("⚠️ Price chart unavailable right now: Yahoo Finance returned no price history"
                   + (f" ({reason})" if reason else "")
                   + ". Press ↻ Retry above or ⟳ Refresh data in the sidebar.")
        return
    try:
        fig = _price_figure(ticker, s, kind, _RANGE_DAYS[rng])
        st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})
        st.caption(f"Daily data through {s['last_date']} · Yahoo Finance, adjusted for splits and dividends"
                   + (f" · ⚠️ Showing saved data from {time_ago(s['fetched_at'])} because Yahoo did not respond "
                      "to the latest refresh" if s.get("stale") else ""))
    except Exception:
        st.caption("⚠️ The price chart could not be drawn.")


def extract_sentiment(text: str):
    """Pulls the SENTIMENT tag out of the report and returns (sentiment, cleaned_text)."""
    match = re.search(r"SENTIMENT:\s*(BULLISH|NEUTRAL|BEARISH)", text, re.IGNORECASE)
    if not match:
        return None, text
    sentiment = match.group(1).upper()
    cleaned = (text[:match.start()] + text[match.end():]).strip()
    return sentiment, cleaned


def build_markdown_export(ticker: str, sentiment: str, content: str, ts=None) -> str:
    """Builds a clean markdown file for download, including metadata header."""
    header = f"# Investment Report: {ticker}\n\n"
    if sentiment:
        header += f"**Sentiment:** {sentiment.title()}\n\n"
    if ts:
        header += f"*Generated {stamp(ts)}. Market data: Yahoo Finance. Analysis: Gemini.*\n\n"
    header += "---\n\n"
    return header + content + "\n\n---\n*Educational research only. Not financial advice.*\n"


def render_assistant_block(ticker, sentiment, metrics, content, uid, ts=None, animate=False,
                           expanded=False, followups=None):
    """One complete answer: compact summary, chart, then collapsible detail sections.
    Used for history replay, cached answers and live answers, so they always look the same.
    `expanded` opens the AI report section (used for the newest answer only).
    `followups` is the list stored on the message (follow-up questions and answers)."""
    if not ticker:                                   # e.g. "couldn't identify a ticker" or an error
        render_report(content, sentiment, animate=animate, uid=uid)
        return

    with st.spinner("Loading market data, fundamentals and news…"):
        profile = get_profile(ticker)
        stats = get_price_stats(ticker)
        news = get_news(ticker, company=profile.get("name") or "")

    signals = compute_signals(profile, metrics, ticker)
    card = compute_scorecard(profile, stats, ticker)

    notices = []
    if not metrics:
        notices.append("A live quote was not captured for this analysis, so price figures are unavailable.")
    if not profile:
        notices.append("Company fundamentals are unavailable right now (Yahoo Finance).")
    if not stats:
        notices.append("Price history is unavailable right now (Yahoo Finance).")

    render_summary(ticker, profile, metrics, sentiment, signals, card, bottom_line_from(content), ts, notices)
    if not profile or not stats:
        st.button("↻ Retry loading market data", key=f"retry_{uid}", on_click=refresh_data)

    render_price_chart(ticker, uid, stats)

    with st.expander("🧠 AI analyst report", expanded=expanded):
        render_report(content, sentiment, animate=animate, uid=uid)

    with st.expander("📊 Fundamentals", expanded=False):
        render_key_metrics(profile, metrics, ticker, section=False)

    n_pos, n_neg, n_risk = len(signals["pos"]), len(signals["neg"]), len(signals["risk"])
    with st.expander(f"⚖️ Signals & risks · {n_pos} ▲  {n_neg} ▼  {n_risk} ⚠", expanded=False):
        render_signals(signals, section=False)

    sc_label = "🧾 Research scorecard" + (f" · {card['points']}/{card['max']}" if card["pct"] is not None else "")
    with st.expander(sc_label, expanded=False):
        render_scorecard(card, section=False)

    with st.expander("🏢 About the company", expanded=False):
        render_overview(profile, section=False)

    with st.expander(f"📰 Recent news ({len(news)})", expanded=False):
        render_news(ticker, news, section=False)

    if followups is not None:
        pending = st.session_state.get("fu_pending")
        opening = bool(pending and pending.get("uid") == uid)      # keep it open while a question is answered
        label = "💬 Ask a follow-up question" + (f" · {len(followups)}" if followups else "")
        with st.expander(label, expanded=bool(followups) or opening):
            render_followups(uid, followups, ticker, profile, metrics, content, news, ts)

    with st.expander("🔎 Sources & data freshness", expanded=False):
        render_freshness(profile, ts, stats)

    st.download_button(
        label="⬇️ Download report (Markdown)",
        data=build_markdown_export(ticker, sentiment, content, ts),
        file_name=f"{ticker}_report.md",
        mime="text/markdown",
        key=f"dl_{uid}",
    )


def safe_render_block(ticker, sentiment, metrics, content, uid, **kwargs):
    """Render an answer; if a section fails, say so and fall back to the plain AI text.
    The answer is already saved in session state, so an error here can never lose it."""
    try:
        render_assistant_block(ticker, sentiment, metrics, content, uid=uid, **kwargs)
    except Exception as e:
        st.error(f"Part of this report could not be displayed ({type(e).__name__}: {e}). "
                 "Your analysis is saved. The AI text is shown below.")
        render_report(content, sentiment, animate=False, uid=f"{uid}fb")

# =====================================================================
# SESSION STATE INITIALIZATION
# =====================================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "watchlist" not in st.session_state:
    st.session_state.watchlist = []

if "pending_query" not in st.session_state:
    st.session_state.pending_query = None

if "response_cache" not in st.session_state:
    st.session_state.response_cache = {}

if "compare_items" not in st.session_state:
    st.session_state.compare_items = None

# Drive the 3D scene: calm standby globe when there's no conversation yet
if not st.session_state.messages:
    set_scene_mode("idle")

# =====================================================================
# SIDEBAR (branding, controls, watchlist, recent research, popular stocks)
# =====================================================================
with st.sidebar:
    side_query, history_slot = render_sidebar()
if side_query:
    st.session_state.pending_query = side_query
    st.session_state.compare_items = None
    st.rerun()


def finish_sidebar():
    """Save any changes, then fill the 'Recent research' list last,
    so a just-finished analysis shows up immediately."""
    persist_state()                                      # NEW: writes only if something changed
    again = render_history(history_slot)
    if again:
        st.session_state.pending_query = again
        st.session_state.compare_items = None
        st.rerun()

# =====================================================================
# SEARCH BAR (everywhere) + COMPARE STOCKS (entry panel)
# =====================================================================
searching = render_search()
render_compare_entry()
render_overview_entry()

if st.session_state.compare_items:
    cmp_pick = render_compare_view(st.session_state.compare_items)
    finish_sidebar()
    if cmp_pick:
        st.session_state.compare_items = None
        st.session_state.pending_query = cmp_pick
        st.rerun()
    st.stop()

# =====================================================================
# LANDING SCREEN (only when there is no conversation yet)
# =====================================================================
landing_slot = st.empty()
if not st.session_state.messages and not st.session_state.pending_query and not searching:
    with landing_slot.container():
        picked = render_landing()
    if picked:
        st.session_state.pending_query = picked
        st.rerun()

# =====================================================================
# RENDER CHAT HISTORY (styled replay; only the newest answer keeps its AI report open)
# =====================================================================
last_ai = max((i for i, m in enumerate(st.session_state.messages) if m["role"] == "assistant"), default=-1)
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            safe_render_block(
                msg.get("ticker"), msg.get("sentiment"), msg.get("metrics", {}),
                msg["content"], uid=f"m{i}", ts=msg.get("ts"), expanded=(i == last_ai),
                followups=msg.setdefault("followups", []) if msg.get("ticker") else None,
            )
        else:
            st.markdown(msg["content"])

# =====================================================================
# DETERMINE INPUT SOURCE (typed vs. search/watchlist/history click vs. landing card)
# =====================================================================
if st.session_state.pending_query:
    user_input = st.session_state.pending_query
    st.session_state.pending_query = None
else:
    user_input = st.chat_input("Ask about a stock (e.g., 'Is Nvidia a good buy right now?')")

# typing animation in the chat box placeholder (starts once, survives reruns; off in Performance mode)
if not PERF:
    animate_chat_placeholder(PROMPTS)

# a question was submitted: clear the landing screen right away
if user_input:
    landing_slot.empty()

# =====================================================================
# MAIN CHAT FLOW
# =====================================================================
if user_input:
    # 1. Display the user's question instantly in the UI
    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 1b. Check cache first — avoids burning API quota on a repeated identical question
    #     (e.g. re-running the same demo question multiple times while practicing).
    cache_key = user_input.strip().lower()
    cached = st.session_state.response_cache.get(cache_key)

    if cached:
        extracted_ticker = cached["ticker"]
        final_reply = cached["content"]
        sentiment = cached["sentiment"]
        metrics = cached.get("metrics", {})
        ts = cached.get("ts")
        set_scene_mode(sentiment.lower() if sentiment else "neutral", extracted_ticker)

        # save the answer FIRST, then render it: a display problem can never lose it
        a_idx = len(st.session_state.messages)
        st.session_state.messages.append({
            "role": "assistant", "content": final_reply,
            "ticker": extracted_ticker, "sentiment": sentiment, "metrics": metrics, "ts": ts,
            "followups": [],
        })
        record_history(user_input, extracted_ticker, sentiment)
        with st.chat_message("assistant"):
            st.caption("⚡ Served from cache — no API call used")
            safe_render_block(
                extracted_ticker, sentiment, metrics, final_reply,
                uid=f"m{a_idx}", ts=ts, animate=True, expanded=True,
                followups=st.session_state.messages[a_idx]["followups"] if extracted_ticker else None,
            )
        finish_sidebar()
        scroll_to_latest()
        st.stop()

    # 2. Pack parameters inside the LangGraph state dictionary
    inputs = {"messages": [HumanMessage(content=user_input)]}
    config = {"configurable": {"thread_id": st.session_state.thread_id}}

    # 3. Stream the graph execution with a multi-stage status indicator
    extracted_ticker = ""
    final_reply = ""
    metrics = {}
    set_scene_mode("research")
    with st.status("🔎 Identifying ticker...", expanded=True) as status:
        # Pipeline tracker: Identify -> Research -> Analyze -> Report
        pipeline_slot = st.empty()
        stage = 0
        pipeline_slot.markdown(render_pipeline(stage), unsafe_allow_html=True)
        try:
            for step in financial_agent_app.stream(inputs, config=config, stream_mode="values"):
                new_stage = stage
                if step.get("ticker") and not extracted_ticker:
                    extracted_ticker = step["ticker"]
                    if extracted_ticker:
                        status.update(label=f"📊 Gathering data for {extracted_ticker}...")
                        set_scene_mode("research", extracted_ticker)
                        new_stage = max(new_stage, 1)
                if step.get("stock_data"):
                    status.update(label="🧠 Compiling analysis...")
                    new_stage = max(new_stage, 2)
                if step.get("metrics"):
                    metrics = step["metrics"]
                if step["messages"] and isinstance(step["messages"][-1], AIMessage):
                    final_reply = step["messages"][-1].content
                if new_stage != stage:
                    stage = new_stage
                    pipeline_slot.markdown(render_pipeline(stage, extracted_ticker), unsafe_allow_html=True)

            if extracted_ticker and final_reply:
                pipeline_slot.markdown(render_pipeline(3, extracted_ticker), unsafe_allow_html=True)
            status.update(label="✅ Report ready", state="complete", expanded=False)
        except Exception as e:
            error_str = str(e)
            if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                final_reply = (
                    "⏳ **Daily AI request limit reached.**\n\n"
                    "The free tier of the Gemini API allows a limited number of requests per day. "
                    "You've used up today's quota — it resets automatically after 24 hours.\n\n"
                    "**To fix this permanently:** enable billing on your Google AI Studio project "
                    "(aistudio.google.com) to move to a much higher paid-tier limit.\n\n"
                    "**In the meantime:** try again later today, or tomorrow."
                )
            else:
                final_reply = (
                    f"⚠️ An error occurred during agent execution: {error_str}\n\n"
                    "*Make sure your API keys in the `.env` file are correct.*"
                )
            status.update(label="❌ Error occurred", state="error", expanded=True)

    # 3b. Extract sentiment tag from the completed report (must run after streaming ends)
    sentiment, final_reply = extract_sentiment(final_reply)
    if extracted_ticker:
        set_scene_mode(sentiment.lower() if sentiment else "neutral", extracted_ticker)
    else:
        set_scene_mode("idle")

    # 4. Save the answer FIRST (history, cache, recent research), then render it.
    #    Rendering is the part that can fail; the analysis itself must never be lost.
    ts = time.time()
    a_idx = len(st.session_state.messages)
    st.session_state.messages.append({
        "role": "assistant",
        "content": final_reply,
        "ticker": extracted_ticker,
        "sentiment": sentiment,
        "metrics": metrics,
        "ts": ts,
        "followups": [],
    })

    # Cache successful responses (skip caching error messages) so a repeated
    # identical question later doesn't burn additional API quota.
    is_error = final_reply.startswith("⚠️") or final_reply.startswith("⏳")
    if extracted_ticker and not is_error:
        st.session_state.response_cache[cache_key] = {
            "ticker": extracted_ticker,
            "content": final_reply,
            "sentiment": sentiment,
            "metrics": metrics,
            "ts": ts,
        }
        record_history(user_input, extracted_ticker, sentiment)

    # 5. Render the finalized response: summary + chart + collapsible sections
    with st.chat_message("assistant"):
        safe_render_block(
            extracted_ticker, sentiment, metrics, final_reply,
            uid=f"m{a_idx}", ts=ts, animate=True, expanded=True,
            followups=st.session_state.messages[a_idx]["followups"] if extracted_ticker else None,
        )

    finish_sidebar()
    scroll_to_latest()

# no question this run: draw the 'Recent research' list now
# (question runs draw it themselves, right after their answer is ready)
if not user_input:
    finish_sidebar()