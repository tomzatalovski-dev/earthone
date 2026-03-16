"""
EarthOne — ELX Engine & API  (v4 final)
"""

import math
import random
import hashlib
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path

app = FastAPI(title="EarthOne", version="4.0.0")

BASE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


# ---------------------------------------------------------------------------
# ELX Engine
# ---------------------------------------------------------------------------

def _seed(date_str: str) -> float:
    h = hashlib.sha256(date_str.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _compute_elx(dt: datetime) -> dict:
    day_key = dt.strftime("%Y-%m-%d")
    s = _seed(day_key)
    t = (dt.timetuple().tm_yday + dt.year * 365)
    cycle = math.sin(2 * math.pi * t / 480)
    rng = random.Random(int(s * 1e9))

    liquidity    = max(0, min(100, 55 + cycle * 25 + rng.gauss(0, 6)))
    credit       = max(0, min(100, 58 + cycle * 18 + rng.gauss(0, 5)))
    real_yields  = max(0, min(100, 50 - cycle * 15 + rng.gauss(0, 7)))
    dollar_inv   = max(0, min(100, 48 - cycle * 12 + rng.gauss(0, 5)))
    beta         = max(0, min(100, 52 + cycle * 20 + rng.gauss(0, 8)))

    value = round(
        0.40 * liquidity + 0.25 * credit + 0.20 * real_yields
        + 0.10 * dollar_inv + 0.05 * beta
    )
    value = max(0, min(100, value))

    # Regime
    if value >= 65:
        regime, bias = "Liquidity Expansion", "Risk-On"
    elif value >= 45:
        regime, bias = "Neutral Liquidity", "Neutral"
    else:
        regime, bias = "Liquidity Contraction", "Risk-Off"

    # Interpretation — short, punchy
    if value >= 75:
        interpretation = "Strong expansion — broad risk appetite, accommodative conditions across credit and equity markets."
    elif value >= 65:
        interpretation = "Moderate expansion — liquidity supportive, favor cyclical exposure and duration."
    elif value >= 55:
        interpretation = "Transition regime — mixed signals, selective positioning recommended."
    elif value >= 45:
        interpretation = "Neutral conditions — no directional bias, monitor credit spreads for early signals."
    elif value >= 35:
        interpretation = "Early contraction — tightening conditions emerging, reduce beta exposure."
    else:
        interpretation = "Deep contraction — defensive positioning warranted, favor cash and short duration."

    # Directional asset bias calls
    if value >= 65:
        asset_bias = [
            {"asset": "Equities", "direction": "up",   "label": "Overweight"},
            {"asset": "Gold",     "direction": "up",   "label": "Bid"},
            {"asset": "BTC",      "direction": "up",   "label": "Bid"},
            {"asset": "USD",      "direction": "down", "label": "Weak"},
            {"asset": "Bonds",    "direction": "up",   "label": "Duration +"},
        ]
    elif value >= 55:
        asset_bias = [
            {"asset": "Equities", "direction": "up",   "label": "Selective"},
            {"asset": "Gold",     "direction": "up",   "label": "Neutral-Bid"},
            {"asset": "BTC",      "direction": "flat", "label": "Neutral"},
            {"asset": "USD",      "direction": "flat", "label": "Neutral"},
            {"asset": "Bonds",    "direction": "flat", "label": "Neutral"},
        ]
    elif value >= 45:
        asset_bias = [
            {"asset": "Equities", "direction": "flat", "label": "Neutral"},
            {"asset": "Gold",     "direction": "flat", "label": "Neutral"},
            {"asset": "BTC",      "direction": "flat", "label": "Neutral"},
            {"asset": "USD",      "direction": "flat", "label": "Neutral"},
            {"asset": "Bonds",    "direction": "flat", "label": "Neutral"},
        ]
    elif value >= 35:
        asset_bias = [
            {"asset": "Equities", "direction": "down", "label": "Underweight"},
            {"asset": "Gold",     "direction": "up",   "label": "Hedge"},
            {"asset": "BTC",      "direction": "down", "label": "Risk-Off"},
            {"asset": "USD",      "direction": "up",   "label": "Strong"},
            {"asset": "Bonds",    "direction": "down", "label": "Duration −"},
        ]
    else:
        asset_bias = [
            {"asset": "Equities", "direction": "down", "label": "Avoid"},
            {"asset": "Gold",     "direction": "up",   "label": "Safe haven"},
            {"asset": "BTC",      "direction": "down", "label": "Sell"},
            {"asset": "USD",      "direction": "up",   "label": "Flight"},
            {"asset": "Bonds",    "direction": "down", "label": "Short"},
        ]

    # Driver helpers
    def _signal(score):
        return "Expansionary" if score >= 60 else "Neutral" if score >= 40 else "Contractionary"

    def _direction(score):
        return "up" if score >= 60 else "flat" if score >= 40 else "down"

    drivers = [
        {"name": "Global Liquidity",  "score": round(liquidity, 1),         "weight": 40, "signal": _signal(liquidity),   "direction": _direction(liquidity)},
        {"name": "Credit Conditions", "score": round(credit, 1),            "weight": 25, "signal": _signal(credit),      "direction": _direction(credit)},
        {"name": "Real Yields",       "score": round(100 - real_yields, 1), "weight": 20, "signal": _signal(real_yields), "direction": _direction(real_yields)},
        {"name": "Dollar Strength",   "score": round(100 - dollar_inv, 1),  "weight": 10, "signal": _signal(dollar_inv),  "direction": _direction(dollar_inv)},
        {"name": "Market Beta",       "score": round(beta, 1),              "weight": 5,  "signal": _signal(beta),        "direction": _direction(beta)},
    ]

    # Previous day delta
    prev = _seed((dt - timedelta(days=1)).strftime("%Y-%m-%d"))
    prev_rng = random.Random(int(prev * 1e9))
    prev_cycle = math.sin(2 * math.pi * (t - 1) / 480)
    prev_liq = max(0, min(100, 55 + prev_cycle * 25 + prev_rng.gauss(0, 6)))
    prev_cre = max(0, min(100, 58 + prev_cycle * 18 + prev_rng.gauss(0, 5)))
    prev_ry  = max(0, min(100, 50 - prev_cycle * 15 + prev_rng.gauss(0, 7)))
    prev_di  = max(0, min(100, 48 - prev_cycle * 12 + prev_rng.gauss(0, 5)))
    prev_be  = max(0, min(100, 52 + prev_cycle * 20 + prev_rng.gauss(0, 8)))
    prev_val = round(0.40 * prev_liq + 0.25 * prev_cre + 0.20 * prev_ry + 0.10 * prev_di + 0.05 * prev_be)
    prev_val = max(0, min(100, prev_val))
    delta = value - prev_val

    return {
        "date": day_key,
        "value": value,
        "delta": delta,
        "regime": regime,
        "bias": bias,
        "interpretation": interpretation,
        "asset_bias": asset_bias,
        "drivers": drivers,
    }


# ---------------------------------------------------------------------------
# Market simulation
# ---------------------------------------------------------------------------

def _market_series(days: int = 90):
    today = datetime.utcnow()
    elx_series = []
    for i in range(days, -1, -1):
        dt = today - timedelta(days=i)
        elx_series.append(_compute_elx(dt))

    markets = {
        "SPX":  {"label": "S&P 500",   "base": 5200, "beta": 1.2,  "vol": 0.008},
        "GOLD": {"label": "Gold",      "base": 2050, "beta": 0.4,  "vol": 0.006},
        "BTC":  {"label": "Bitcoin",   "base": 68000,"beta": 1.8,  "vol": 0.018},
        "DXY":  {"label": "US Dollar", "base": 104,  "beta": -0.7, "vol": 0.003},
    }

    result = {}
    for ticker, cfg in markets.items():
        prices = []
        price = cfg["base"]
        for j, elx_pt in enumerate(elx_series):
            day_seed = _seed(elx_pt["date"] + ticker)
            rng = random.Random(int(day_seed * 1e9))
            elx_norm = (elx_pt["value"] - 50) / 50
            drift = cfg["beta"] * elx_norm * 0.002
            noise = rng.gauss(0, cfg["vol"])
            price = price * (1 + drift + noise)
            prices.append({"date": elx_pt["date"], "price": round(price, 2)})

        elx_vals = [e["value"] for e in elx_series]
        price_vals = [p["price"] for p in prices]
        corr = _pearson(elx_vals, price_vals)

        p_now = prices[-1]["price"]
        p_30d = prices[-31]["price"] if len(prices) > 31 else prices[0]["price"]
        change_pct = round(((p_now - p_30d) / p_30d) * 100, 2)

        result[ticker] = {
            "ticker": ticker,
            "label": cfg["label"],
            "price": round(p_now, 2),
            "change_30d": change_pct,
            "correlation": round(corr, 2),
            "sparkline": [round(p["price"], 2) for p in prices[-30:]],
        }

    return result


def _pearson(x, y):
    n = len(x)
    if n == 0: return 0
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / n) or 1
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / n) or 1
    return sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n * sx * sy)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/elx")
def get_elx():
    return _compute_elx(datetime.utcnow())

@app.get("/api/elx/history")
def get_elx_history(days: int = 365):
    days = min(days, 730)
    today = datetime.utcnow()
    series = []
    for i in range(days, -1, -1):
        dt = today - timedelta(days=i)
        pt = _compute_elx(dt)
        series.append({"date": pt["date"], "value": pt["value"]})
    return {"series": series}

@app.get("/api/elx/markets")
def get_elx_markets():
    return _market_series(90)


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def homepage():
    return HTMLResponse(
        content=(BASE / "templates" / "index.html").read_text(),
        status_code=200,
    )
