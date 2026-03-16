"""
EarthOne — Data Fetcher
Fetches real macro data from FRED (CSV endpoint, no API key)
and market data from Yahoo Finance (direct HTTP, no yfinance).
Implements time-based caching to avoid hammering sources.
"""

import io
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Cache store  { key: (timestamp, dataframe) }
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[float, pd.DataFrame]] = {}

MACRO_TTL = 86400   # 24 hours
MARKET_TTL = 3600   # 1 hour

def _get_cached(key: str, ttl: int):
    if key in _cache:
        ts, df = _cache[key]
        if time.time() - ts < ttl:
            return df
    return None

def _set_cached(key: str, df: pd.DataFrame):
    _cache[key] = (time.time(), df)

# ---------------------------------------------------------------------------
# FRED CSV fetcher
# ---------------------------------------------------------------------------
FRED_SERIES = {
    "WALCL":        "Fed Balance Sheet",
    "M2SL":         "M2 Money Supply",
    "BAMLH0A0HYM2": "HY Credit Spread",
    "DGS10":        "US 10Y Yield",
    "T10YIE":       "10Y Breakeven Inflation",
    "DTWEXBGS":     "Trade-Weighted Dollar",
}

def fetch_fred_series(series_id: str, years: int = 3) -> pd.DataFrame:
    """Fetch a single FRED series as a DataFrame with date index."""
    cached = _get_cached(f"fred_{series_id}", MACRO_TTL)
    if cached is not None:
        return cached

    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    url = (
        f"https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&cosd={start}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), parse_dates=["observation_date"])
        df = df.rename(columns={"observation_date": "date", series_id: "value"})
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])
        df = df.set_index("date").sort_index()
        _set_cached(f"fred_{series_id}", df)
        return df
    except Exception as e:
        print(f"[FRED] Error fetching {series_id}: {e}")
        return pd.DataFrame(columns=["value"])


def fetch_all_fred() -> dict[str, pd.DataFrame]:
    """Fetch all FRED series and return as a dict."""
    return {sid: fetch_fred_series(sid) for sid in FRED_SERIES}


# ---------------------------------------------------------------------------
# Yahoo Finance direct HTTP fetcher (no yfinance dependency)
# Works on cloud servers where yfinance is often blocked.
# ---------------------------------------------------------------------------
MARKET_TICKERS = {
    "SPY":     "S&P 500",
    "GC=F":    "Gold",
    "BTC-USD": "Bitcoin",
}

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}


_yf_session: requests.Session | None = None


def _get_yf_session() -> requests.Session:
    """Get a Yahoo Finance session with valid cookies."""
    global _yf_session
    if _yf_session is None:
        _yf_session = requests.Session()
        _yf_session.headers.update(_YF_HEADERS)
        # Get cookies from Yahoo
        try:
            _yf_session.get("https://fc.yahoo.com", timeout=10, allow_redirects=True)
        except Exception:
            pass  # We just need the cookies
    return _yf_session


def _fetch_yahoo_chart(ticker: str, range_str: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Fetch price data directly from Yahoo Finance chart API with retry."""
    import time as _time
    session = _get_yf_session()

    endpoints = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}",
    ]
    params = f"?range={range_str}&interval={interval}&includeAdjustedClose=true"

    for attempt in range(3):
        for base in endpoints:
            url = base + params
            try:
                resp = session.get(url, timeout=15)
                if resp.status_code == 429:
                    _time.sleep(2 * (attempt + 1))  # backoff
                    continue
                resp.raise_for_status()
                data = resp.json()

                result = data["chart"]["result"][0]
                timestamps = result["timestamp"]
                closes = result["indicators"]["quote"][0]["close"]

                df = pd.DataFrame({
                    "close": closes,
                }, index=pd.to_datetime(timestamps, unit="s", utc=True))

                df.index = df.index.tz_localize(None)
                df.index.name = "date"
                df = df.dropna(subset=["close"])
                df = df.sort_index()
                return df

            except Exception as e:
                print(f"[YF-HTTP] Attempt {attempt+1} error fetching {ticker} from {base}: {e}")
                _time.sleep(1)

    print(f"[YF-HTTP] All attempts failed for {ticker}")
    return pd.DataFrame(columns=["close"])


def fetch_market_data(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Fetch market price history from Yahoo Finance (direct HTTP)."""
    cached = _get_cached(f"yf_{ticker}", MARKET_TTL)
    if cached is not None:
        return cached

    # Map period strings to Yahoo range format
    range_map = {"1y": "1y", "2y": "2y", "5y": "5y", "6mo": "6mo", "1mo": "1mo"}
    range_str = range_map.get(period, "2y")

    df = _fetch_yahoo_chart(ticker, range_str=range_str)

    if not df.empty:
        _set_cached(f"yf_{ticker}", df)

    return df


def fetch_all_markets() -> dict[str, pd.DataFrame]:
    """Fetch all market tickers."""
    return {t: fetch_market_data(t) for t in MARKET_TICKERS}


# ---------------------------------------------------------------------------
# Dollar index (also from FRED for consistency)
# ---------------------------------------------------------------------------
def fetch_dollar_index() -> pd.DataFrame:
    return fetch_fred_series("DTWEXBGS")
