import os
import re
from concurrent.futures import ThreadPoolExecutor

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
KNOWN_TICKERS = {
    "apple": "AAPL", "tesla": "TSLA", "nvidia": "NVDA", "microsoft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "amazon": "AMZN", "meta": "META",
    "facebook": "META", "netflix": "NFLX", "amd": "AMD", "intel": "INTC",
    "tata motors": "TATAMOTORS.NS", "tata steel": "TATASTEEL.NS",
    "tata consultancy": "TCS.NS", "tcs": "TCS.NS", "tata power": "TATAPOWER.NS",
    "reliance": "RELIANCE.NS", "infosys": "INFY.NS", "hdfc bank": "HDFCBANK.NS",
    "icici bank": "ICICIBANK.NS", "wipro": "WIPRO.NS", "adani enterprises": "ADANIENT.NS",
    "state bank of india": "SBIN.NS", "sbi": "SBIN.NS",
}


def lookup_known_ticker(text: str):
    """Checks the user's message against a static company->ticker map before
    spending an LLM call on extraction. Returns None if no confident match."""
    text_lower = text.lower()
    for name, ticker in KNOWN_TICKERS.items():
        if name in text_lower:
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
    Returns a tuple: (resolved_ticker_or_original, formatted_metrics_string)."""
    candidates = [ticker]
    if "." not in ticker:
        candidates += [f"{ticker}.NS", f"{ticker}.BO"]

    last_error = None
    for candidate in candidates:
        try:
            stock = yf.Ticker(candidate)
            info = stock.info
            # A resolved ticker should have at least a name or a price; otherwise treat as a miss
            if not info.get("longName") and not info.get("currentPrice"):
                continue
            margins = info.get('profitMargins', None)
            margins_display = f"{margins * 100:.2f}%" if isinstance(margins, (int, float)) else "N/A"
            formatted = f"""
        Company Name: {info.get('longName', 'N/A')}
        Ticker Used: {candidate}
        Current Market Price: ${info.get('currentPrice', 'N/A')}
        P/E Ratio: {info.get('trailingPE', 'N/A')}
        52-Week High: ${info.get('fiftyTwoWeekHigh', 'N/A')}
        52-Week Low: ${info.get('fiftyTwoWeekLow', 'N/A')}
        Profit Margins: {margins_display}
        """
            return candidate, formatted
        except Exception as e:
            last_error = e
            continue

    return ticker, f"Could not gather market metrics for '{ticker}' (tried: {', '.join(candidates)}). Last error: {last_error}"

def search_market_news(ticker: str) -> str:
    """Tool: Fetches web articles and sentiment trends via Tavily."""
    try:
        search = TavilyAnswer()
        return search.run(f"Latest stock market news and financial investor sentiment for ticker: {ticker}")
    except Exception as e:
        return f"Could not gather web research: {str(e)}"

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
      group (e.g. "Tata" -> Tata Motors -> TATAMOTORS.NS; "Reliance" -> RELIANCE.NS). Do not invent a
      ticker that does not exist.
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
    with ThreadPoolExecutor(max_workers=2) as executor:
        metrics_future = executor.submit(fetch_stock_metrics, ticker)
        news_future = executor.submit(search_market_news, ticker)
        resolved_ticker, metrics = metrics_future.result()
        news = news_future.result()
    # If a suffix fallback (.NS/.BO) resolved the ticker, propagate that back into state
    # so downstream chart/metric rendering in app.py uses the correct resolvable ticker.
    return {"stock_data": metrics, "web_research": news, "ticker": resolved_ticker}


def analyst_node(state: AgentState):
    """Agent 3: Compiles complete analytical report outcomes."""
    print(f"[AGENT LOG] Analyst Node compiling final report...")

    analysis_prompt = f"""
    You are an elite financial research analyst who writes clear, easy-to-understand reports for
    everyday retail investors — not other analysts. Avoid unexplained jargon; if you must use a
    financial term (e.g. P/E ratio, market cap), briefly explain what it means in plain language.

    Synthesize a comprehensive investment report based strictly on the provided data components.

    [VERIFIED FINANCIAL METRICS]
    {state['stock_data']}

    [RECENT NEWS & SENTIMENT]
    {state['web_research']}

    FORMATTING RULES (follow these strictly):
    - Use **bold** for every key number, verdict word, and standalone conclusion (e.g. "**overvalued**",
      "**$195.30**", "**Buy**", "**high risk**"). Do not bold entire sentences — only the specific
      important word or figure.
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
