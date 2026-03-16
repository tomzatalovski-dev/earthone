"""
EarthOne — ELX Engine
Computes the Earth Liquidity Index from real FRED + market data.

Formula:
  ELX = 0.40 * liquidity + 0.25 * credit(inv) + 0.20 * real_yield(inv)
      + 0.10 * dollar(inv) + 0.05 * market_beta

Each component is a z-score, then the composite is scaled to [-100, +100].

Data frequencies:
  WALCL      — weekly  (~52/yr)
  M2SL       — monthly (~12/yr)
  BAMLH0A0HYM2 — daily (~252/yr)
  DGS10, T10YIE — daily
  DTWEXBGS   — weekly/business-daily (~252/yr)
  SPY        — daily
"""

import time
from datetime import datetime
import numpy as np
import pandas as pd
from .data_fetcher import fetch_fred_series, fetch_market_data


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_elx_cache: dict[str, tuple[float, object]] = {}
ELX_TTL = 3600


def _zscore_full(series: pd.Series) -> pd.Series:
    """Full-sample z-score (uses all available history as the reference)."""
    mean = series.mean()
    std = series.std()
    if std == 0 or np.isnan(std):
        return series * 0
    return (series - mean) / std


def _scale(z: float) -> int:
    """Scale a z-score to [-100, +100], clamped at ±3."""
    clamped = max(-3.0, min(3.0, z))
    return round(clamped / 3.0 * 100)


# ---------------------------------------------------------------------------
# Component calculators
# ---------------------------------------------------------------------------

def _compute_liquidity() -> tuple[pd.Series, float, str]:
    """Global Liquidity: YoY% of WALCL (weekly) and M2SL (monthly), z-scored."""
    walcl = fetch_fred_series("WALCL", years=5)
    m2 = fetch_fred_series("M2SL", years=5)

    z_series_list = []

    # WALCL: weekly → YoY = 52-period pct_change
    if not walcl.empty and len(walcl) > 52:
        w_yoy = walcl["value"].pct_change(periods=52).dropna()
        z_w = _zscore_full(w_yoy)
        z_series_list.append(z_w)

    # M2SL: monthly → YoY = 12-period pct_change
    if not m2.empty and len(m2) > 12:
        m_yoy = m2["value"].pct_change(periods=12).dropna()
        z_m = _zscore_full(m_yoy)
        z_series_list.append(z_m)

    if not z_series_list:
        return pd.Series(dtype=float), 0.0, "N/A"

    # Average the available z-scores
    if len(z_series_list) == 2:
        combined = pd.DataFrame({"a": z_series_list[0], "b": z_series_list[1]})
        combined = combined.ffill().dropna()
        z_avg = (combined["a"] + combined["b"]) / 2
    else:
        z_avg = z_series_list[0]

    latest = float(z_avg.iloc[-1]) if len(z_avg) > 0 else 0.0
    direction = "Expansionary" if latest > 0 else "Contractionary"
    return z_avg, latest, direction


def _compute_credit() -> tuple[pd.Series, float, str]:
    """Credit Conditions: inverted z-score of HY spread (daily)."""
    hy = fetch_fred_series("BAMLH0A0HYM2", years=5)
    if hy.empty or len(hy) < 30:
        return pd.Series(dtype=float), 0.0, "N/A"

    z = _zscore_full(hy["value"])
    z_inv = -z  # wider spread = tighter = negative for liquidity
    z_inv = z_inv.dropna()

    latest = float(z_inv.iloc[-1]) if len(z_inv) > 0 else 0.0
    direction = "Expansionary" if latest > 0 else "Contractionary"
    return z_inv, latest, direction


