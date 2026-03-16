"""
EarthOne — Social Post Generator
Generates ready-to-post text for X/Twitter and Threads.
Run daily to produce the ELX Daily update.
"""

from datetime import datetime


def generate_post(elx_data: dict) -> dict:
    """Generate social media posts from ELX data.
    
    Returns dict with 'twitter' and 'threads' text versions.
    """
    value = elx_data.get("value", 0)
    regime = elx_data.get("regime", "—")
    bias = elx_data.get("bias", "—")
    interpretation = elx_data.get("interpretation", "")
    asset_bias = elx_data.get("asset_bias", [])
    drivers = elx_data.get("drivers", [])
    date_str = datetime.now().strftime("%b %d, %Y")

    sign = "+" if value >= 0 else ""

    # Asset bias lines
    asset_lines = []
    for ab in asset_bias:
        arrow = "↑" if ab["direction"] == "up" else "↓" if ab["direction"] == "down" else "→"
        asset_lines.append(f"{ab['asset']} {arrow} {ab['call']}")

    # Top driver
    top_driver = ""
    if drivers:
        sorted_d = sorted(drivers, key=lambda d: abs(d["score"]), reverse=True)
        td = sorted_d[0]
        td_sign = "+" if td["score"] >= 0 else ""
        top_driver = f"{td['name']} {td_sign}{td['score']}"

    # ---- Twitter/X version (280 char limit) ----
    twitter = f"""ELX Update — {date_str}

ELX: {sign}{value}
Regime: {regime}

{interpretation}

{chr(10).join(asset_lines)}

elxindex.com"""

    # ---- Threads version (longer, more detail) ----
    threads = f"""ELX Daily — {date_str}

ELX: {sign}{value}
Regime: {regime}
Bias: {bias}

{interpretation}

Asset Bias:
{chr(10).join(asset_lines)}

Key Driver: {top_driver}

Data: FRED + Stooq
Link: elxindex.com

#ELX #Macro #Liquidity #Markets"""

    # ---- Short version for captions ----
    short = f"ELX {sign}{value} · {regime} · elxindex.com"

    return {
        "twitter": twitter.strip(),
        "threads": threads.strip(),
        "short": short.strip(),
        "date": date_str,
    }


def generate_daily_report(elx_data: dict) -> str:
    """Generate a longer daily report for email/newsletter."""
    value = elx_data.get("value", 0)
    regime = elx_data.get("regime", "—")
    bias = elx_data.get("bias", "—")
    interpretation = elx_data.get("interpretation", "")
    asset_bias = elx_data.get("asset_bias", [])
    drivers = elx_data.get("drivers", [])
    date_str = datetime.now().strftime("%B %d, %Y")
    sign = "+" if value >= 0 else ""

    driver_lines = []
    for d in drivers:
        d_sign = "+" if d["score"] >= 0 else ""
        driver_lines.append(f"  {d['name']}: {d_sign}{d['score']} ({d['direction']}) — {d['weight']} weight")

    asset_lines = []
    for ab in asset_bias:
        arrow = "↑" if ab["direction"] == "up" else "↓" if ab["direction"] == "down" else "→"
        asset_lines.append(f"  {ab['asset']} {arrow} {ab['call']}")

    report = f"""ELX Daily Report — {date_str}
{'=' * 50}

ELX: {sign}{value}
Regime: {regime}
Bias: {bias}

{interpretation}

Macro Drivers:
{chr(10).join(driver_lines)}

Asset Bias:
{chr(10).join(asset_lines)}

---
EarthOne Research · elxindex.com
Data: FRED + Stooq · Not financial advice
"""
    return report.strip()
