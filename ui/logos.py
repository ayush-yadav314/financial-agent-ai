"""ui/logos.py
Company logos with graceful fallbacks.

How it works
1. Ticker -> website domain, from a built-in table (US + Indian large caps),
   or from a `website` value you pass in (e.g. Yahoo Finance's company website).
2. The logo image is downloaded on the SERVER (Google's favicon service, no API key),
   cached in memory for 24 hours, and embedded in the page as a data URI.
   Because the server does the download, a failed lookup is detected here and we
   show a clean fallback; the browser can never show a broken-image icon.
3. No domain, or download failed -> a gradient monogram avatar (e.g. "NV").

Public API
    logo_html(ticker, name="", size=36, website="")            -> str
    logo_row_html(ticker, name, sub="", size=36, website="")   -> str  (logo + name + ticker)
    prefetch_logos(tickers)                                    warm the cache in parallel
    domain_for(ticker, website="")                             -> str
"""
import base64
import html
import re
import threading
import time
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse

# ---------------------------------------------------------------------
# Ticker -> website domain. Add or fix rows freely.
# Typed from general knowledge and not checked one by one: if a logo is wrong
# or missing, correct the domain here (the app falls back to a monogram).
# ---------------------------------------------------------------------
DOMAINS = {
    # ---- US tech ----
    "NVDA": "nvidia.com", "AAPL": "apple.com", "MSFT": "microsoft.com",
    "GOOGL": "google.com", "GOOG": "google.com", "AMZN": "amazon.com",
    "META": "meta.com", "TSLA": "tesla.com", "NFLX": "netflix.com",
    "AMD": "amd.com", "INTC": "intel.com", "AVGO": "broadcom.com",
    "ORCL": "oracle.com", "CRM": "salesforce.com", "ADBE": "adobe.com",
    "PLTR": "palantir.com", "QCOM": "qualcomm.com", "CSCO": "cisco.com",
    "IBM": "ibm.com", "UBER": "uber.com", "PYPL": "paypal.com",
    "SHOP": "shopify.com", "SNOW": "snowflake.com", "CRWD": "crowdstrike.com",
    "MU": "micron.com", "ARM": "arm.com", "DELL": "dell.com",
    "SPOT": "spotify.com", "ABNB": "airbnb.com", "COIN": "coinbase.com",
    # ---- US blue chips ----
    "JPM": "jpmorganchase.com", "V": "visa.com", "MA": "mastercard.com",
    "BRK-B": "berkshirehathaway.com", "WMT": "walmart.com", "KO": "coca-colacompany.com",
    "DIS": "disney.com", "NKE": "nike.com", "BA": "boeing.com",
    "PFE": "pfizer.com", "XOM": "exxonmobil.com", "JNJ": "jnj.com",
    "COST": "costco.com", "HD": "homedepot.com", "MCD": "mcdonalds.com",
    "SBUX": "starbucks.com", "PEP": "pepsico.com", "PG": "pg.com",
    "UNH": "unitedhealthgroup.com", "LLY": "lilly.com", "ABBV": "abbvie.com",
    "BAC": "bankofamerica.com", "GS": "goldmansachs.com", "MS": "morganstanley.com",
    "C": "citigroup.com", "WFC": "wellsfargo.com", "T": "att.com",
    "VZ": "verizon.com", "CVX": "chevron.com", "F": "ford.com", "GM": "gm.com",
    # ---- Global ADRs ----
    "TSM": "tsmc.com", "TM": "toyota.com", "SONY": "sony.com",
    "BABA": "alibabagroup.com", "NVO": "novonordisk.com", "ASML": "asml.com",
    "SAP": "sap.com", "SHEL": "shell.com",
    # ---- India (NSE; .BO listings reuse these) ----
    "RELIANCE.NS": "ril.com", "TCS.NS": "tata.com", "INFY.NS": "infosys.com",
    "HDFCBANK.NS": "hdfcbank.com", "ICICIBANK.NS": "icicibank.com",
    "SBIN.NS": "sbi.co.in", "AXISBANK.NS": "axisbank.com",
    "KOTAKBANK.NS": "kotak.com", "BHARTIARTL.NS": "airtel.in",
    "LT.NS": "larsentoubro.com", "ITC.NS": "itcportal.com",
    "HINDUNILVR.NS": "hul.co.in", "WIPRO.NS": "wipro.com",
    "TATASTEEL.NS": "tatasteel.com", "BAJFINANCE.NS": "bajajfinance.in",
    "TMPV.NS": "tatamotors.com", "TMCV.NS": "tatamotors.com",
    "TATAMOTORS.NS": "tatamotors.com", "TATAPOWER.NS": "tatapower.com",
    "ADANIENT.NS": "adani.com", "MARUTI.NS": "marutisuzuki.com",
    "SUNPHARMA.NS": "sunpharma.com", "ASIANPAINT.NS": "asianpaints.com",
    "TITAN.NS": "titancompany.in", "NESTLEIND.NS": "nestle.in",
    "ULTRACEMCO.NS": "ultratechcement.com", "ONGC.NS": "ongcindia.com",
    "NTPC.NS": "ntpc.co.in", "POWERGRID.NS": "powergrid.in",
    "COALINDIA.NS": "coalindia.in", "HCLTECH.NS": "hcltech.com",
    "TECHM.NS": "techmahindra.com", "M&M.NS": "mahindra.com",
    "BAJAJ-AUTO.NS": "bajajauto.com", "EICHERMOT.NS": "eichermotors.com",
}