def _compute_real_yields() -> tuple[pd.Series, float, str]:
    """Real Yields: inverted z-score of (10Y yield - breakeven inflation)."""
    dgs10 = fetch_fred_series("DGS10", years=5)
    t10yie = fetch_fred_series("T10YIE", years=5)

    if dgs10.empty or t10yie.empty:
        return pd.Series(dtype=float), 0.0, "N/A"

    combined = pd.DataFrame({"y": dgs10["value"], "i": t10yie["value"]}).dropna()
    if len(combined) < 30:
        return pd.Series(dtype=float), 0.0, "N/A"

    real_yield = combined["y"] - combined["i"]
    z = _zscore_full(real_yield)
    z_inv = -z  # higher real yield = tighter = negative
    z_inv = z_inv.dropna()

    latest = float(z_inv.iloc[-1]) if len(z_inv) > 0 else 0.0
    direction = "Expansionary" if latest > 0 else "Contractionary"
    return z_inv, latest, direction


def _compute_dollar() -> tuple[pd.Series, float, str]:
    """Dollar Strength: inverted z-score of trade-weighted dollar."""
    dxy = fetch_fred_series("DTWEXBGS", years=5)
    if dxy.empty or len(dxy) < 30:
        return pd.Series(dtype=float), 0.0, "N/A"

    z = _zscore_full(dxy["value"])
    z_inv = -z  # stronger dollar = tighter
    z_inv = z_inv.dropna()

    latest = float(z_inv.iloc[-1]) if len(z_inv) > 0 else 0.0
    direction = "Expansionary" if latest > 0 else "Contractionary"
    return z_inv, latest, direction


def _compute_market_beta() -> tuple[pd.Series, float, str]:
    """Market Beta: z-score of SPY 6-month return (daily, 126 periods)."""
    spy = fetch_market_data("SPY", period="5y")
    if spy.empty or len(spy) < 130:
        return pd.Series(dtype=float), 0.0, "N/A"

    ret_6m = spy["close"].pct_change(periods=126).dropna()
    z = _zscore_full(ret_6m)
    z = z.dropna()

    latest = float(z.iloc[-1]) if len(z) > 0 else 0.0
    direction = "Expansionary" if latest > 0 else "Contractionary"
    return z, latest, direction


# ---------------------------------------------------------------------------
# Regime mapping
# ---------------------------------------------------------------------------

def _get_regime(value: int) -> str:
    if value >= 80:   return "Liquidity Surge"
    if value >= 60:   return "Expansion"
    if value >= 20:   return "Growth"
    if value >= -20:  return "Neutral"
    if value >= -60:  return "Tightening"
    if value >= -80:  return "Stress"
    return "Crisis"


def _get_bias(value: int) -> str:
    if value >= 40:   return "Risk-On"
    if value >= 0:    return "Mild Risk-On"
    if value >= -40:  return "Mild Risk-Off"
    return "Risk-Off"


def _get_interpretation(value: int, regime: str) -> str:
    interps = {
        "Liquidity Surge": "Exceptional liquidity expansion — all risk assets supported, momentum strong.",
        "Expansion":       "Broad liquidity expansion — favorable for equities and crypto, reduce hedges.",
        "Growth":          "Moderate liquidity growth — constructive environment, selective risk-on.",
        "Neutral":         "Balanced liquidity conditions — no strong directional bias, stay nimble.",
        "Tightening":      "Early tightening — conditions deteriorating, reduce beta exposure.",
        "Stress":          "Liquidity stress — defensive positioning recommended, increase hedges.",
        "Crisis":          "Severe liquidity crisis — maximum defensive, cash and safe havens.",
    }
    return interps.get(regime, "Monitoring conditions.")


