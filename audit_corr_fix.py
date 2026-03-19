"""
Fix correlation analysis — the history is downsampled (bi-weekly for >10Y),
so we need to use daily ELX history for proper correlation.
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.data_fetcher import fetch_fred_series, fetch_market_data
from engine.elx_engine import compute_elx_history

OUTPUT_DIR = "/home/ubuntu/earthone/audit_output"

# Get 1Y daily ELX for correlation (not downsampled)
hist_1y = compute_elx_history(days=365)
hist_5y = compute_elx_history(days=1825)

for label, hist in [("1Y", hist_1y), ("5Y", hist_5y)]:
    print(f"\n=== Correlation Analysis ({label}) ===")
    if not hist['dates']:
        print("  No data")
        continue

    df_elx = pd.DataFrame({
        "date": pd.to_datetime(hist['dates']),
        "elx": hist['values']
    }).set_index("date")
    print(f"  ELX data points: {len(df_elx)}, freq: {label}")

    markets = {
        "spy.us": "S&P 500",
        "xauusd": "Gold",
        "btcusd": "Bitcoin",
    }

    corr_results = {}

    for ticker, name in markets.items():
        mkt = fetch_market_data(ticker, period="25y")
        if mkt.empty:
            continue

        # Resample market to match ELX frequency
        merged = df_elx.join(mkt[["close"]], how="inner")
        if len(merged) < 10:
            # Try with ffill
            mkt_resampled = mkt[["close"]].resample("D").last().ffill()
            merged = df_elx.join(mkt_resampled, how="left").ffill().dropna()

        print(f"  {name}: {len(merged)} merged points")

        if len(merged) < 10:
            corr_results[name] = {"error": f"Only {len(merged)} overlap points"}
            continue

        # Level correlation
        level_corr = merged["elx"].corr(merged["close"])

        # Change correlation (more meaningful)
        elx_chg = merged["elx"].diff().dropna()
        mkt_chg = merged["close"].pct_change().dropna()
        chg_merged = pd.DataFrame({"elx_chg": elx_chg, "mkt_chg": mkt_chg}).dropna()
        change_corr = chg_merged["elx_chg"].corr(chg_merged["mkt_chg"]) if len(chg_merged) > 5 else None

        # Rolling correlation (30-period)
        if len(merged) >= 30:
            rc = merged["elx"].rolling(30).corr(merged["close"]).dropna()
            rolling_stats = {
                "mean": round(float(rc.mean()), 3),
                "std": round(float(rc.std()), 3),
                "min": round(float(rc.min()), 3),
                "max": round(float(rc.max()), 3),
                "latest": round(float(rc.iloc[-1]), 3),
            }
        else:
            rolling_stats = None

        corr_results[name] = {
            "level_correlation": round(float(level_corr), 3) if not np.isnan(level_corr) else None,
            "change_correlation": round(float(change_corr), 3) if change_corr and not np.isnan(change_corr) else None,
            "data_points": len(merged),
            "rolling_30p": rolling_stats,
        }
        print(f"    Level corr: {level_corr:.3f}, Change corr: {change_corr:.3f}" if change_corr else f"    Level corr: {level_corr:.3f}")

    # DXY
    dxy = fetch_fred_series("DTWEXBGS")
    if not dxy.empty:
        dxy_daily = dxy[["value"]].rename(columns={"value": "close"})
        merged = df_elx.join(dxy_daily, how="inner")
        if len(merged) < 10:
            dxy_resampled = dxy_daily.resample("D").last().ffill()
            merged = df_elx.join(dxy_resampled, how="left").ffill().dropna()

        if len(merged) >= 10:
            level_corr = merged["elx"].corr(merged["close"])
            elx_chg = merged["elx"].diff().dropna()
            mkt_chg = merged["close"].pct_change().dropna()
            chg_merged = pd.DataFrame({"elx_chg": elx_chg, "mkt_chg": mkt_chg}).dropna()
            change_corr = chg_merged["elx_chg"].corr(chg_merged["mkt_chg"]) if len(chg_merged) > 5 else None

            corr_results["US Dollar (DXY)"] = {
                "level_correlation": round(float(level_corr), 3),
                "change_correlation": round(float(change_corr), 3) if change_corr and not np.isnan(change_corr) else None,
                "data_points": len(merged),
            }
            print(f"  DXY: Level corr: {level_corr:.3f}")

    with open(f"{OUTPUT_DIR}/correlation_analysis_{label.lower()}.json", "w") as f:
        json.dump(corr_results, f, indent=2)
    print(f"  Saved correlation_analysis_{label.lower()}.json")

# Also compute the live correlations from the API
print("\n=== Live correlations (from compute_correlations) ===")
from engine.elx_engine import compute_correlations
live_corr = compute_correlations(90)
for item in live_corr:
    print(f"  {item['name']}: corr={item['correlation']}, price={item['price']}")

with open(f"{OUTPUT_DIR}/live_correlations.json", "w") as f:
    json.dump(live_corr, f, indent=2, default=str)
print("  Saved live_correlations.json")
