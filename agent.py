import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yfinance as yf
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.tools import TavilyAnswer

# Explicitly pull configurations from your local .env file
load_dotenv()

MODEL_NAME = "gemini-2.5-flash"

# Common company name -> ticker lookups, checked BEFORE calling the LLM.
# Saves an API call (and daily free-tier quota) for the most frequently asked companies.
# NOTE: Tata Motors was demerged in late 2025. The old TATAMOTORS.NS symbol no longer
# exists: the passenger-vehicle business (incl. Jaguar Land Rover) trades as TMPV and the
# commercial-vehicle business trades as TMCV.
KNOWN_TICKERS = {
    "apple": "AAPL", "tesla": "TSLA", "nvidia": "NVDA", "microsoft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "amazon": "AMZN", "meta": "META",
    "facebook": "META", "netflix": "NFLX", "amd": "AMD", "intel": "INTC",
    "tata motors passenger vehicles": "TMPV.NS", "tata motors passenger": "TMPV.NS",
    "tata motors commercial vehicles": "TMCV.NS", "tata motors commercial": "TMCV.NS",
    "tmpv": "TMPV.NS", "tmcv": "TMCV.NS",
    "tata motors": "TMPV.NS", "tata steel": "TATASTEEL.NS",
    "tata consultancy": "TCS.NS", "tcs": "TCS.NS", "tata power": "TATAPOWER.NS",
    "reliance": "RELIANCE.NS", "infosys": "INFY.NS", "hdfc bank": "HDFCBANK.NS",
    "icici bank": "ICICIBANK.NS", "wipro": "WIPRO.NS", "adani enterprises": "ADANIENT.NS",
    "state bank of india": "SBIN.NS", "sbi": "SBIN.NS",
}

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "GBP": "£", "GBp": "p", "EUR": "€", "JPY": "¥"}

# Matches an explicit Yahoo ticker in brackets, e.g. "Analyse Microsoft (MSFT)" or "(TCS.NS)".
# Case-sensitive on purpose, so ordinary words like "(and)" are never mistaken for tickers.
_EXPLICIT_TICKER = re.compile(r'\(([A-Z][A-Z0-9&\-]{0,11}(?:\.[A-Z]{1,3})?)\)')


def lookup_known_ticker(text: str):
    """Checks the user's message for a ticker before spending an LLM call on extraction.
    1) An explicit bracketed ticker like '(MSFT)' or '(HDFCBANK.NS)' wins immediately
       (this is what the landing-page catalog and search results send).
    2) Otherwise the static company->ticker map is checked using word-boundary regex
       (not a plain substring check) so short entries like 'meta' or 'sbi' don't
       false-positive-match inside unrelated words (e.g. 'metadata', 'metaphor').
       Longest names are tried first so that 'tata motors commercial vehicles'
       wins over the shorter 'tata motors'.
    Returns None if no confident match."""
    explicit = _EXPLICIT_TICKER.search(text)
    if explicit:
        return explicit.group(1)

    text_lower = text.lower()
    for name, ticker in sorted(KNOWN_TICKERS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(r'\b' + re.escape(name) + r'\b', text_lower):
            return ticker
    return None

# =====================================================================
# 1. DEFINE THE SHARED AGENT STATE
# =====================================================================
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    ticker: str
    stock_data: str
    web_research: str
    metrics: dict

# =====================================================================
# 2. LLM CLIENTS (instantiated once, not per-call)
# =====================================================================
llm_extractor = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0
)

llm_analyst = ChatGoogleGenerativeAI(
    model=MODEL_NAME,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.2
)

