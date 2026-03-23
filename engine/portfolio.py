"""
EarthOne — Portfolio Assessment Engine
Evaluates user portfolio against current ELX regime.
"""

from engine.elx_engine import compute_elx


def assess_portfolio(portfolio: dict, regime: str = None) -> dict:
    """
    Assess a portfolio against the current ELX regime.

    portfolio: dict with keys equities, btc, gold, cash, bonds, other (all %)
    regime: optional override; if None, uses live ELX regime
    """
    # Default values
    eq = portfolio.get("equities", 0)
    btc = portfolio.get("btc", 0)
    gold = portfolio.get("gold", 0)
    cash = portfolio.get("cash", 0)
    bonds = portfolio.get("bonds", 0)
    other = portfolio.get("other", 0)

    # Get current regime if not provided
    if not regime:
        elx = compute_elx()
        regime = elx.get("regime", "Neutral")

    total_risk = eq + btc + other
    defensive_exposure = cash + gold + bonds
    hedge_coverage = cash + gold

    status = "BALANCED"
    summary = "Portfolio broadly aligned with current regime."
    recommendations = []
    risk_level = "Normal"

    # --- Risk-Off regime ---
    if regime == "Risk-Off":
        risk_level = "Elevated"
        if total_risk > 50:
            status = "OVEREXPOSED"
            summary = "Portfolio is too exposed to risk assets for the current regime."
            recommendations = [
                f"Reduce equities by 10% (currently {eq}%)",
                f"Reduce BTC by 5% (currently {btc}%)",
                "Increase cash by 10%",
                "Add gold by 5%",
            ]
        elif hedge_coverage < 20:
            status = "UNDERHEDGED"
            summary = "Portfolio lacks sufficient defensive protection."
            recommendations = [
                "Increase cash allocation to at least 15%",
                "Add gold hedge (target 10%+)",
            ]
        else:
            summary = "Portfolio is defensively positioned — aligned with Risk-Off regime."

    # --- Neutral regime ---
    elif regime == "Neutral":
        if total_risk > 60:
            status = "OVEREXPOSED"
            risk_level = "Elevated"
            summary = "Portfolio is slightly too aggressive for a neutral regime."
            recommendations = [
                f"Reduce equities by 5-10% (currently {eq}%)",
                "Maintain gold hedge",
                "Keep cash buffer above 15%",
            ]
        elif defensive_exposure > 60:
            status = "UNDEREXPOSED"
            summary = "Portfolio is too defensive for a neutral regime."
            recommendations = [
                "Consider adding selective equity exposure",
                "Reduce excess cash gradually",
            ]
        else:
            summary = "Portfolio is balanced — aligned with Neutral regime."

    # --- Risk-On regime ---
    elif regime == "Risk-On":
        risk_level = "Low"
        if defensive_exposure > 50:
            status = "UNDEREXPOSED"
            summary = "Portfolio is too defensive for a supportive regime."
            recommendations = [
                "Add equities gradually",
                "Consider selective BTC exposure",
                f"Reduce excess cash (currently {cash}%)",
            ]
        elif hedge_coverage < 10:
            status = "UNDERHEDGED"
            summary = "Portfolio lacks minimum hedge even in Risk-On."
            recommendations = [
                "Keep at least 10% in cash + gold as insurance",
            ]
        else:
            summary = "Portfolio is well-positioned for the current Risk-On regime."

    # Hedge coverage label
    if hedge_coverage >= 30:
        hedge_label = "Strong"
    elif hedge_coverage >= 15:
        hedge_label = "Moderate"
    else:
        hedge_label = "Weak"

    return {
        "total_risk": total_risk,
        "defensive_exposure": defensive_exposure,
        "hedge_coverage": hedge_coverage,
        "hedge_label": hedge_label,
        "risk_level": risk_level,
        "status": status,
        "summary": summary,
        "recommendations": recommendations,
        "regime": regime,
        "portfolio": {
            "equities": eq,
            "btc": btc,
            "gold": gold,
            "cash": cash,
            "bonds": bonds,
            "other": other,
        },
    }
