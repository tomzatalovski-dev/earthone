"""
ELX Institutional Audit — Quantitative Analysis Script
Extracts full historical data, runs sensitivity tests, correlation analysis,
regime stability checks, and historical validation.
"""

import sys
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.data_fetcher import fetch_fred_series, fetch_market_data
from engine.elx_engine import (
    _zscore_full, _scale, _compute_liquidity, _compute_credit,
    _compute_real_yields, _compute_dollar, _compute_market_beta,
    compute_elx, compute_elx_history, compute_correlations,
    _get_regime, _get_bias
)

OUTPUT_DIR = "/home/ubuntu/earthone/audit_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def save_json(data, name):
    with open(f"{OUTPUT_DIR}/{name}.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved {name}.json")

# ============================================================================
# 1. EXTRACT RAW INPUTS
# ============================================================================
print("=" * 60)
print("STEP 1: Extracting raw input data...")
print("=" * 60)

raw_data = {}

# FRED series
fred_series = {
    "WALCL": "Fed Balance Sheet (weekly)",
    "M2SL": "M2 Money Supply (monthly)",
    "BAMLH0A0HYM2": "HY Credit Spread (daily)",
    "DGS10": "US 10Y Yield (daily)",
    "T10YIE": "10Y Breakeven Inflation (daily)",
    "DTWEXBGS": "Trade-Weighted Dollar (daily)",
}

for sid, desc in fred_series.items():
    df = fetch_fred_series(sid, years=25)
    if not df.empty:
        raw_data[sid] = {
            "description": desc,
            "start_date": str(df.index[0]),
            "end_date": str(df.index[-1]),
            "count": len(df),
            "min": round(float(df["value"].min()), 4),
            "max": round(float(df["value"].max()), 4),
            "mean": round(float(df["value"].mean()), 4),
            "std": round(float(df["value"].std()), 4),
            "latest": round(float(df["value"].iloc[-1]), 4),
        }
        print(f"  {sid}: {len(df)} obs, {df.index[0].date()} to {df.index[-1].date()}")
    else:
        print(f"  {sid}: EMPTY - FAILED TO FETCH")
        raw_data[sid] = {"error": "Failed to fetch"}

# Market data
market_tickers = {"spy.us": "S&P 500 (SPY)", "xauusd": "Gold", "btcusd": "Bitcoin"}
for ticker, desc in market_tickers.items():
    df = fetch_market_data(ticker, period="25y")
    if not df.empty:
        raw_data[ticker] = {
            "description": desc,
            "start_date": str(df.index[0]),
            "end_date": str(df.index[-1]),
            "count": len(df),
            "min": round(float(df["close"].min()), 2),
            "max": round(float(df["close"].max()), 2),
            "latest": round(float(df["close"].iloc[-1]), 2),
        }
        print(f"  {ticker}: {len(df)} obs, {df.index[0].date()} to {df.index[-1].date()}")
    else:
        print(f"  {ticker}: EMPTY")
        raw_data[ticker] = {"error": "Failed to fetch"}

save_json(raw_data, "raw_inputs")

# ============================================================================
# 2. EXTRACT COMPONENT Z-SCORES
# ============================================================================
print("\n" + "=" * 60)
print("STEP 2: Computing component z-scores...")
print("=" * 60)

components = {}

liq_z, liq_val, liq_dir = _compute_liquidity()
crd_z, crd_val, crd_dir = _compute_credit()
ryl_z, ryl_val, ryl_dir = _compute_real_yields()
dol_z, dol_val, dol_dir = _compute_dollar()
bet_z, bet_val, bet_dir = _compute_market_beta()