# =====================================================================
# 3. DEFINE THE PROGRAMMATIC TOOLS
# =====================================================================
def fetch_stock_metrics(ticker: str):
    """Tool: Fetches clean numerical fundamentals from Yahoo Finance.
    Falls back to common Indian exchange suffixes (.NS, .BO) if the raw ticker
    doesn't resolve, since the LLM sometimes omits the suffix.
    Also retries once after a short delay if Yahoo Finance returns an empty/blocked
    response, since this is a known intermittent issue with yfinance's unofficial API.
    Returns a tuple: (resolved_ticker_or_original, formatted_metrics_string, metrics_dict)."""
    candidates = [ticker]
    if "." not in ticker:
        candidates += [f"{ticker}.NS", f"{ticker}.BO"]

    last_error = None
    for candidate in candidates:
        for attempt in range(2):  # try once, retry once after a short delay if empty
            try:
                stock = yf.Ticker(candidate)
                info = stock.info
                if not info.get("longName") and not info.get("currentPrice"):
                    if attempt == 0:
                        time.sleep(1.5)  # brief pause — Yahoo's endpoint is sometimes just momentarily rate-limited
                        continue
                    break  # give up on this candidate after retry
                margins = info.get('profitMargins', None)
                margins_display = f"{margins * 100:.2f}%" if isinstance(margins, (int, float)) else "N/A"
                cur = CURRENCY_SYMBOLS.get(info.get("currency"), "")
                metrics_dict = {
                    "price": info.get("currentPrice"),
                    "pe": info.get("trailingPE"),
                    "low_52": info.get("fiftyTwoWeekLow"),
                    "high_52": info.get("fiftyTwoWeekHigh"),
                    "prev_close": info.get("previousClose"),
                }
                formatted = f"""
        Company Name: {info.get('longName', 'N/A')}
        Ticker Used: {candidate}
        Currency: {info.get('currency', 'N/A')}
        Current Market Price: {cur}{info.get('currentPrice', 'N/A')}
        P/E Ratio: {info.get('trailingPE', 'N/A')}
        52-Week High: {cur}{info.get('fiftyTwoWeekHigh', 'N/A')}
        52-Week Low: {cur}{info.get('fiftyTwoWeekLow', 'N/A')}
        Profit Margins: {margins_display}
        """
                return candidate, formatted, metrics_dict
            except Exception as e:
                last_error = e
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                break
    print(f"[AGENT LOG] Metrics unavailable for {ticker} (tried {', '.join(candidates)}). Last error: {last_error!r}")
    return ticker, f"Could not gather market metrics for '{ticker}' (tried: {', '.join(candidates)}). Last error: {last_error}", {}

def search_market_news(ticker: str) -> str:
    """Tool: Fetches web articles and sentiment trends via Tavily."""
    try:
        search = TavilyAnswer()
        return search.run(f"Latest stock market news and financial investor sentiment for ticker: {ticker}")
    except Exception as e:
        return f"Could not gather web research: {str(e)}"


_GENERIC_NAME_WORDS = {
    "the", "inc", "inc.", "corp", "corp.", "corporation", "company", "co", "co.", "ltd", "ltd.",
    "limited", "plc", "holdings", "holding", "group", "ag", "sa", "nv", "llc", "and", "&",
}


def _headline_keywords(company: str, ticker: str) -> list:
    """Words that make a headline 'about' this company: the most distinctive word of its
    name ('NVIDIA Corporation' -> 'NVIDIA') and its ticker symbol ('NVDA')."""
    words = []
    for w in re.findall(r"[A-Za-z0-9&.]+", company or ""):
        w = w.strip(".")
        if len(w) >= 3 and w.lower() not in _GENERIC_NAME_WORDS:
            words.append(w)
            break
    base = (ticker or "").split(".")[0]
    if len(base) >= 3:
        words.append(base)
    return words


def fetch_yahoo_headlines(ticker: str) -> list:
    """Tool: Recent headlines from Yahoo Finance as [{'title', 'publisher', 'when'}].
    Yahoo tags stories loosely, so callers should filter them with format_headlines().
    Returns [] if there are none or Yahoo is unavailable."""
    try:
        items = []
        try:
            got = yf.Ticker(ticker).news
            if got:
                items = list(got)
        except Exception:
            items = []
        if not items:
            try:
                s = yf.Search(ticker, max_results=1, news_count=10, timeout=6)
            except TypeError:                      # older yfinance without those arguments
                s = yf.Search(ticker, news_count=10)
            items = [it for it in (getattr(s, "news", None) or [])
                     if isinstance(it, dict)
                     and ticker in [str(x).upper() for x in (it.get("relatedTickers") or [])]]

        out = []
        for it in items:
            if not isinstance(it, dict):
                continue
            c = it.get("content") if isinstance(it.get("content"), dict) else it
            title = c.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            provider = c.get("provider")
            publisher = (provider.get("displayName") if isinstance(provider, dict) else None) \
                or c.get("publisher") or "unknown source"
            when = ""
            raw = c.get("pubDate") or c.get("displayTime") or c.get("providerPublishTime")
            try:
                if isinstance(raw, (int, float)):
                    when = datetime.fromtimestamp(raw, tz=timezone.utc).strftime("%d %b %Y")
                elif isinstance(raw, str):
                    when = datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d %b %Y")
            except Exception:
                when = ""
            out.append({"title": title.strip(), "publisher": publisher, "when": when})
        return out
    except Exception:
        return []


