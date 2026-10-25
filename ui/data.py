"""ui/data.py
Real company data for the report: profile, key metrics, news with source links,
and data-freshness timestamps.

Rules this module follows
- Everything comes from Yahoo Finance (via yfinance). Nothing is invented.
- A missing value is returned as None (profile) or [] (news). Callers show "N/A".
- Failures are never cached, and a failing ticker is not retried for 45 seconds,
  so a dead Yahoo endpoint can never stall the page.
- News from search results is only kept if it is clearly about the company
  (tagged with its ticker, or its name appears in the headline).

Public API
    get_profile(ticker)  -> dict ({} if unavailable)
    get_news(ticker, limit=6, company="") -> list[dict]  (title, publisher, url, published, summary)
    news_page_url(ticker) -> str   (Yahoo's own news page for the ticker, for "see more" links)
    currency(ticker)     -> "$" or "₹"
    fmt_cap(value, ticker), fmt_pct(frac), fmt_ratio(value), fmt_num(value)
    time_ago(epoch), stamp(epoch, tz_name="")
    h(text)              -> HTML-escaped text that is also safe from LaTeX "$" parsing
"""
import html
import numbers
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import streamlit as st
import yfinance as yf

_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&\-^]{0,14}$")


# ---------------------------------------------------------------------
# small safe-conversion helpers
# ---------------------------------------------------------------------
def _num(v):
    """float, or None for anything that isn't a real finite number."""
    if isinstance(v, bool) or not isinstance(v, numbers.Real):
        return None
    v = float(v)
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _text(v, maxlen=400):
    if not isinstance(v, str):
        return None
    v = re.sub(r"\s+", " ", v).strip()
    return v[:maxlen] if v else None


def _clean(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    return t if _TICKER_RE.match(t) else ""


def h(text) -> str:
    """Escape for HTML and keep '$' away from Streamlit's LaTeX parser."""
    return html.escape("" if text is None else str(text)).replace("$", "&#36;")


# ---------------------------------------------------------------------
# formatters (all return plain strings, "N/A" when the value is missing)
# ---------------------------------------------------------------------
def currency(ticker: str) -> str:
    return "₹" if (ticker or "").upper().endswith((".NS", ".BO")) else "$"


def fmt_cap(value, ticker: str) -> str:
    v = _num(value)
    if v is None or v <= 0:
        return "N/A"
    if currency(ticker) == "₹":
        cr = v / 1e7                              # 1 crore = 10 million
        return f"₹{cr / 1e5:,.2f} L Cr" if cr >= 1e5 else f"₹{cr:,.0f} Cr"
    for div, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if v >= div:
            return f"${v / div:,.2f}{suffix}"
    return f"${v:,.0f}"


def fmt_pct(frac, digits=1) -> str:
    """0.153 -> '15.3%'. Expects a fraction, which is how Yahoo reports margins and growth."""
    v = _num(frac)
    return "N/A" if v is None else f"{v * 100:.{digits}f}%"


def fmt_ratio(value, digits=2) -> str:
    v = _num(value)
    return "N/A" if v is None else f"{v:,.{digits}f}"


def fmt_num(value) -> str:
    v = _num(value)
    if v is None:
        return "N/A"
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v / div:,.2f}{suffix}"
    return f"{v:,.0f}"


def time_ago(ts) -> str:
    ts = _num(ts)
    if not ts:
        return ""
    d = max(0.0, time.time() - ts)
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    if d < 30 * 86400:
        return f"{int(d // 86400)} d ago"
    return datetime.fromtimestamp(ts).strftime("%d %b %Y")


def stamp(ts, tz_name: str = "") -> str:
    """'23 Oct 2026, 15:42 IST'. Uses the exchange's timezone when known, else the server's."""
    ts = _num(ts)
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    try:
        if tz_name:
            from zoneinfo import ZoneInfo
            dt = dt.astimezone(ZoneInfo(tz_name))
        else:
            dt = dt.astimezone()
    except Exception:                 # unknown zone, or no tz database on this machine
        dt = dt.astimezone()
    return dt.strftime("%d %b %Y, %H:%M %Z").strip()


