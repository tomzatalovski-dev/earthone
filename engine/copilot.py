"""
EarthOne Copilot — Verdict generation via OpenAI.
Builds a snapshot from live ELX data, sends to GPT, returns structured verdict.
"""

import json
import os
import time
from datetime import datetime

from .elx_engine import compute_elx
from .decision_engine import compute_decision, compute_hedge, compute_scenarios

# ---------------------------------------------------------------------------
# Cache — one verdict per hour max
# ---------------------------------------------------------------------------
_verdict_cache: dict[str, tuple[float, dict]] = {}
VERDICT_TTL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Snapshot builder — uses real ELX data
# ---------------------------------------------------------------------------
def build_snapshot(portfolio: dict | None = None) -> dict:
    """Build a macro snapshot from current ELX data for the Copilot prompt."""
    elx = compute_elx()
    decision = compute_decision(elx)
    hedge = compute_hedge(elx)
    scenarios = compute_scenarios(elx)

    # Extract driver summary
    drivers = elx.get("drivers", [])
    macro = {}
    for d in drivers:
        key = d["name"].lower().replace(" ", "_")
        macro[key] = {"score": d["score"], "direction": d["direction"]}

    snapshot = {
        "elx": {
            "score": elx["value"],
            "regime": elx["regime"],
            "bias": elx.get("bias", ""),
            "interpretation": elx.get("interpretation", ""),
        },
        "decision": {
            "action": decision["action"],
            "conviction": decision["conviction"],
            "hedge_need": decision["hedgeNeed"],
            "liquidity": decision["liquidityDirection"],
        },
        "hedge": {
            "suggestion": hedge.get("suggestion", ""),
            "allocations": hedge.get("allocations", []),
        },
        "macro": macro,
        "scenarios": [
            {"horizon": s.get("horizon", ""), "action": s.get("action", ""), "probability": s.get("probability", "")}
            for s in scenarios[:3]
        ],
    }

    if portfolio:
        snapshot["portfolio"] = portfolio

    return snapshot


# ---------------------------------------------------------------------------
# Generate verdict via OpenAI
# ---------------------------------------------------------------------------
def generate_verdict(portfolio: dict | None = None) -> dict:
    """Generate a Copilot verdict using OpenAI. Returns cached if fresh.
    
    Portfolio personalization:
    - If portfolio is provided (via POST /api/copilot/generate), the verdict
      includes a portfolio_note assessing the user's allocation vs current regime.
    - If no portfolio, returns a global verdict (no portfolio_note).
    - No portfolio DB exists yet; users pass portfolio via API body.
      Example: {"portfolio": {"equities": 40, "btc": 30, "gold": 10, "cash": 20}}
    """

    cache_key = "with_portfolio" if portfolio else "global"
    cached = _verdict_cache.get(cache_key)
    if cached:
        ts, data = cached
        if time.time() - ts < VERDICT_TTL:
            return data

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return _fallback_verdict(portfolio)

    try:
        from openai import OpenAI
        client = OpenAI()  # uses env OPENAI_API_KEY + pre-configured base_url

        snapshot = build_snapshot(portfolio)

        prompt = f"""You are EarthOne Copilot, a macro decision engine.

You must return a structured verdict based on ELX, macro, and portfolio data.

Rules:
- Be decisive
- No vague language
- Max 3 bullets per section
- If portfolio is too risky, reduce or hedge
- If portfolio is too defensive and conditions are supportive, add risk
- Always return valid JSON

Return exactly this JSON shape:
{{
  "date": "ISO date string",
  "action": "ADD_RISK" or "WAIT" or "REDUCE" or "HEDGE",
  "confidence": number 0-100,
  "regime": "Risk-On" or "Neutral" or "Risk-Off",
  "summary": "short summary max 2 sentences",
  "why": ["reason1", "reason2"],
  "actions": ["action1", "action2"],
  "avoid": ["avoid1", "avoid2"],
  "hedge": ["hedge1", "hedge2"],
  "invalidation": "string",
  "portfolio_note": "optional string or null"
}}

Data:
{json.dumps(snapshot)}"""

        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a top-tier macro strategist and portfolio risk advisor."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        result = completion.choices[0].message.content
        if not result:
            return _fallback_verdict()

        verdict = json.loads(result)
        _verdict_cache[cache_key] = (time.time(), verdict)
        return verdict

    except Exception as e:
        print(f"[Copilot] OpenAI error: {e}")
        return _fallback_verdict(portfolio)


# ---------------------------------------------------------------------------
# Fallback verdict (no OpenAI needed)
# ---------------------------------------------------------------------------
def _fallback_verdict(portfolio: dict | None = None) -> dict:
    """Rule-based fallback when OpenAI is unavailable."""
    elx = compute_elx()
    decision = compute_decision(elx)
    hedge = compute_hedge(elx)

    value = elx["value"]
    regime = elx["regime"]
    bias = elx.get("bias", "")

    # Map decision action to verdict action
    action_map = {
        "ADD RISK": "ADD_RISK",
        "NO TRADE": "WAIT",
        "REDUCE RISK": "REDUCE",
        "HEDGE NOW": "HEDGE",
    }

    # Portfolio personalization (rule-based)
    portfolio_note = None
    if portfolio:
        eq = portfolio.get("equities", 0)
        btc = portfolio.get("btc", 0)
        gold = portfolio.get("gold", 0)
        cash = portfolio.get("cash", 0)
        risk_pct = eq + btc
        if value < -20 and risk_pct > 50:
            portfolio_note = f"Your risk allocation ({risk_pct}% equities+BTC) is too high for a {bias} regime. Consider reducing to below 40%."
        elif value > 20 and risk_pct < 30:
            portfolio_note = f"Your risk allocation ({risk_pct}% equities+BTC) is conservative for a {regime} regime. Consider increasing exposure."
        elif gold < 10 and value < 0:
            portfolio_note = f"Gold at {gold}% is low for current conditions. Consider increasing to 15-20% as a hedge."
        elif cash > 40 and value > 10:
            portfolio_note = f"Cash at {cash}% is high. Liquidity conditions support deploying capital."

    return {
        "date": datetime.now().isoformat(),
        "action": action_map.get(decision["action"], "WAIT"),
        "confidence": decision["conviction"],
        "regime": regime,
        "summary": elx.get("interpretation", ""),
        "why": [
            f"ELX at {value} \u2014 {bias}",
            f"Liquidity {decision['liquidityDirection'].lower()}",
            f"Hedge need at {decision['hedgeNeed']}",
        ],
        "actions": [hedge.get("suggestion", "Hold current positions")],
        "avoid": ["Over-leverage in current regime"] if value < 0 else ["Excessive defensiveness"],
        "hedge": [a.get("label", "") for a in hedge.get("allocations", []) if a.get("change", 0) != 0][:3],
        "invalidation": f"ELX crossing {'above ' + str(value + 20) if value < 0 else 'below ' + str(value - 20)}",
        "portfolio_note": portfolio_note,
    }