def format_headlines(items: list, company: str, ticker: str, limit: int = 6) -> str:
    """Keep only headlines whose title names the company, then format them for the analyst.
    Returns '' when none qualify (so unrelated stories are never presented as company news)."""
    patterns = [re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE)
                for k in _headline_keywords(company, ticker)]
    picked = [i for i in items if any(p.search(i["title"]) for p in patterns)]
    return "\n".join(
        f"- {i['title']} ({i['publisher']}{', ' + i['when'] if i['when'] else ''})"
        for i in picked[:limit]
    )

# =====================================================================
# 4. DEFINE THE NODES
# =====================================================================
def state_initializer(state: AgentState):
    """Agent 1: Extracts clean ticker symbol from user statements."""
    # Grab the latest human message text for a quick, free, no-API-call lookup first.
    last_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_text = msg.content
            break

    quick_match = lookup_known_ticker(last_text)
    if quick_match:
        print(f"[AGENT LOG] Ticker resolved from lookup table (no LLM call): {quick_match}")
        return {"ticker": quick_match}

    prompt = f"""
    Analyze the user conversation below. Extract the single primary public stock ticker symbol mentioned,
    in the exact format Yahoo Finance uses.

    IMPORTANT RULES:
    - If the user names a conglomerate or group (e.g. "Tata", "Reliance", "Adani", "Birla") rather than
      a specific listed company, pick the most well-known, most commonly traded listed entity under that
      group (e.g. "Tata" -> Tata Motors Passenger Vehicles -> TMPV.NS; "Reliance" -> RELIANCE.NS). Do not
      invent a ticker that does not exist.
    - Tata Motors was demerged in 2025. The old symbol TATAMOTORS.NS no longer exists. Use TMPV.NS for
      passenger vehicles / Jaguar Land Rover and TMCV.NS for commercial vehicles (trucks and buses).
    - For Indian stocks, ALWAYS include the exchange suffix: ".NS" for NSE (preferred default) or ".BO" for BSE.
    - For US stocks, no suffix is needed (e.g. AAPL, TSLA).
    - For other international exchanges, use the correct Yahoo Finance suffix (e.g. ".L" for London, ".TO" for Toronto).
    - Return ONLY the raw ticker symbol in uppercase. Do not add punctuation or extra words.
    - If you cannot confidently identify one specific real, listed ticker, return NONE.

    Conversation History: {state['messages']}
    """

    response = llm_extractor.invoke([HumanMessage(content=prompt)])
    extracted_ticker = response.content.strip().upper()
    print(f"[AGENT LOG] Extracted Ticker: {extracted_ticker}")

    if extracted_ticker == "NONE" or not re.match(r"^[A-Z]{1,10}(\.[A-Z]{1,3})?$", extracted_ticker):
        return {
            "ticker": "",
            "messages": [AIMessage(content="I couldn't identify a single, specific stock ticker in your message. "
                                            "If you're asking about a group of companies (like Tata or Reliance), "
                                            "could you tell me which specific company you mean, "
                                            "e.g. Tata Motors, Tata Steel, or Tata Consultancy Services?")]
        }
    return {"ticker": extracted_ticker}


def researcher_node(state: AgentState):
    """Agent 2: Gathers metrics and search parameters concurrently."""
    ticker = state["ticker"]
    print(f"[AGENT LOG] Researcher Node running tools for: {ticker}")
    with ThreadPoolExecutor(max_workers=3) as executor:
        metrics_future = executor.submit(fetch_stock_metrics, ticker)
        news_future = executor.submit(search_market_news, ticker)
        headlines_future = executor.submit(fetch_yahoo_headlines, ticker)
        resolved_ticker, metrics, metrics_dict = metrics_future.result()
        news = news_future.result()
        raw_headlines = headlines_future.result()

    # keep only headlines that actually name the company (Yahoo's tagging is loose)
    name_match = re.search(r"Company Name:\s*(.+)", metrics)
    company = name_match.group(1).strip() if name_match else ""
    headlines = format_headlines(raw_headlines, company, resolved_ticker)
    print(f"[AGENT LOG] Yahoo headlines: {len(raw_headlines)} found, "
          f"{len(headlines.splitlines()) if headlines else 0} name the company")
    if headlines:
        news = f"{news}\n\n[YAHOO FINANCE HEADLINES - real, dated, naming the company]\n{headlines}"

    # If a suffix fallback (.NS/.BO) resolved the ticker, propagate that back into state
    # so downstream chart/metric rendering in app.py uses the correct resolvable ticker.
    # metrics_dict carries the raw numeric values forward so app.py doesn't need a
    # second Yahoo Finance call just to render the metric cards.
    return {"stock_data": metrics, "web_research": news, "ticker": resolved_ticker, "metrics": metrics_dict}


