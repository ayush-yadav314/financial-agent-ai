import os
import yfinance as yf
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.tools import TavilyAnswer

# Explicitly pull configurations from your local .env file
load_dotenv()

# =====================================================================
# 1. DEFINE THE SHARED AGENT STATE
# =====================================================================
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    ticker: str
    stock_data: str
    web_research: str

# =====================================================================
# 2. DEFINE THE PROGRAMMATIC TOOLS
# =====================================================================
def fetch_stock_metrics(ticker: str) -> str:
    """Tool: Fetches clean numerical fundamentals from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return f"""
        Company Name: {info.get('longName', 'N/A')}
        Current Market Price: ${info.get('currentPrice', 'N/A')}
        P/E Ratio: {info.get('trailingPE', 'N/A')}
        52-Week High: ${info.get('fiftyTwoWeekHigh', 'N/A')}
        52-Week Low: ${info.get('fiftyTwoWeekLow', 'N/A')}
        Profit Margins: {info.get('profitMargins', 'N/A')}
        """
    except Exception as e:
        return f"Could not gather market metrics: {str(e)}"

def search_market_news(ticker: str) -> str:
    """Tool: Fetches web articles and sentiment trends via Tavily."""
    try:
        search = TavilyAnswer()
        return search.run(f"Latest stock market news and financial investor sentiment for ticker: {ticker}")
    except Exception as e:
        return f"Could not gather web research: {str(e)}"

# =====================================================================
# 3. DEFINE THE NODES (Updated for gemini-2.5-flash & explicit key mapping)
# =====================================================================
def state_initializer(state: AgentState):
    """Agent 1: Extracts clean ticker symbol from user statements."""
    # Using gemini-2.5-flash which correctly processes modern AQ. tokens
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0
    )
    
    prompt = f"""
    Analyze the user conversation below. Extract the single primary public stock ticker symbol mentioned.
    Return ONLY the raw ticker symbol in uppercase (e.g., AAPL, TSLA, INFY.NS). Do not add any punctuation or extra words.
    
    Conversation History: {state['messages']}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    extracted_ticker = response.content.strip()
    print(f"[AGENT LOG] Extracted Ticker: {extracted_ticker}")
    return {"ticker": extracted_ticker}


def researcher_node(state: AgentState):
    """Agent 2: Gathers metrics and search parameters concurrently."""
    print(f"[AGENT LOG] Researcher Node running tools for: {state['ticker']}")
    metrics = fetch_stock_metrics(state["ticker"])
    news = search_market_news(state["ticker"])
    return {"stock_data": metrics, "web_research": news}


def analyst_node(state: AgentState):
    """Agent 3: Compiles complete analytical report outcomes."""
    print(f"[AGENT LOG] Analyst Node compiling final report...")
    # Updated to gemini-2.5-flash with explicit token mapping
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.2
    )
    
    analysis_prompt = f"""
    You are an elite financial research analyst. Synthesize a comprehensive investment report based strictly on the provided data components.
    
    [VERIFIED FINANCIAL METRICS]
    {state['stock_data']}
    
    [RECENT NEWS & SENTIMENT]
    {state['web_research']}
    
    Format your response beautifully with these exact Markdown headers:
    ## 📈 Executive Summary
    ## 🔍 Financial Health & Metrics Evaluation
    ## ⚠️ Key Risks & Current Sentiment
    ## 🎯 Final Verdict & Actionable Recommendation
    """
    
    response = llm.invoke([HumanMessage(content=analysis_prompt)])
    return {"messages": [AIMessage(content=response.content)]}

# =====================================================================
# 4. CONSTRUCT THE STATE GRAPH MACHINE
# =====================================================================
workflow = StateGraph(AgentState)

# Wire the processing nodes
workflow.add_node("initialize", state_initializer)
workflow.add_node("research", researcher_node)
workflow.add_node("analyze", analyst_node)

# Map step sequences
workflow.add_edge(START, "initialize")
workflow.add_edge("initialize", "research")
workflow.add_edge("research", "analyze")
workflow.add_edge("analyze", END)

# Compile into executable instance
financial_agent_app = workflow.compile()
print("[AGENT LOG] Agent State Graph successfully compiled with Gemini 2.5 architecture!")