# Monogram gradients, all in the app's cyan / violet / emerald family
_GRADIENTS = [
    ("#22D3EE", "#3B82F6"),
    ("#8B5CF6", "#6366F1"),
    ("#10B981", "#22D3EE"),
    ("#6366F1", "#22D3EE"),
    ("#8B5CF6", "#22D3EE"),
    ("#0EA5E9", "#8B5CF6"),
]

# ---------------------------------------------------------------------
# In-memory cache (shared by every session in this server process)
# ---------------------------------------------------------------------
_CACHE = {}      # domain -> (timestamp, data URI)
_FAILED = {}     # domain -> timestamp of the last failed download
_LOCK = threading.Lock()
_TTL = 24 * 3600      # keep a good logo for 24 hours
_RETRY = 600          # after a failure, don't retry for 10 minutes
_MAX_ENTRIES = 400


def _norm(ticker: str) -> str:
    return (ticker or "").strip().upper()


def _domain_from_url(url: str) -> str:
    """'https://www.apple.com/in/' -> 'apple.com'. Returns '' if it doesn't look like a domain."""
    if not url:
        return ""
    url = str(url).strip()
    if "://" not in url:
        url = "http://" + url
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host) else ""


def domain_for(ticker: str, website: str = "") -> str:
    """Best-known website domain for a ticker ('' if unknown)."""
    t = _norm(ticker)
    if t in DOMAINS:
        return DOMAINS[t]
    if t.endswith(".BO") and (t[:-3] + ".NS") in DOMAINS:
        return DOMAINS[t[:-3] + ".NS"]
    return _domain_from_url(website)


def _download(domain: str) -> str:
    """Download a logo and return it as a data URI, or '' on any failure."""
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain or ""):
        return ""
    url = f"https://www.google.com/s2/favicons?domain={quote(domain)}&sz=128"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            ctype = resp.headers.get_content_type() or ""
            data = resp.read(250_000)
    except Exception:
        return ""          # includes 404s, timeouts, offline, blocked network
    if not ctype.startswith("image/") or len(data) < 120:
        return ""
    return f"data:{ctype};base64," + base64.b64encode(data).decode("ascii")