def analyst_node(state: AgentState):
    """Agent 3: Compiles complete analytical report outcomes."""
    print(f"[AGENT LOG] Analyst Node compiling final report...")
    today = datetime.now().strftime("%d %B %Y")
    if not state.get("metrics"):
        return {"messages": [AIMessage(content=(
            "⚠️ **No verified market data could be retrieved for this stock right now**, so no report was written. "
            "Yahoo Finance may be rate-limiting this server. Please try again in a few minutes."))]}

    analysis_prompt = f"""
    You are an elite financial research analyst who writes clear, easy-to-understand reports for
    everyday retail investors — not other analysts. Avoid unexplained jargon; if you must use a
    financial term (e.g. P/E ratio, market cap), briefly explain what it means in plain language.

    Synthesize a comprehensive investment report based strictly on the provided data components.
    Today's date is {today}.

    [VERIFIED FINANCIAL METRICS]
    {state['stock_data']}

    [RECENT NEWS & SENTIMENT]
    {state['web_research']}

    FORMATTING RULES (follow these strictly):
    - Use **bold** for every key number, verdict word, and standalone conclusion (e.g. "**overvalued**",
      "**$195.30**", "**Buy**", "**high risk**"). Do not bold entire sentences — only the specific
      important word or figure.
    - Use the currency shown in the verified metrics (for example ₹ for Indian stocks), never assume dollars.
    - Only call news "recent" if its date is within about 90 days of today's date. Older items (for example an
      earnings release from years ago) are background, not recent news.
    - If the news text disagrees with the VERIFIED FINANCIAL METRICS (for example a different price or daily
      change), trust the verified metrics and say the news summary may be outdated.
    - If news coverage is thin, say so in one plain sentence. Do not imply that nothing is happening, and do not
      invent events.
    - Keep paragraphs short: 2-4 sentences max. Break up long explanations into bullet points where
      it improves readability.
    - In the Executive Summary, the very first sentence must state the bottom-line takeaway in one
      bolded phrase (e.g. "**Bottom line: a moderate buy with near-term risk.**").
    - Use bullet points for lists of risks, strengths, or factors — never a single dense paragraph.

    First, output a single line in exactly this format (no other text on that line):
    SENTIMENT: BULLISH | NEUTRAL | BEARISH

    Then, on the following lines, format your full response beautifully with these exact Markdown headers:
    ## 📈 Executive Summary
    ## 🔍 Financial Health & Metrics Evaluation
    ## ⚠️ Key Risks & Current Sentiment
    ## 🎯 Final Verdict & Actionable Recommendation
    """

    response = llm_analyst.invoke([HumanMessage(content=analysis_prompt)])
    return {"messages": [AIMessage(content=response.content)]}


def route_after_initialize(state: AgentState):
    """Conditional routing: skip research/analysis if no valid ticker was found."""
    if not state.get("ticker"):
        return END
    return "research"

# =====================================================================
# 5. CONSTRUCT THE STATE GRAPH MACHINE
# =====================================================================
workflow = StateGraph(AgentState)

workflow.add_node("initialize", state_initializer)
workflow.add_node("research", researcher_node)
workflow.add_node("analyze", analyst_node)

workflow.add_edge(START, "initialize")
workflow.add_conditional_edges("initialize", route_after_initialize, {"research": "research", END: END})
workflow.add_edge("research", "analyze")
workflow.add_edge("analyze", END)

# Compile with an in-memory checkpointer so conversation state (ticker, history)
# persists across turns within the same thread_id.
# NOTE: MemorySaver resets on server restart and does not work across multiple
# server instances/replicas. For production, swap in SqliteSaver or PostgresSaver.
memory = MemorySaver()
financial_agent_app = workflow.compile(checkpointer=memory)
print("[AGENT LOG] Agent State Graph successfully compiled with Gemini 2.5 architecture!")