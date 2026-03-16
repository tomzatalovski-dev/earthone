"""
EarthOne — Regime Change Alerts
Detects when ELX crosses regime boundaries and generates alerts.
"""

from datetime import datetime


# Regime boundaries (same as elx_engine)
REGIMES = [
    (-100, -40, "Deep Contraction"),
    (-40,  -20, "Liquidity Contraction"),
    (-20,   20, "Neutral"),
    ( 20,   40, "Liquidity Expansion"),
    ( 40,  100, "Full Expansion"),
]


def _get_regime(value: int) -> str:
    for lo, hi, name in REGIMES:
        if lo <= value < hi:
            return name
    return "Full Expansion" if value >= 40 else "Deep Contraction"


def detect_regime_changes(history: dict) -> list[dict]:
    """Scan ELX history for regime transitions.
    
    Returns a list of regime change events, most recent first.
    """
    dates = history.get("dates", [])
    values = history.get("values", [])
    
    if len(dates) < 2:
        return []
    
    changes = []
    prev_regime = _get_regime(values[0])
    
    for i in range(1, len(values)):
        curr_regime = _get_regime(values[i])
        if curr_regime != prev_regime:
            changes.append({
                "date": dates[i],
                "from_regime": prev_regime,
                "to_regime": curr_regime,
                "elx_value": values[i],
                "direction": "expansion" if values[i] > values[i - 1] else "contraction",
            })
        prev_regime = curr_regime
    
    # Most recent first
    changes.reverse()
    return changes


def get_current_alert(elx_data: dict, history: dict) -> dict | None:
    """Check if a regime change happened in the last 7 days.
    
    Returns an alert dict or None.
    """
    changes = detect_regime_changes(history)
    if not changes:
        return None
    
    latest = changes[0]
    
    # Check if the latest change is within 7 days
    try:
        change_date = datetime.strptime(latest["date"], "%Y-%m-%d")
        days_ago = (datetime.now() - change_date).days
        if days_ago <= 7:
            return {
                "active": True,
                "type": "regime_change",
                "date": latest["date"],
                "days_ago": days_ago,
                "from_regime": latest["from_regime"],
                "to_regime": latest["to_regime"],
                "elx_value": latest["elx_value"],
                "message": f"Regime shift: {latest['from_regime']} → {latest['to_regime']} ({days_ago}d ago)",
            }
    except Exception:
        pass
    
    return {"active": False, "message": "No recent regime change"}


def get_regime_map(value: int) -> dict:
    """Generate regime map data for the visual scale.
    
    Returns the full scale with current position.
    """
    zones = [
        {"id": "deep_contraction", "label": "Deep Contraction", "range": [-100, -40], "color": "#dc2626"},
        {"id": "contraction",      "label": "Contraction",      "range": [-40, -20],  "color": "#f97316"},
        {"id": "neutral",          "label": "Neutral",          "range": [-20, 20],   "color": "#eab308"},
        {"id": "expansion",        "label": "Expansion",        "range": [20, 40],    "color": "#22c55e"},
        {"id": "full_expansion",   "label": "Full Expansion",   "range": [40, 100],   "color": "#16a34a"},
    ]
    
    current_zone = "neutral"
    for z in zones:
        if z["range"][0] <= value < z["range"][1]:
            current_zone = z["id"]
            break
    if value >= 40:
        current_zone = "full_expansion"
    
    # Position as percentage (0-100) across the full -100 to +100 range
    position = max(0, min(100, (value + 100) / 200 * 100))
    
    return {
        "value": value,
        "position": round(position, 1),
        "current_zone": current_zone,
        "zones": zones,
    }