# ---------------------------------------------------------------------
# company profile + key metrics
# ---------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def _fetch_profile(ticker: str) -> dict:
    info = yf.Ticker(ticker).info            # may raise; exceptions are never cached
    if not isinstance(info, dict) or not (info.get("longName") or info.get("shortName")):
        raise RuntimeError("Yahoo returned no company profile")
    return {
        "ticker": ticker,
        "name": _text(info.get("longName") or info.get("shortName"), 120),
        "sector": _text(info.get("sector"), 80),
        "industry": _text(info.get("industry"), 100),
        "country": _text(info.get("country"), 60),
        "city": _text(info.get("city"), 60),
        "website": _text(info.get("website"), 200),
        "employees": _num(info.get("fullTimeEmployees")),
        "summary": _text(info.get("longBusinessSummary"), 1500),
        "exchange": _text(info.get("fullExchangeName") or info.get("exchange"), 40),
        "currency": _text(info.get("currency"), 8),
        "tz": _text(info.get("exchangeTimezoneName"), 60),
        # market data
        "market_cap": _num(info.get("marketCap")),
        "volume": _num(info.get("volume") or info.get("regularMarketVolume")),
        "avg_volume": _num(info.get("averageVolume")),
        "price_time": _num(info.get("regularMarketTime")),
        # valuation + quality metrics
        "forward_pe": _num(info.get("forwardPE")),
        "price_to_book": _num(info.get("priceToBook")),
        "beta": _num(info.get("beta")),
        "profit_margin": _num(info.get("profitMargins")),
        "revenue_growth": _num(info.get("revenueGrowth")),
        "roe": _num(info.get("returnOnEquity")),
        # analyst view (Yahoo's aggregate, not ours)
        "target_mean": _num(info.get("targetMeanPrice")),
        "recommendation": _text(info.get("recommendationKey"), 30),
        "analysts": _num(info.get("numberOfAnalystOpinions")),
        # when WE fetched it (inside the cache, so cached data keeps its true age)
        "fetched_at": time.time(),
    }


def _in_backoff(kind: str, ticker: str) -> bool:
    return time.time() < st.session_state.get(f"_retry_{kind}", {}).get(ticker, 0)


def _start_backoff(kind: str, ticker: str, seconds: int = 45) -> None:
    st.session_state.setdefault(f"_retry_{kind}", {})[ticker] = time.time() + seconds


def get_profile(ticker: str) -> dict:
    """Company profile + metrics for the report, or {} if Yahoo can't provide it right now."""
    t = _clean(ticker)
    if not t or _in_backoff("profile", t):
        return {}
    try:
        return _fetch_profile(t)
    except Exception:
        _start_backoff("profile", t)
        return {}


# ---------------------------------------------------------------------
# news
# ---------------------------------------------------------------------
def _parse_time(raw):
    """Accepts an epoch number or an ISO-8601 string. Returns epoch seconds or None."""
    n = _num(raw)
    if n:
        return n / 1000 if n > 1e12 else n          # tolerate milliseconds
    if isinstance(raw, str) and raw.strip():
        try:
            return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _safe_url(url) -> str:
    if not isinstance(url, str):
        return ""
    url = url.strip()
    p = urlparse(url)
    return url if p.scheme in ("http", "https") and p.netloc else ""


def _normalise_news(item) -> dict:
    """Handle both yfinance news layouts (nested 'content' and the older flat one)."""
    if not isinstance(item, dict):
        return {}
    c = item.get("content") if isinstance(item.get("content"), dict) else item
    title = _text(c.get("title"), 220)
    if not title:
        return {}

    url = ""
    for key in ("canonicalUrl", "clickThroughUrl"):
        v = c.get(key)
        if isinstance(v, dict) and _safe_url(v.get("url")):
            url = _safe_url(v.get("url"))
            break
    url = url or _safe_url(c.get("link")) or _safe_url(c.get("url"))
    if not url:
        return {}                                   # no verifiable source link: don't show it

    provider = c.get("provider")
    publisher = (_text(provider.get("displayName"), 60) if isinstance(provider, dict) else None) \
        or _text(c.get("publisher"), 60)

    return {
        "title": title,
        "publisher": publisher,
        "url": url,
        "published": _parse_time(c.get("pubDate") or c.get("displayTime") or c.get("providerPublishTime")),
        "summary": _text(c.get("summary") or c.get("description"), 280),
    }