comp_data = {
    "liquidity": {"series": liq_z, "latest_z": liq_val, "direction": liq_dir, "weight": 0.40},
    "credit": {"series": crd_z, "latest_z": crd_val, "direction": crd_dir, "weight": 0.25},
    "real_yields": {"series": ryl_z, "latest_z": ryl_val, "direction": ryl_dir, "weight": 0.20},
    "dollar": {"series": dol_z, "latest_z": dol_val, "direction": dol_dir, "weight": 0.10},
    "market_beta": {"series": bet_z, "latest_z": bet_val, "direction": bet_dir, "weight": 0.05},
}

for name, data in comp_data.items():
    s = data["series"]
    if len(s) > 0:
        stats = {
            "latest_z": round(data["latest_z"], 4),
            "latest_scaled": _scale(data["latest_z"]),
            "direction": data["direction"],
            "weight": data["weight"],
            "z_min": round(float(s.min()), 4),
            "z_max": round(float(s.max()), 4),
            "z_mean": round(float(s.mean()), 4),
            "z_std": round(float(s.std()), 4),
            "count": len(s),
            "start_date": str(s.index[0]),
            "end_date": str(s.index[-1]),
            "pct_above_2std": round(float((s > 2).sum() / len(s) * 100), 2),
            "pct_below_neg2std": round(float((s < -2).sum() / len(s) * 100), 2),
        }
        components[name] = stats
        print(f"  {name}: z={stats['latest_z']:.3f}, scaled={stats['latest_scaled']}, "
              f"range=[{stats['z_min']:.2f}, {stats['z_max']:.2f}], n={stats['count']}")
    else:
        components[name] = {"error": "Empty series"}
        print(f"  {name}: EMPTY SERIES")

save_json(components, "component_zscores")

# ============================================================================
# 3. EXTRACT FULL HISTORICAL ELX
# ============================================================================
print("\n" + "=" * 60)
print("STEP 3: Computing full ELX history (MAX ~20 years)...")
print("=" * 60)

hist_max = compute_elx_history(days=7300)
print(f"  Total data points: {len(hist_max['dates'])}")
if hist_max['dates']:
    print(f"  Date range: {hist_max['dates'][0]} to {hist_max['dates'][-1]}")
    vals = np.array(hist_max['values'])
    print(f"  ELX range: [{vals.min()}, {vals.max()}]")
    print(f"  ELX mean: {vals.mean():.1f}")
    print(f"  ELX std: {vals.std():.1f}")

save_json(hist_max, "elx_history_max")

# Also get 1Y for recent analysis
hist_1y = compute_elx_history(days=365)
save_json(hist_1y, "elx_history_1y")

# ============================================================================
# 4. HISTORICAL VALIDATION — KEY MACRO EVENTS
# ============================================================================
print("\n" + "=" * 60)
print("STEP 4: Historical validation against key macro events...")
print("=" * 60)

if hist_max['dates']:
    df_elx = pd.DataFrame({
        "date": pd.to_datetime(hist_max['dates']),
        "elx": hist_max['values']
    }).set_index("date")

    events = {
        "2008 GFC Peak Stress": ("2008-09-01", "2009-03-31"),
        "2009 QE1 Recovery": ("2009-04-01", "2010-06-30"),
        "2011 Euro Crisis": ("2011-06-01", "2012-01-31"),
        "2013 Taper Tantrum": ("2013-05-01", "2013-09-30"),
        "2015 China Deval": ("2015-08-01", "2016-02-28"),
        "2018 QT + Rate Hikes": ("2018-09-01", "2019-01-31"),
        "2020 COVID Crash": ("2020-02-15", "2020-04-15"),
        "2020-2021 QE Infinity": ("2020-05-01", "2021-12-31"),
        "2022 Tightening Cycle": ("2022-01-01", "2022-12-31"),
        "2023 Bank Stress (SVB)": ("2023-03-01", "2023-05-31"),
        "2024 Soft Landing": ("2024-01-01", "2024-12-31"),
        "Current (2025-2026)": ("2025-01-01", "2026-03-18"),
    }

    event_results = {}
    for event_name, (start, end) in events.items():
        try:
            mask = (df_elx.index >= start) & (df_elx.index <= end)
            subset = df_elx[mask]
            if len(subset) > 0:
                event_results[event_name] = {
                    "period": f"{start} to {end}",
                    "data_points": len(subset),
                    "elx_mean": round(float(subset['elx'].mean()), 1),
                    "elx_min": int(subset['elx'].min()),
                    "elx_max": int(subset['elx'].max()),
                    "elx_start": int(subset['elx'].iloc[0]),
                    "elx_end": int(subset['elx'].iloc[-1]),
                    "regime_at_start": _get_regime(int(subset['elx'].iloc[0])),
                    "regime_at_end": _get_regime(int(subset['elx'].iloc[-1])),
                }
                print(f"  {event_name}: ELX [{subset['elx'].min()}, {subset['elx'].max()}], "
                      f"mean={subset['elx'].mean():.1f}")
            else:
                event_results[event_name] = {"error": "No data in range"}
                print(f"  {event_name}: No data in range")
        except Exception as e:
            event_results[event_name] = {"error": str(e)}
            print(f"  {event_name}: Error - {e}")

    save_json(event_results, "historical_validation")

