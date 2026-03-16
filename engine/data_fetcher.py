"""
EarthOne — Data Fetcher
Fetches real macro data from FRED (CSV endpoint, no API key)
and market data from Yahoo Finance (yfinance).
Implements time-based caching to avoid hammering sources.
"""

import io
import time
import requests
import pandas as pd
import yfinance as yf
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
# Yahoo Finance fetcher
# ---------------------------------------------------------------------------
MARKET_TICKERS = {
    "SPY":     "S&P 500",
    "GC=F":    "Gold",
    "BTC-USD": "Bitcoin",
}

def fetch_market_data(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Fetch market price history from Yahoo Finance."""
    cached = _get_cached(f"yf_{ticker}", MARKET_TTL)
    if cached is not None:
        return cached

    try:
        data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if data.empty:
            return pd.DataFrame(columns=["close"])
        df = data[["Close"]].copy()
        df.columns = ["close"]
        # Flatten MultiIndex if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        df = df.sort_index()
        _set_cached(f"yf_{ticker}", df)
        return df
    except Exception as e:
        print(f"[YF] Error fetching {ticker}: {e}")
        return pd.DataFrame(columns=["close"])


def fetch_all_markets() -> dict[str, pd.DataFrame]:
    """Fetch all market tickers."""
    return {t: fetch_market_data(t) for t in MARKET_TICKERS}


# ---------------------------------------------------------------------------
# Dollar index (also from FRED for consistency)
# ---------------------------------------------------------------------------
def fetch_dollar_index() -> pd.DataFrame:
    return fetch_fred_series("DTWEXBGS")