def _get_asset_bias(value: int) -> list[dict]:
    if value >= 40:
        return [
            {"asset": "Equities", "direction": "up",   "call": "Overweight"},
            {"asset": "Gold",     "direction": "down", "call": "Trim"},
            {"asset": "BTC",      "direction": "up",   "call": "Risk-On"},
            {"asset": "USD",      "direction": "down", "call": "Weak"},
            {"asset": "Bonds",    "direction": "down", "call": "Duration −"},
        ]
    elif value >= 0:
        return [
            {"asset": "Equities", "direction": "up",      "call": "Neutral+"},
            {"asset": "Gold",     "direction": "neutral",  "call": "Hold"},
            {"asset": "BTC",      "direction": "up",       "call": "Neutral+"},
            {"asset": "USD",      "direction": "neutral",  "call": "Neutral"},
            {"asset": "Bonds",    "direction": "neutral",  "call": "Neutral"},
        ]
    elif value >= -40:
        return [
            {"asset": "Equities", "direction": "down", "call": "Underweight"},
            {"asset": "Gold",     "direction": "up",   "call": "Hedge"},
            {"asset": "BTC",      "direction": "down", "call": "Risk-Off"},
            {"asset": "USD",      "direction": "up",   "call": "Strong"},
            {"asset": "Bonds",    "direction": "down", "call": "Duration −"},
        ]
    else:
        return [
            {"asset": "Equities", "direction": "down", "call": "Sell"},
            {"asset": "Gold",     "direction": "up",   "call": "Max Hedge"},
            {"asset": "BTC",      "direction": "down", "call": "Avoid"},
            {"asset": "USD",      "direction": "up",   "call": "Safe Haven"},
            {"asset": "Bonds",    "direction": "up",   "call": "Duration +"},
        ]


# ---------------------------------------------------------------------------
# Main compute
# ---------------------------------------------------------------------------

def compute_elx() -> dict:
    """Compute the full ELX snapshot."""
    cached = _elx_cache.get("current")
    if cached:
        ts, data = cached
        if time.time() - ts < ELX_TTL:
            return data

    liq_z, liq_val, liq_dir = _compute_liquidity()
    crd_z, crd_val, crd_dir = _compute_credit()
    ryl_z, ryl_val, ryl_dir = _compute_real_yields()
    dol_z, dol_val, dol_dir = _compute_dollar()
    bet_z, bet_val, bet_dir = _compute_market_beta()

    composite = (
        0.40 * liq_val
        + 0.25 * crd_val
        + 0.20 * ryl_val
        + 0.10 * dol_val
        + 0.05 * bet_val
    )

    elx_value = _scale(composite)
    regime = _get_regime(elx_value)
    bias = _get_bias(elx_value)
    interpretation = _get_interpretation(elx_value, regime)
    asset_bias = _get_asset_bias(elx_value)

    drivers = [
        {"name": "Global Liquidity",  "score": _scale(liq_val), "direction": liq_dir, "weight": "40%"},
        {"name": "Credit Conditions", "score": _scale(crd_val), "direction": crd_dir, "weight": "25%"},
        {"name": "Real Yields",       "score": _scale(ryl_val), "direction": ryl_dir, "weight": "20%"},
        {"name": "Dollar Strength",   "score": _scale(dol_val), "direction": dol_dir, "weight": "10%"},
        {"name": "Market Beta",       "score": _scale(bet_val), "direction": bet_dir, "weight": "5%"},
    ]

    result = {
        "value": elx_value,
        "regime": regime,
        "bias": bias,
        "interpretation": interpretation,
        "asset_bias": asset_bias,
        "drivers": drivers,
        "updated": datetime.now().isoformat(),
    }

    _elx_cache["current"] = (time.time(), result)
    return result


# ---------------------------------------------------------------------------
# Historical ELX series
# ---------------------------------------------------------------------------