# ============================================================================
# 5. SENSITIVITY ANALYSIS
# ============================================================================
print("\n" + "=" * 60)
print("STEP 5: Sensitivity analysis...")
print("=" * 60)

# Current composite
current_elx = compute_elx()
current_value = current_elx['value']
print(f"  Current ELX: {current_value}")

# Test: What if each component moves by +1 std
sensitivity = {}
weights = {"liquidity": 0.40, "credit": 0.25, "real_yields": 0.20, "dollar": 0.10, "market_beta": 0.05}
current_zs = {
    "liquidity": liq_val, "credit": crd_val, "real_yields": ryl_val,
    "dollar": dol_val, "market_beta": bet_val
}

for comp_name, weight in weights.items():
    # +1 std shock
    shocked_composite = sum(
        weights[k] * (current_zs[k] + (1.0 if k == comp_name else 0.0))
        for k in weights
    )
    shocked_value = _scale(shocked_composite)
    delta = shocked_value - current_value

    # -1 std shock
    shocked_composite_neg = sum(
        weights[k] * (current_zs[k] + (-1.0 if k == comp_name else 0.0))
        for k in weights
    )
    shocked_value_neg = _scale(shocked_composite_neg)
    delta_neg = shocked_value_neg - current_value

    # +3 std extreme shock
    shocked_composite_ext = sum(
        weights[k] * (current_zs[k] + (3.0 if k == comp_name else 0.0))
        for k in weights
    )
    shocked_value_ext = _scale(shocked_composite_ext)
    delta_ext = shocked_value_ext - current_value

    sensitivity[comp_name] = {
        "weight": weight,
        "current_z": round(current_zs[comp_name], 3),
        "plus_1std_delta": delta,
        "minus_1std_delta": delta_neg,
        "plus_3std_delta": delta_ext,
        "max_possible_impact": round(weight * 100 / 3 * 3, 1),  # weight * 100 at z=3
    }
    print(f"  {comp_name} (w={weight}): +1σ → Δ{delta:+d}, -1σ → Δ{delta_neg:+d}, +3σ → Δ{delta_ext:+d}")

save_json(sensitivity, "sensitivity_analysis")

# ============================================================================
# 6. CORRELATION ANALYSIS (ELX vs Markets)
# ============================================================================
print("\n" + "=" * 60)
print("STEP 6: Correlation analysis...")
print("=" * 60)

corr_results = {}

