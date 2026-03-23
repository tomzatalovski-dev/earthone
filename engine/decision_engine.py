"""
ELX Decision Engine — Computes actionable decisions from ELX data.
Produces: action, hedge allocation, scenarios, portfolio warnings.
"""

from datetime import datetime


def compute_decision(elx: dict) -> dict:
    """Compute the decision block from ELX data."""
    value = elx["value"]
    regime = elx["regime"]
    drivers = elx.get("drivers", [])

    # Determine action
    if value >= 30:
        action = "ADD RISK"
        action_label = "Add risk exposure — liquidity supports broad allocation"
        action_color = "green"
    elif value >= 0:
        action = "NO TRADE"
        action_label = "No directional trade — wait for clearer regime signal"
        action_color = "amber"
    elif value >= -30:
        action = "REDUCE RISK"
        action_label = "Reduce risk exposure — liquidity deteriorating"
        action_color = "orange"
    else:
        action = "HEDGE NOW"
        action_label = "Activate full hedge — protect capital immediately"
        action_color = "red"

    # Override: if regime is Neutral but bias is Risk-Off, escalate
    bias = elx.get("bias", "")
    if "Risk-Off" in bias and action == "NO TRADE":
        action = "REDUCE RISK"
        action_label = "Reduce risk — mild risk-off bias detected"
        action_color = "orange"

    # Stress and hedge need scores
    stress_score = max(0, min(100, 50 - value))
    hedge_need = max(0, min(100, 60 - value))
    conviction = max(10, min(95, abs(value) + 20))

    # Liquidity direction
    liq_driver = next((d for d in drivers if d["name"] == "Global Liquidity"), None)
    liq_score = liq_driver["score"] if liq_driver else 0
    liq_dir = "Expanding" if liq_score > 10 else "Contracting" if liq_score < -10 else "Flat"

    return {
        "action": action,
        "actionLabel": action_label,
        "actionColor": action_color,
        "elxScore": value,
        "regime": regime,
        "bias": bias,
        "conviction": conviction,
        "stressScore": stress_score,
        "hedgeNeed": hedge_need,
        "liquidityDirection": liq_dir,
        "liquidityScore": liq_score,
        "updatedAt": datetime.now().isoformat(),
    }


def compute_hedge(elx: dict) -> dict:
    """Compute exact hedge allocation from ELX data."""
    value = elx["value"]
    regime = elx["regime"]
    bias = elx.get("bias", "")

    # Base allocation adjustments based on ELX value
    if value <= -40:
        # Deep contraction — max defensive
        alloc = [
            {"asset": "Equities", "delta": -30, "direction": "down"},
            {"asset": "Gold", "delta": 15, "direction": "up"},
            {"asset": "Cash", "delta": 25, "direction": "up"},
            {"asset": "Bonds", "delta": -5, "direction": "down"},
            {"asset": "BTC", "delta": -10, "direction": "down"},
        ]
        suggestion = "Max defensive: Equities -30%, Gold +15%, Cash +25%, Bonds -5%, BTC -10%. Reduce equity beta to minimum."
        confidence = 75
    elif value <= -20:
        # Contraction — defensive tilt
        alloc = [
            {"asset": "Equities", "delta": -20, "direction": "down"},
            {"asset": "Gold", "delta": 10, "direction": "up"},
            {"asset": "Cash", "delta": 15, "direction": "up"},
            {"asset": "Bonds", "delta": -5, "direction": "down"},
            {"asset": "BTC", "delta": -5, "direction": "down"},
        ]
        suggestion = "Defensive tilt: Equities -20%, Gold +10%, Cash +15%, Bonds -5%, BTC -5%."
        confidence = 65
    elif value <= 0:
        # Mild contraction — reduce and hedge
        alloc = [
            {"asset": "Equities", "delta": -10, "direction": "down"},
            {"asset": "Gold", "delta": 5, "direction": "up"},
            {"asset": "Cash", "delta": 10, "direction": "up"},
            {"asset": "Bonds", "delta": 0, "direction": "neutral"},
            {"asset": "BTC", "delta": -5, "direction": "down"},
        ]
        suggestion = "Mild defensive: Equities -10%, Gold +5%, Cash +10%, BTC -5%. Bonds neutral."
        confidence = 50
    elif value <= 20:
        # Neutral — no change
        alloc = [
            {"asset": "Equities", "delta": 0, "direction": "neutral"},
            {"asset": "Gold", "delta": 0, "direction": "neutral"},
            {"asset": "Cash", "delta": 0, "direction": "neutral"},
            {"asset": "Bonds", "delta": 0, "direction": "neutral"},
            {"asset": "BTC", "delta": 0, "direction": "neutral"},
        ]
        suggestion = "No allocation change. Maintain current positioning."
        confidence = 40
    elif value <= 40:
        # Expansion — add risk
        alloc = [
            {"asset": "Equities", "delta": 10, "direction": "up"},
            {"asset": "Gold", "delta": -5, "direction": "down"},
            {"asset": "Cash", "delta": -10, "direction": "down"},
            {"asset": "Bonds", "delta": 5, "direction": "up"},
            {"asset": "BTC", "delta": 5, "direction": "up"},
        ]
        suggestion = "Add risk: Equities +10%, BTC +5%, Bonds +5%. Reduce cash -10%, Gold -5%."
        confidence = 60
    else:
        # Full expansion — max risk-on
        alloc = [
            {"asset": "Equities", "delta": 20, "direction": "up"},
            {"asset": "Gold", "delta": -10, "direction": "down"},
            {"asset": "Cash", "delta": -15, "direction": "down"},
            {"asset": "Bonds", "delta": 5, "direction": "up"},
            {"asset": "BTC", "delta": 10, "direction": "up"},
        ]
        suggestion = "Max risk-on: Equities +20%, BTC +10%, Bonds +5%. Reduce cash -15%, Gold -10%."
        confidence = 70

    # Invalidation
    if value < 0:
        invalidation = f"Invalidated by: ELX breaking above {value + 30} (bullish confirmation) or below {value - 20} (stress trigger)."
    else:
        invalidation = f"Invalidated by: ELX breaking below {value - 30} (bearish trigger) or above {value + 20} (overextension)."

    return {
        "suggestion": suggestion,
        "allocation": alloc,
        "confidence": confidence,
        "dominantRisk": bias,
        "invalidation": invalidation,
        "horizon": "1 Week",
        "updatedAt": datetime.now().isoformat(),
    }