def compute_elx_history(days: int = 365) -> dict:
    """Compute historical ELX values aligned on common dates."""
    cached = _elx_cache.get(f"history_{days}")
    if cached:
        ts, data = cached
        if time.time() - ts < ELX_TTL:
            return data

    liq_z, _, _ = _compute_liquidity()
    crd_z, _, _ = _compute_credit()
    ryl_z, _, _ = _compute_real_yields()
    dol_z, _, _ = _compute_dollar()
    bet_z, _, _ = _compute_market_beta()

    # Build a daily date range and resample all series to it
    all_series = {"liq": liq_z, "crd": crd_z, "ryl": ryl_z, "dol": dol_z, "bet": bet_z}
    combined = pd.DataFrame(all_series)

    # Ensure DatetimeIndex before resampling
    if not combined.empty:
        if not isinstance(combined.index, pd.DatetimeIndex):
            combined.index = pd.to_datetime(combined.index)
        combined = combined.resample("D").last().ffill().dropna()

    if combined.empty:
        return {"dates": [], "values": []}

    # Trim to requested days
    combined = combined.iloc[-days:]

    elx_series = (
        0.40 * combined["liq"]
        + 0.25 * combined["crd"]
        + 0.20 * combined["ryl"]
        + 0.10 * combined["dol"]
        + 0.05 * combined["bet"]
    )

    elx_scaled = elx_series.apply(lambda x: _scale(x))

    result = {
        "dates": [d.strftime("%Y-%m-%d") for d in elx_scaled.index],
        "values": [int(v) for v in elx_scaled.tolist()],
    }

    _elx_cache[f"history_{days}"] = (time.time(), result)
    return result


# ---------------------------------------------------------------------------
# Market correlations
# ---------------------------------------------------------------------------

def compute_correlations(window: int = 90) -> list[dict]:
    """Compute correlations between ELX and market assets over `window` days."""
    cached = _elx_cache.get(f"corr_{window}")
    if cached:
        ts, data = cached
        if time.time() - ts < ELX_TTL:
            return data

    history = compute_elx_history(days=max(365, window + 30))
    if not history["dates"]:
        return []

    elx_df = pd.DataFrame({
        "date": pd.to_datetime(history["dates"]),
        "elx": history["values"],
    }).set_index("date")

    tickers = {"SPY": "S&P 500", "GC=F": "Gold", "BTC-USD": "Bitcoin"}
    dxy = fetch_fred_series("DTWEXBGS")

    results = []

    for ticker, name in tickers.items():
        mkt = fetch_market_data(ticker, period="2y")
        if mkt.empty:
            results.append({"name": name, "ticker": ticker, "correlation": 0, "price": 0, "change_30d": 0, "series": []})
            continue

        merged = elx_df.join(mkt[["close"]], how="inner")
        if len(merged) < window:
            corr = 0.0
        else:
            corr = merged["elx"].iloc[-window:].corr(merged["close"].iloc[-window:])
            corr = round(float(corr), 2) if not np.isnan(corr) else 0.0

        price = round(float(mkt["close"].iloc[-1]), 1)
        p30 = float(mkt["close"].iloc[-min(30, len(mkt))]) if len(mkt) > 1 else price
        change_30d = round((price - p30) / p30 * 100, 2) if p30 != 0 else 0.0

        spark = [round(float(v), 2) for v in mkt["close"].iloc[-30:].tolist()]

        results.append({
            "name": name, "ticker": ticker, "correlation": corr,
            "price": price, "change_30d": change_30d, "series": spark,
        })

    # DXY from FRED
    if not dxy.empty and len(dxy) > 30:
        dxy_daily = dxy[["value"]].rename(columns={"value": "close"})
        merged = elx_df.join(dxy_daily, how="inner")
        if len(merged) >= window:
            corr = merged["elx"].iloc[-window:].corr(merged["close"].iloc[-window:])
            corr = round(float(corr), 2) if not np.isnan(corr) else 0.0
        else:
            corr = 0.0
        price = round(float(dxy["value"].iloc[-1]), 1)
        p30 = float(dxy["value"].iloc[-min(30, len(dxy))]) if len(dxy) > 1 else price
        change_30d = round((price - p30) / p30 * 100, 2) if p30 != 0 else 0.0
        spark = [round(float(v), 2) for v in dxy["value"].iloc[-30:].tolist()]
        results.append({
            "name": "US Dollar", "ticker": "DXY", "correlation": corr,
            "price": price, "change_30d": change_30d, "series": spark,
        })

    _elx_cache[f"corr_{window}"] = (time.time(), results)
    return results