if hist_max['dates']:
    df_elx = pd.DataFrame({
        "date": pd.to_datetime(hist_max['dates']),
        "elx": hist_max['values']
    }).set_index("date")

    # Fetch market data
    markets = {
        "spy.us": "S&P 500",
        "xauusd": "Gold",
        "btcusd": "Bitcoin",
    }

    for ticker, name in markets.items():
        mkt = fetch_market_data(ticker, period="25y")
        if mkt.empty:
            corr_results[name] = {"error": "No data"}
            continue

        merged = df_elx.join(mkt[["close"]], how="inner")
        if len(merged) < 30:
            corr_results[name] = {"error": "Insufficient overlap"}
            continue

        # Full-sample correlation
        full_corr = merged["elx"].corr(merged["close"])

        # Rolling correlations at different windows
        rolling_corrs = {}
        for window in [30, 60, 90, 180, 365]:
            if len(merged) >= window:
                rc = merged["elx"].rolling(window).corr(merged["close"])
                rolling_corrs[f"{window}d"] = {
                    "mean": round(float(rc.mean()), 3),
                    "std": round(float(rc.std()), 3),
                    "min": round(float(rc.min()), 3),
                    "max": round(float(rc.max()), 3),
                    "latest": round(float(rc.iloc[-1]), 3) if not np.isnan(rc.iloc[-1]) else None,
                }

        # Lead/lag analysis: does ELX lead or lag the market?
        lead_lag = {}
        for lag in [-20, -10, -5, 0, 5, 10, 20]:
            if lag == 0:
                c = merged["elx"].corr(merged["close"])
            elif lag > 0:
                # ELX leads market by `lag` days
                c = merged["elx"].iloc[:-lag].corr(merged["close"].iloc[lag:].reset_index(drop=True))
            else:
                # Market leads ELX by `abs(lag)` days
                c = merged["elx"].iloc[abs(lag):].reset_index(drop=True).corr(merged["close"].iloc[:lag])
            lead_lag[f"lag_{lag}d"] = round(float(c), 3) if not np.isnan(c) else None

        corr_results[name] = {
            "full_sample_corr": round(float(full_corr), 3),
            "data_points": len(merged),
            "rolling_correlations": rolling_corrs,
            "lead_lag": lead_lag,
        }
        print(f"  {name}: full_corr={full_corr:.3f}, n={len(merged)}")

    # DXY
    dxy = fetch_fred_series("DTWEXBGS")
    if not dxy.empty:
        dxy_daily = dxy[["value"]].rename(columns={"value": "close"})
        merged = df_elx.join(dxy_daily, how="inner")
        if len(merged) >= 30:
            full_corr = merged["elx"].corr(merged["close"])
            corr_results["US Dollar (DXY)"] = {
                "full_sample_corr": round(float(full_corr), 3),
                "data_points": len(merged),
            }
            print(f"  DXY: full_corr={full_corr:.3f}, n={len(merged)}")

save_json(corr_results, "correlation_analysis")

# ============================================================================
# 7. REGIME STABILITY ANALYSIS
# ============================================================================
print("\n" + "=" * 60)
print("STEP 7: Regime stability analysis...")
print("=" * 60)

