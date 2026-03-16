"""
EarthOne — Data Fetcher
Fetches real macro data from FRED (CSV endpoint, no API key)
and market data from Stooq (CSV endpoint, no API key).
Both sources are public, reliable, and work on cloud servers.
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

def fetch_fred_series(series_id: str, years: int = 25) -> pd.DataFrame:
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
        resp = requests.get(url, timeout=30)
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
# Stooq CSV fetcher — reliable, no API key, works on cloud servers
# ---------------------------------------------------------------------------
MARKET_TICKERS = {
    "spy.us":  "S&P 500",
    "xauusd":  "Gold",
    "btcusd":  "Bitcoin",
}

_STOOQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}


def _fetch_stooq(ticker: str, years: int = 25) -> pd.DataFrame:
    """Fetch historical price data from Stooq CSV endpoint."""
    start = (datetime.now() - timedelta(days=years * 365)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={ticker}&d1={start}&d2={end}&i=d"

    try:
        resp = requests.get(url, headers=_STOOQ_HEADERS, timeout=30)
        resp.raise_for_status()

        text = resp.text.strip()
        if not text or "No data" in text or len(text) < 50:
            print(f"[Stooq] No data for {ticker}")
            return pd.DataFrame(columns=["close"])

        df = pd.read_csv(io.StringIO(text), parse_dates=["Date"])
        df = df.rename(columns={"Date": "date", "Close": "close"})
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["close"])
        df = df.set_index("date").sort_index()
        df = df[["close"]]
        return df

    except Exception as e:
        print(f"[Stooq] Error fetching {ticker}: {e}")
        return pd.DataFrame(columns=["close"])


def fetch_market_data(ticker: str, period: str = "25y") -> pd.DataFrame:
    """Fetch market price history from Stooq."""
    cached = _get_cached(f"stooq_{ticker}", MARKET_TTL)
    if cached is not None:
        return cached

    years = {"1y": 1, "2y": 2, "5y": 5, "10y": 10, "25y": 25, "6mo": 1, "1mo": 1}.get(period, 25)
    df = _fetch_stooq(ticker, years=years)

    if not df.empty:
        _set_cached(f"stooq_{ticker}", df)

    return df


def fetch_all_markets() -> dict[str, pd.DataFrame]:
    """Fetch all market tickers."""
    return {t: fetch_market_data(t) for t in MARKET_TICKERS}


# ---------------------------------------------------------------------------
# Dollar index (from FRED for consistency)
# ---------------------------------------------------------------------------
def fetch_dollar_index() -> pd.DataFrame:
    return fetch_fred_series("DTWEXBGS")
