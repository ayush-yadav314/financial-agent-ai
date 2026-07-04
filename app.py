import uuid
import re
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from langchain_core.messages import HumanMessage, AIMessage
from agent import financial_agent_app

# =====================================================================
# PAGE CONFIG (Step 1 & 2)
# =====================================================================
st.set_page_config(page_title="Agentic Finance Analyst", page_icon="📈", layout="wide")

# =====================================================================
# HEADER (Step 2)
# =====================================================================
st.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <h1 style="margin-bottom: 0;">📈 Agentic Finance Analyst</h1>
        <p style="color: gray; font-size: 0.9rem;">Multi-agent research powered by LangGraph & Gemini</p>
    </div>
""", unsafe_allow_html=True)

st.divider()

# =====================================================================
# HELPERS
# =====================================================================
def render_report(content: str):
    """Renders assistant report content inside a styled card (Step 3)."""
    st.markdown(
        '<div style="background-color:#1A1D23; padding:1.2rem; border-radius:12px; border:1px solid #2A2E37;">',
        unsafe_allow_html=True
    )
    st.markdown(content)
    st.markdown('</div>', unsafe_allow_html=True)


def render_price_chart(ticker: str):
    """Renders a 6-month candlestick chart for the given ticker (Step 5)."""
    try:
        hist = yf.Ticker(ticker).history(period="6mo")
        if hist.empty:
            return
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index,
            open=hist['Open'], high=hist['High'],
            low=hist['Low'], close=hist['Close'],
            increasing_line_color="#00C853", decreasing_line_color="#FF5252"
        )])
        fig.update_layout(
            template="plotly_dark",
            height=350,
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_rangeslider_visible=False,
            title=f"{ticker} — 6 Month Price History"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass


def render_metric_cards(ticker: str):
    """Renders quick-glance metric cards for price, P/E, and 52-week range (Step 6)."""
    try:
        info = yf.Ticker(ticker).info
        price = info.get("currentPrice")
        pe = info.get("trailingPE")
        low_52 = info.get("fiftyTwoWeekLow")
        high_52 = info.get("fiftyTwoWeekHigh")
        prev_close = info.get("previousClose")

        delta = None
        if price and prev_close:
            delta = f"{price - prev_close:+.2f} ({((price - prev_close) / prev_close) * 100:+.2f}%)"

        col1, col2, col3 = st.columns(3)
        col1.metric("Price", f"${price:.2f}" if price else "N/A", delta)
        col2.metric("P/E Ratio", f"{pe:.2f}" if pe else "N/A")
        col3.metric("52W Range", f"${low_52:.0f} – ${high_52:.0f}" if low_52 and high_52 else "N/A")
    except Exception:
        pass


def extract_sentiment(text: str):
    """Pulls the SENTIMENT tag out of the report and returns (sentiment, cleaned_text)."""
    match = re.search(r"SENTIMENT:\s*(BULLISH|NEUTRAL|BEARISH)", text, re.IGNORECASE)
    if not match:
        return None, text
    sentiment = match.group(1).upper()
    cleaned = (text[:match.start()] + text[match.end():]).strip()
    return sentiment, cleaned


def render_sentiment_badge(sentiment: str):
    """Renders a colored pill badge indicating bullish/neutral/bearish sentiment (Step 8)."""
    colors = {
        "BULLISH": ("#00C853", "🟢 Bullish"),
        "NEUTRAL": ("#FFC107", "🟡 Neutral"),
        "BEARISH": ("#FF5252", "🔴 Bearish"),
    }
    color, label = colors.get(sentiment, ("#888888", "⚪ Unclear"))
    st.markdown(f"""
        <div style="display:inline-block; background-color:{color}22; color:{color};
                    border:1px solid {color}; padding:0.3rem 0.9rem; border-radius:20px;
                    font-weight:600; font-size:0.9rem; margin-bottom:0.8rem;">
            {label}
        </div>
    """, unsafe_allow_html=True)


def build_markdown_export(ticker: str, sentiment: str, content: str) -> str:
    """Builds a clean markdown file for download, including metadata header."""
    header = f"# Investment Report: {ticker}\n\n"
    if sentiment:
        header += f"**Sentiment:** {sentiment.title()}\n\n"
    header += "---\n\n"
    return header + content

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

# =====================================================================
# SIDEBAR (Step 4 — Controls & Watchlist)
# =====================================================================
with st.sidebar:
    st.header("⚙️ Controls")

    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

    st.divider()
    st.subheader("📌 Watchlist")

    new_ticker = st.text_input("Add ticker", placeholder="e.g. AAPL", label_visibility="collapsed")
    if st.button("➕ Add to watchlist", use_container_width=True) and new_ticker:
        ticker_clean = new_ticker.strip().upper()
        if ticker_clean and ticker_clean not in st.session_state.watchlist:
            st.session_state.watchlist.append(ticker_clean)
        st.rerun()

    if not st.session_state.watchlist:
        st.caption("No tickers saved yet.")

    for t in st.session_state.watchlist:
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(f"📊 {t}", key=f"wl_{t}", use_container_width=True):
                st.session_state.pending_query = f"Give me a full analysis of {t}"
                st.rerun()
        with col2:
            if st.button("✕", key=f"remove_{t}"):
                st.session_state.watchlist.remove(t)
                st.rerun()

# =====================================================================
# RENDER CHAT HISTORY (Step 3, 5, 6 — styled replay incl. chart + metrics)
# =====================================================================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            if msg.get("ticker"):
                render_price_chart(msg["ticker"])
                render_metric_cards(msg["ticker"])
            if msg.get("sentiment"):
                render_sentiment_badge(msg["sentiment"])
            render_report(msg["content"])
            if msg.get("ticker"):
                export_content = build_markdown_export(msg["ticker"], msg.get("sentiment"), msg["content"])
                st.download_button(
                    label="⬇️ Download Report",
                    data=export_content,
                    file_name=f"{msg['ticker']}_report.md",
                    mime="text/markdown",
                    key=f"download_{id(msg)}"
                )
        else:
            st.markdown(msg["content"])

# =====================================================================
# DETERMINE INPUT SOURCE (Step 4 — typed vs. watchlist click)
# =====================================================================
if st.session_state.pending_query:
    user_input = st.session_state.pending_query
    st.session_state.pending_query = None
else:
    user_input = st.chat_input("Ask about a stock (e.g., 'Is Nvidia a good buy right now?')")

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
        with st.chat_message("assistant"):
            st.caption("⚡ Served from cache — no API call used")
            if extracted_ticker:
                render_price_chart(extracted_ticker)
                render_metric_cards(extracted_ticker)
            if sentiment:
                render_sentiment_badge(sentiment)
            render_report(final_reply)
            if extracted_ticker:
                export_content = build_markdown_export(extracted_ticker, sentiment, final_reply)
                st.download_button(
                    label="⬇️ Download Report",
                    data=export_content,
                    file_name=f"{extracted_ticker}_report.md",
                    mime="text/markdown",
                    key="download_cached"
                )
        st.session_state.messages.append({
            "role": "assistant", "content": final_reply,
            "ticker": extracted_ticker, "sentiment": sentiment
        })
        st.stop()

    # 2. Pack parameters inside the LangGraph state dictionary
    inputs = {"messages": [HumanMessage(content=user_input)]}
    config = {"configurable": {"thread_id": st.session_state.thread_id}}

    # 3. Stream the graph execution with a multi-stage status indicator (Step 7)
    extracted_ticker = ""
    final_reply = ""
    with st.status("🔎 Identifying ticker...", expanded=True) as status:
        try:
            for step in financial_agent_app.stream(inputs, config=config, stream_mode="values"):
                if step.get("ticker") and not extracted_ticker:
                    extracted_ticker = step["ticker"]
                    if extracted_ticker:
                        status.update(label=f"📊 Gathering data for {extracted_ticker}...")
                if step.get("stock_data"):
                    status.update(label="🧠 Compiling analysis...")
                if step["messages"] and isinstance(step["messages"][-1], AIMessage):
                    final_reply = step["messages"][-1].content

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

    # 4. Render the agent's finalized response: chart + metrics + sentiment + styled report
    with st.chat_message("assistant"):
        if extracted_ticker:
            render_price_chart(extracted_ticker)
            render_metric_cards(extracted_ticker)
        if sentiment:
            render_sentiment_badge(sentiment)
        render_report(final_reply)

        if extracted_ticker:
            export_content = build_markdown_export(extracted_ticker, sentiment, final_reply)
            st.download_button(
                label="⬇️ Download Report",
                data=export_content,
                file_name=f"{extracted_ticker}_report.md",
                mime="text/markdown",
                key="download_live"
            )

    st.session_state.messages.append({
        "role": "assistant",
        "content": final_reply,
        "ticker": extracted_ticker,
        "sentiment": sentiment
    })

    # Cache successful responses (skip caching error messages) so a repeated
    # identical question later doesn't burn additional API quota.
    is_error = final_reply.startswith("⚠️") or final_reply.startswith("⏳")
    if extracted_ticker and not is_error:
        st.session_state.response_cache[cache_key] = {
            "ticker": extracted_ticker,
            "content": final_reply,
            "sentiment": sentiment
        }