def _logo_uri(domain: str) -> str:
    """Cached lookup. Returns '' when there is no usable logo."""
    if not domain:
        return ""
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(domain)
        if hit and now - hit[0] < _TTL:
            return hit[1]
        failed = _FAILED.get(domain)
        if failed and now - failed < _RETRY:
            return ""
    uri = _download(domain)
    with _LOCK:
        if uri:
            if len(_CACHE) >= _MAX_ENTRIES:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[domain] = (time.time(), uri)
            _FAILED.pop(domain, None)
        else:
            _FAILED[domain] = time.time()
    return uri


def prefetch_logos(tickers) -> None:
    """Download any logos not cached yet, in parallel. Call this once before
    rendering a grid or list, so the first view doesn't download them one by one."""
    domains = {d for d in (domain_for(t) for t in tickers) if d}
    with _LOCK:
        now = time.time()
        todo = [d for d in domains if not (d in _CACHE and now - _CACHE[d][0] < _TTL)]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_logo_uri, todo))


def _initials(ticker: str, name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    if len(words) >= 2:
        text = words[0][0] + words[1][0]
    elif words:
        text = words[0][:2]
    else:
        text = re.sub(r"[^A-Z0-9]", "", _norm(ticker))[:2] or "?"
    return text.upper()


def logo_html(ticker: str, name: str = "", size: int = 36, website: str = "") -> str:
    """Inline HTML for a square company logo. Falls back to a gradient monogram.
    Uses inline styles only, so it works anywhere st.markdown(..., unsafe_allow_html=True) does."""
    t = _norm(ticker)
    uri = _logo_uri(domain_for(t, website))
    radius = max(8, round(size * 0.28))
    alt = html.escape(f"{name or t} logo", quote=True)

    if uri:
        pad = max(3, round(size * 0.12))
        return (
            f'<span style="display:inline-flex;flex:0 0 {size}px;width:{size}px;height:{size}px;'
            f'border-radius:{radius}px;background:#fff;padding:{pad}px;box-sizing:border-box;'
            f'box-shadow:0 0 0 1px rgba(255,255,255,.14),0 6px 16px -8px rgba(0,0,0,.8);'
            f'vertical-align:middle;">'
            f'<img src="{uri}" alt="{alt}" '
            f'style="width:100%;height:100%;object-fit:contain;display:block;"></span>'
        )

    c1, c2 = _GRADIENTS[zlib.crc32(t.encode("utf-8")) % len(_GRADIENTS)]
    font = max(10, round(size * 0.38))
    return (
        f'<span role="img" aria-label="{alt}" style="display:inline-flex;flex:0 0 {size}px;'
        f'width:{size}px;height:{size}px;border-radius:{radius}px;align-items:center;'
        f'justify-content:center;background:linear-gradient(135deg,{c1},{c2});color:#fff;'
        f'font-family:var(--font-display,sans-serif);font-weight:700;font-size:{font}px;'
        f'letter-spacing:.02em;box-shadow:0 0 0 1px rgba(255,255,255,.14),'
        f'0 6px 16px -8px rgba(0,0,0,.8);vertical-align:middle;">'
        f'{html.escape(_initials(t, name))}</span>'
    )


def logo_row_html(ticker: str, name: str, sub: str = "", size: int = 36, website: str = "") -> str:
    """Logo + company name + ticker (and an optional small label such as the exchange)."""
    t = _norm(ticker)
    sub_part = f" · {html.escape(sub)}" if sub else ""
    return (
        '<div style="display:flex;align-items:center;gap:.7rem;min-width:0;">'
        f'{logo_html(t, name, size, website)}'
        '<div style="min-width:0;line-height:1.25;">'
        '<div style="font-weight:600;color:var(--text,#E6EAF2);white-space:nowrap;'
        f'overflow:hidden;text-overflow:ellipsis;">{html.escape(name or t)}</div>'
        '<div style="font-size:.78rem;color:var(--muted,#8B93A7);letter-spacing:.04em;">'
        f'{html.escape(t)}{sub_part}</div>'
        '</div></div>'
    )