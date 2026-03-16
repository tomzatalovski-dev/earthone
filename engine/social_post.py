"""
EarthOne — Social Post Generator (V4)
Generates ready-to-post text for X/Twitter, Threads, weekly threads, and video scripts.
All content is deterministic — no LLM, pure template logic.
"""

from datetime import datetime


def generate_post(elx_data: dict) -> dict:
    """Generate social media posts from ELX data.
    
    Returns dict with twitter, threads, short, weekly_thread, and video_script.
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
    top_driver_detail = ""
    if drivers:
        sorted_d = sorted(drivers, key=lambda d: abs(d["score"]), reverse=True)
        td = sorted_d[0]
        td_sign = "+" if td["score"] >= 0 else ""
        top_driver = f"{td['name']} {td_sign}{td['score']}"
        top_driver_detail = td["name"]

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

    # ---- Weekly Thread (5 tweets) ----
    weekly_thread = _generate_weekly_thread(elx_data, date_str)

    # ---- Video Script (60s) ----
    video_script = _generate_video_script(elx_data, date_str)

    return {
        "twitter": twitter.strip(),
        "threads": threads.strip(),
        "short": short.strip(),
        "weekly_thread": weekly_thread,
        "video_script": video_script,
        "date": date_str,
    }


def _generate_weekly_thread(elx_data: dict, date_str: str) -> list[str]:
    """Generate a 5-tweet weekly thread for X/Twitter."""
    value = elx_data.get("value", 0)
    regime = elx_data.get("regime", "—")
    bias = elx_data.get("bias", "—")
    interpretation = elx_data.get("interpretation", "")
    asset_bias = elx_data.get("asset_bias", [])
    drivers = elx_data.get("drivers", [])
    sign = "+" if value >= 0 else ""

    # Sort drivers by absolute score
    sorted_drivers = sorted(drivers, key=lambda d: abs(d["score"]), reverse=True) if drivers else []

    # Tweet 1: Hook
    t1 = f"""🧵 ELX Weekly — {date_str}

ELX: {sign}{value}
Regime: {regime}

Here's what global liquidity is telling us this week.

👇"""

    # Tweet 2: Top driver
    if sorted_drivers:
        d = sorted_drivers[0]
        d_sign = "+" if d["score"] >= 0 else ""
        direction = "expanding" if d["score"] > 0 else "contracting" if d["score"] < 0 else "flat"
        t2 = f"""1/ Key Driver: {d['name']} ({d_sign}{d['score']})

{d['name']} is {direction}.

This accounts for {d.get('weight', '—')} of the ELX composite.

It's the strongest signal in the macro picture right now."""
    else:
        t2 = "1/ No driver data available this week."

    # Tweet 3: Asset bias
    asset_lines = []
    for ab in asset_bias[:4]:
        arrow = "↑" if ab["direction"] == "up" else "↓" if ab["direction"] == "down" else "→"
        asset_lines.append(f"  {ab['asset']} {arrow} {ab['call']}")

    t3 = f"""2/ Asset Bias:

{chr(10).join(asset_lines)}

{interpretation}"""

    # Tweet 4: Second and third drivers
    if len(sorted_drivers) >= 3:
        d2 = sorted_drivers[1]
        d3 = sorted_drivers[2]
        d2s = "+" if d2["score"] >= 0 else ""
        d3s = "+" if d3["score"] >= 0 else ""
        t4 = f"""3/ Other signals:

{d2['name']}: {d2s}{d2['score']} ({d2.get('direction', '—')})
{d3['name']}: {d3s}{d3['score']} ({d3.get('direction', '—')})

The macro picture is {'mixed' if abs(value) < 20 else 'directional'}."""
    else:
        t4 = "3/ Limited driver data this week."

    # Tweet 5: CTA
    t5 = f"""4/ Summary:

ELX {sign}{value} — {regime}
Bias: {bias}

Track the index live:
elxindex.com

#ELX #Macro #Liquidity"""

    return [t1.strip(), t2.strip(), t3.strip(), t4.strip(), t5.strip()]


def _generate_video_script(elx_data: dict, date_str: str) -> str:
    """Generate a 60-second video script for ELX Daily."""
    value = elx_data.get("value", 0)
    regime = elx_data.get("regime", "—")
    bias = elx_data.get("bias", "—")
    interpretation = elx_data.get("interpretation", "")
    asset_bias = elx_data.get("asset_bias", [])
    drivers = elx_data.get("drivers", [])
    sign = "+" if value >= 0 else ""

    sorted_drivers = sorted(drivers, key=lambda d: abs(d["score"]), reverse=True) if drivers else []
    top = sorted_drivers[0] if sorted_drivers else None
    top_name = top["name"] if top else "macro conditions"
    top_dir = "expanding" if top and top["score"] > 0 else "contracting" if top and top["score"] < 0 else "flat"

    asset_calls = []
    for ab in asset_bias[:3]:
        direction = "bullish" if ab["direction"] == "up" else "bearish" if ab["direction"] == "down" else "neutral"
        asset_calls.append(f"{ab['asset']} looks {direction}")

    script = f"""[ELX Daily — {date_str}]

HOOK (0-5s):
"ELX is at {sign}{value}. We're in {regime}. Here's what it means."

CONTEXT (5-20s):
"The Earth Liquidity Index measures global liquidity conditions across five macro drivers. Today, {top_name} is the dominant signal — it's {top_dir}."

INTERPRETATION (20-35s):
"{interpretation}"

ASSET BIAS (35-50s):
"What does this mean for your portfolio? {'. '.join(asset_calls)}."

CTA (50-60s):
"Track ELX live at elxindex.com. Link in bio."

---
Tone: Calm, institutional, confident.
Visual: Show ELX chart, regime map, driver scores.
Duration: 45-60 seconds."""

    return script.strip()


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