_GENERIC_WORDS = {
    "the", "inc", "inc.", "corp", "corp.", "corporation", "company", "co", "co.", "ltd", "ltd.",
    "limited", "plc", "holdings", "holding", "group", "ag", "sa", "nv", "llc", "&", "and",
}


def _keyword(company: str) -> str:
    """The most distinctive word of a company name ('HDFC Bank Limited' -> 'HDFC')."""
    for word in re.findall(r"[A-Za-z0-9&.]+", company or ""):
        w = word.strip(".")
        if len(w) >= 3 and w.lower() not in _GENERIC_WORDS:
            return w
    return ""


def _relevant(item, ticker: str, keyword: str) -> bool:
    """Keep a search-result story only if it is clearly about this company."""
    if not isinstance(item, dict):
        return False
    rel = item.get("relatedTickers")
    if isinstance(rel, list) and ticker in {str(x).upper() for x in rel}:
        return True
    c = item.get("content") if isinstance(item.get("content"), dict) else item
    title = c.get("title") if isinstance(c.get("title"), str) else ""
    return bool(keyword and re.search(r"\b" + re.escape(keyword) + r"\b", title, re.IGNORECASE))


def _search_news(query: str) -> list:
    try:
        s = yf.Search(query, max_results=1, news_count=10, timeout=6)
    except TypeError:                               # older yfinance without those arguments
        s = yf.Search(query, news_count=10)
    got = getattr(s, "news", None)
    if not isinstance(got, list):
        raise RuntimeError("Yahoo search returned no news list")
    return got


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_news(ticker: str, company: str) -> list:
    keyword = _keyword(company)
    raw, last_err = [], None

    # source 1: the ticker's own news feed (every item here is about the ticker already)
    try:
        got = yf.Ticker(ticker).news
        if isinstance(got, list):
            raw = list(got)
    except Exception as e:
        last_err = e

    # sources 2 + 3: Yahoo search by ticker, then by company name, filtered for relevance
    if not raw:
        queries = [ticker]
        if company and company.lower() != ticker.lower():
            queries.append(company)
        for q in queries:
            try:
                raw += [it for it in _search_news(q) if _relevant(it, ticker, keyword)]
            except Exception as e:
                last_err = e
            if raw:
                break

        kw_re = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE) if keyword else None
    out, seen = [], set()
    for item in raw:
        n = _normalise_news(item)
        key = (n.get("title") or "").lower()
        if n and key not in seen:
            seen.add(key)
            n["direct"] = bool(kw_re and kw_re.search(n["title"]))   # headline names the company
            out.append(n)
    # headlines that name the company come first, then newest first
    out.sort(key=lambda n: (not n["direct"], -(n["published"] or 0)))

    if not out and last_err is not None:
        raise last_err                              # a real failure: never cached
    return out                                      # a genuine "no news": fine to cache


def get_news(ticker: str, limit: int = 6, company: str = "") -> list:
    """Recent headlines with publisher and link. [] when none are available.
    Pass the company name (from get_profile) to improve matches for non-US listings."""
    t = _clean(ticker)
    if not t or _in_backoff("news", t):
        return []
    try:
        return _fetch_news(t, (company or "").strip()[:120])[:limit]
    except Exception:
        _start_backoff("news", t)
        return []


def news_page_url(ticker: str) -> str:
    """Yahoo Finance's own news page for the ticker (for a 'see more on Yahoo' link)."""
    t = _clean(ticker)
    return f"https://finance.yahoo.com/quote/{quote(t)}/news" if t else ""