def compute_scenarios(elx: dict) -> list:
    """Compute scenario engine from ELX data."""
    value = elx["value"]
    regime = elx["regime"]
    bias = elx.get("bias", "")

    scenarios = []

    # 1 Week scenario
    if value < -20:
        s1 = {
            "horizon": "1 Week",
            "action": "HEDGE NOW",
            "title": "Continued liquidity contraction",
            "probability": 62,
            "description": f"ELX at {value} with contracting liquidity. Dollar strength and elevated real yields maintain pressure. No catalyst for reversal in sight.",
            "favored": ["Gold", "Cash", "Defensive equities"],
            "pressured": ["High beta equities", "BTC", "Emerging markets"],
            "actions": ["Increase gold to 15-20%", "Raise cash buffer to 25%+", "Cut equity beta to minimum"],
        }
    elif value < 0:
        s1 = {
            "horizon": "1 Week",
            "action": "REDUCE RISK",
            "title": "Neutral drift with mild risk-off bias",
            "probability": 58,
            "description": f"ELX at {value}. Liquidity remains flat to contracting. Dollar stays firm. No catalyst for broad risk-on. Selective opportunities in gold and defensive positions.",
            "favored": ["Gold", "Cash"],
            "pressured": ["High beta equities", "BTC"],
            "actions": ["Increase gold to 15-20%", "Raise cash buffer to 20%+", "Maintain defensive positioning"],
        }
    else:
        s1 = {
            "horizon": "1 Week",
            "action": "NO TRADE",
            "title": "Stable liquidity conditions",
            "probability": 55,
            "description": f"ELX at {value}. Liquidity conditions are stable. No strong directional bias. Wait for confirmation before adding risk.",
            "favored": ["Balanced allocation"],
            "pressured": ["Overweight positions"],
            "actions": ["Maintain current allocation", "Monitor for regime shift signals"],
        }
    scenarios.append(s1)

    # 1 Month scenario
    if value < -10:
        s2 = {
            "horizon": "1 Month",
            "action": "SELECTIVE",
            "title": "Conditional recovery if DXY softens",
            "probability": 38,
            "description": "If ELX trend reverses and DXY breaks below 103, the environment can support broader risk-on. Requires confirmation over 2+ weeks.",
            "favored": ["BTC", "SPX", "Gold"],
            "pressured": ["USD", "Short-duration bonds"],
            "actions": ["Hold gold allocation", "Selective BTC adds on confirmation", "Rotate from max defensive to balanced if ELX > 0"],
        }
    else:
        s2 = {
            "horizon": "1 Month",
            "action": "ADD RISK",
            "title": "Liquidity expansion supports risk assets",
            "probability": 45,
            "description": "If current liquidity trend holds, risk assets should benefit. Monitor central bank signals for confirmation.",
            "favored": ["Equities", "BTC", "Growth"],
            "pressured": ["Cash", "Gold"],
            "actions": ["Increase equity allocation", "Add BTC exposure", "Reduce cash buffer"],
        }
    scenarios.append(s2)

    # 3 Month scenario
    s3 = {
        "horizon": "3 Months",
        "action": "NO TRADE",
        "title": "Regime shift risk — monitor central bank policy",
        "probability": 30,
        "description": "If real yields stay elevated and global liquidity continues contracting, a full regime shift becomes likely. Central bank policy is the key variable.",
        "favored": ["Gold", "Cash", "Defensive equities"],
        "pressured": ["BTC", "Growth equities", "Emerging markets"],
        "actions": ["Stand aside on new positions", "Preserve capital", "Wait for regime confirmation"],
    }
    scenarios.append(s3)

    return scenarios


def compute_portfolio_warnings(elx: dict) -> list:
    """Compute portfolio warnings based on ELX regime."""
    value = elx["value"]
    warnings = []

    if value < -10:
        warnings.append({
            "type": "OVEREXPOSED",
            "severity": "high",
            "message": f"ELX at {value} — growth exposure should be below 50%. Reduce equity and crypto allocation.",
        })
        warnings.append({
            "type": "UNDERHEDGED",
            "severity": "high",
            "message": "Hedge coverage below 30%. Add gold, cash, or protective positions.",
        })
    elif value < 10:
        warnings.append({
            "type": "MONITOR",
            "severity": "medium",
            "message": f"ELX at {value} — neutral zone. Monitor for regime shift before adjusting.",
        })

    return warnings