if hist_max['dates']:
    vals = np.array(hist_max['values'])
    dates = pd.to_datetime(hist_max['dates'])

    # Daily changes
    daily_changes = np.diff(vals)
    
    # Regime transitions
    regimes = [_get_regime(v) for v in vals]
    transitions = sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i-1])
    
    # Average regime duration
    regime_runs = []
    current_run = 1
    for i in range(1, len(regimes)):
        if regimes[i] == regimes[i-1]:
            current_run += 1
        else:
            regime_runs.append(current_run)
            current_run = 1
    regime_runs.append(current_run)

    # Signal-to-noise ratio
    # Signal: std of 30-day moving average
    # Noise: std of daily changes
    ma30 = pd.Series(vals).rolling(30).mean().dropna()
    signal_std = ma30.std()
    noise_std = pd.Series(daily_changes).std()
    snr = signal_std / noise_std if noise_std > 0 else float('inf')

    stability = {
        "total_observations": len(vals),
        "date_range": f"{hist_max['dates'][0]} to {hist_max['dates'][-1]}",
        "daily_change_stats": {
            "mean": round(float(np.mean(daily_changes)), 3),
            "std": round(float(np.std(daily_changes)), 3),
            "median": round(float(np.median(daily_changes)), 3),
            "max_up": int(np.max(daily_changes)),
            "max_down": int(np.min(daily_changes)),
            "pct_zero_change": round(float((daily_changes == 0).sum() / len(daily_changes) * 100), 1),
        },
        "regime_transitions": {
            "total_transitions": transitions,
            "avg_per_year": round(transitions / (len(vals) / 365), 1),
            "avg_regime_duration_days": round(np.mean(regime_runs), 1),
            "median_regime_duration_days": round(float(np.median(regime_runs)), 1),
            "min_regime_duration_days": int(np.min(regime_runs)),
            "max_regime_duration_days": int(np.max(regime_runs)),
        },
        "signal_to_noise": {
            "signal_std_30d_ma": round(float(signal_std), 2),
            "noise_std_daily_change": round(float(noise_std), 2),
            "snr_ratio": round(float(snr), 2),
        },
        "regime_distribution": {},
    }

    # Regime distribution
    from collections import Counter
    regime_counts = Counter(regimes)
    for regime, count in sorted(regime_counts.items(), key=lambda x: -x[1]):
        stability["regime_distribution"][regime] = {
            "count": count,
            "pct": round(count / len(regimes) * 100, 1),
        }

    print(f"  Total transitions: {transitions}")
    print(f"  Avg transitions/year: {stability['regime_transitions']['avg_per_year']}")
    print(f"  Avg regime duration: {stability['regime_transitions']['avg_regime_duration_days']} days")
    print(f"  Daily change std: {stability['daily_change_stats']['std']}")
    print(f"  SNR: {stability['signal_to_noise']['snr_ratio']}")
    print(f"  Regime distribution: {dict(regime_counts)}")

    save_json(stability, "regime_stability")

# ============================================================================
# 8. Z-SCORE DISTRIBUTION ANALYSIS
# ============================================================================
print("\n" + "=" * 60)
print("STEP 8: Z-score distribution analysis...")
print("=" * 60)

zscore_dist = {}
for name, data in comp_data.items():
    s = data["series"]
    if len(s) > 0:
        vals_arr = s.values
        zscore_dist[name] = {
            "skewness": round(float(pd.Series(vals_arr).skew()), 4),
            "kurtosis": round(float(pd.Series(vals_arr).kurtosis()), 4),
            "pct_within_1std": round(float(((vals_arr > -1) & (vals_arr < 1)).sum() / len(vals_arr) * 100), 1),
            "pct_within_2std": round(float(((vals_arr > -2) & (vals_arr < 2)).sum() / len(vals_arr) * 100), 1),
            "pct_extreme_3std": round(float(((vals_arr > 3) | (vals_arr < -3)).sum() / len(vals_arr) * 100), 2),
        }
        print(f"  {name}: skew={zscore_dist[name]['skewness']:.3f}, "
              f"kurt={zscore_dist[name]['kurtosis']:.3f}, "
              f"within_1σ={zscore_dist[name]['pct_within_1std']}%")

save_json(zscore_dist, "zscore_distributions")

# ============================================================================
# 9. CURRENT SNAPSHOT
# ============================================================================
print("\n" + "=" * 60)
print("STEP 9: Current ELX snapshot...")
print("=" * 60)

current = compute_elx()
save_json(current, "current_snapshot")
print(f"  ELX Value: {current['value']}")
print(f"  Regime: {current['regime']}")
print(f"  Bias: {current['bias']}")
print(f"  Interpretation: {current['interpretation']}")
for d in current.get('drivers', []):
    print(f"    {d['name']}: {d['score']} ({d['direction']}, {d['weight']})")

print("\n" + "=" * 60)
print("AUDIT DATA EXTRACTION COMPLETE")
print(f"All output saved to {OUTPUT_DIR}/")
print("=" * 60)
