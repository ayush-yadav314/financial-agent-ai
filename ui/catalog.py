"""ui/catalog.py
Stock catalog for the landing screen.
Add or edit rows freely: (display name, Yahoo Finance ticker, short tag).

Only US listings (USD) and Indian NSE listings (INR) are included, because the
metric cards and 3D chart currently label prices as $ or ₹ only.
"""
import re

# One-click featured cards: (icon, name, tag, ticker)
FEATURED = [
    ("🟢", "NVIDIA", "US · AI chips", "NVDA"),
    ("🍎", "Apple", "US · Consumer tech", "AAPL"),
    ("🛢️", "Reliance", "India · NSE", "RELIANCE.NS"),
    ("💻", "Infosys", "India · IT services", "INFY.NS"),
    ("⚡", "Tesla", "US · Electric vehicles", "TSLA"),
    ("🏢", "TCS", "India · IT services", "TCS.NS"),
]

CATALOG = {
    "🇺🇸 US Tech": [
        ("Microsoft", "MSFT", "Software & cloud"),
        ("Alphabet", "GOOGL", "Search & AI"),
        ("Amazon", "AMZN", "E-commerce & cloud"),
        ("Meta", "META", "Social media"),
        ("Netflix", "NFLX", "Streaming"),
        ("AMD", "AMD", "Chips"),
        ("Intel", "INTC", "Chips"),
        ("Broadcom", "AVGO", "Semiconductors"),
        ("Oracle", "ORCL", "Enterprise software"),
        ("Salesforce", "CRM", "Cloud software"),
        ("Adobe", "ADBE", "Creative software"),
        ("Palantir", "PLTR", "Data analytics"),
    ],
    "🏦 US Blue Chips": [
        ("JPMorgan Chase", "JPM", "Banking"),
        ("Visa", "V", "Payments"),
        ("Mastercard", "MA", "Payments"),
        ("Berkshire Hathaway", "BRK-B", "Conglomerate"),
        ("Walmart", "WMT", "Retail"),
        ("Coca-Cola", "KO", "Beverages"),
        ("Disney", "DIS", "Media"),
        ("Nike", "NKE", "Apparel"),
        ("Boeing", "BA", "Aerospace"),
        ("Pfizer", "PFE", "Pharma"),
        ("Exxon Mobil", "XOM", "Energy"),
        ("Johnson & Johnson", "JNJ", "Healthcare"),
    ],
    "🇮🇳 India Large Caps": [
        ("HDFC Bank", "HDFCBANK.NS", "Banking"),
        ("ICICI Bank", "ICICIBANK.NS", "Banking"),
        ("State Bank of India", "SBIN.NS", "Banking"),
        ("Axis Bank", "AXISBANK.NS", "Banking"),
        ("Kotak Mahindra Bank", "KOTAKBANK.NS", "Banking"),
        ("Bharti Airtel", "BHARTIARTL.NS", "Telecom"),
        ("Larsen & Toubro", "LT.NS", "Infrastructure"),
        ("ITC", "ITC.NS", "FMCG"),
        ("Hindustan Unilever", "HINDUNILVR.NS", "FMCG"),
        ("Wipro", "WIPRO.NS", "IT services"),
        ("Tata Steel", "TATASTEEL.NS", "Metals"),
        ("Bajaj Finance", "BAJFINANCE.NS", "Finance"),
    ],
    "🌏 Global (USD ADRs)": [
        ("TSMC", "TSM", "Taiwan · chips"),
        ("Toyota", "TM", "Japan · autos"),
        ("Sony", "SONY", "Japan · electronics"),
        ("Alibaba", "BABA", "China · e-commerce"),
        ("Novo Nordisk", "NVO", "Denmark · pharma"),
        ("ASML", "ASML", "Netherlands · chip tools"),
        ("SAP", "SAP", "Germany · software"),
        ("Shell", "SHEL", "UK · energy"),
    ],
}


def make_query(name: str, ticker: str) -> str:
    """The ticker in brackets lets agent.py skip the Gemini extraction call."""
    return f"Analyse {name} ({ticker})"


def search_catalog(text: str, limit: int = 12) -> list:
    """Case-insensitive match on name or ticker. Returns [(name, ticker, tag), ...]."""
    q = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not q:
        return []
    hits = []
    for items in CATALOG.values():
        for name, ticker, tag in items:
            if q in name.lower() or q in ticker.lower():
                hits.append((name, ticker, tag))
    return hits[:limit]