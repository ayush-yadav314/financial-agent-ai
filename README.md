# Agentic Finance Analyst

An AI-powered stock research terminal. Ask about a company in plain English and a three-agent
workflow (built with LangGraph) identifies the ticker, gathers live market data and news, and
writes a plain-English research report with a Bullish / Neutral / Bearish verdict.

> **Educational research only. This is not financial advice.** AI output can be wrong, and market
> data can be delayed or incomplete.

## Features

- **Multi-agent workflow**: ticker identification, research (Yahoo Finance and Tavily in parallel), then AI analysis with Gemini
- **Compact report**: summary card with price, verdict gauge and key stats, followed by collapsible sections (AI report, fundamentals, signals and risks, scorecard, company overview, news, sources)
- **Smart search** with company logos, names, tickers and exchanges (US and Indian listings)
- **Charts**: line, candlestick and interactive 3D views, with 1M / 3M / 6M / 1Y ranges and volume
- **Explainable scorecard**: seven transparent rule-based checks; missing data is shown as N/A, never counted as zero
- **Stock comparison**: side by side, with a rebased performance chart, a metrics table and scorecards
- **Follow-up questions** answered only from the report's saved data (up to 5 per report)
- **Watchlist and recent research** with logos and daily price changes, saved between sessions
- **Futuristic UI**: animated 3D market globe, glass cards and a market ticker tape, with a Performance mode and support for reduced-motion settings
- **Data honesty**: freshness timestamps, "N/A" for missing data, and source links for news

## How it works

```
You ask  ->  Identify ticker  ->  Research  ->  Analyze  ->  Report
              (lookup table      (Yahoo Finance   (Gemini)     (summary, charts,
               or Gemini)         + Tavily +                    scorecard, news)
                                  Yahoo headlines)
```

## Quick start

**Requirements:** Python 3.10 or newer, a [Google AI Studio](https://aistudio.google.com) API key
and a [Tavily](https://tavily.com) API key.

```bash
# 1. get the code and enter the folder
git clone https://github.com/ayush-yadav314/financial-agent-ai.git
cd financial-agent-ai

# 2. create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 3. install dependencies
pip install -r requirements.txt

# 4. add your keys: copy .env.example to .env, then fill in the values
#    GOOGLE_API_KEY=...
#    TAVILY_API_KEY=...

# 5. run
streamlit run app.py
```

Never commit your `.env` file. It is listed in `.gitignore`.

## Configuration

| Setting | What it does |
|---|---|
| `GOOGLE_API_KEY` | Gemini API key (required) |
| `TAVILY_API_KEY` | Tavily news search key (required) |
| `FIN_PERSIST=0` | Turns off saving the watchlist and recent research (recommended for public deployments) |
| `FIN_DATA_DIR` | Folder for the saved state (default: `data/`) |
| Sidebar: Performance mode | Turns off the 3D globe, blur effects and typing animation |

## Project structure

```
app.py              main Streamlit app
agent.py            LangGraph agents: initialize -> research -> analyze
check_ui.py         checks that app.py and the ui/ modules match (python check_ui.py)
ui/
  theme.py          fonts, colors, glass styling
  background.py     animated 3D globe (Three.js)
  report.py         summary card and report sections
  chart3d.py        interactive 3D chart
  search.py         smart search          logos.py      company logos
  compare.py        stock comparison      scorecard.py  rule-based scorecard
  followup.py       follow-up questions   sidebar.py    watchlist, history
  data.py           profile and news      prices.py     price history
  store.py          saved state           polish.py     performance mode, mobile
  ...
```

## Data sources and limitations

- Market data and news come from Yahoo Finance via the unofficial `yfinance` library. It can be rate-limited or return incomplete data, and the app shows N/A or a notice instead of guessing.
- News search uses Tavily, and the AI analysis uses Gemini. Free-tier quotas apply, and each analysis and each follow-up question uses AI requests.
- Company logos are fetched from Google's favicon service, with initials as a fallback.
- Search and price labels support US listings and Indian NSE/BSE listings ($ and ₹).
- The scorecard and signals use generic thresholds that ignore industry norms (banks and software companies are valued differently).
- The watchlist file is shared by everyone using the same server, so this app is built for single-user use. For a public deployment, set `FIN_PERSIST=0`.

## Tech stack

Python, Streamlit, LangGraph and LangChain, Google Gemini, Tavily, yfinance, Plotly, Three.js

## License

Add a license of your choice (for example MIT) before sharing the project widely.