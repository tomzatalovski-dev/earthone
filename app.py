"""
EarthOne — FastAPI Application (V4 — Distribution + Regime Intelligence)
Serves the ELX (Earth Liquidity Index) with real data, distribution features,
regime map, alerts, and enhanced social content.
"""

import io
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse
from pydantic import BaseModel

from engine.elx_engine import compute_elx, compute_elx_history, compute_correlations
from engine.database import init_db, track_event, add_subscriber, get_analytics_summary, get_subscribers
from engine.daily_image import generate_daily_image, save_daily_image
from engine.social_post import generate_post, generate_daily_report
from engine.regime_alerts import detect_regime_changes, get_current_alert, get_regime_map
from engine.decision_engine import compute_decision, compute_hedge, compute_scenarios, compute_portfolio_warnings
from engine.stripe_billing import (
    create_checkout_session, handle_webhook, verify_pro_token,
    verify_session, get_pro_subscribers
)
from engine.copilot import generate_verdict
from engine.portfolio import assess_portfolio
from engine.profiles import (
    PROFILES, get_profile_targets, compute_portfolio_score,
    get_daily_history, get_today_vs_yesterday, compute_alerts,
    compute_performance, save_user_score, get_user_evolution,
)
from engine.stripe_billing import _ensure_pro_table
import sqlite3, secrets

app = FastAPI(title="EarthOne", version="4.0")

BASE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


# ---------------------------------------------------------------------------
# Startup — init DB + warm cache + generate daily image
# ---------------------------------------------------------------------------
@app.on_event("startup")
def startup():
    init_db()

    def _warm():
        try:
            print("[EarthOne] Warming data cache...")
            compute_elx()
            compute_elx_history(365)
            compute_elx_history(7300)
            compute_correlations(90)
            print("[EarthOne] Cache warm complete.")
            _generate_daily()
        except Exception as e:
            print(f"[EarthOne] Startup error: {e}")

    threading.Thread(target=_warm, daemon=True).start()

    def _daily_loop():
        while True:
            time.sleep(6 * 3600)
            try:
                _generate_daily()
            except Exception as e:
                print(f"[EarthOne] Daily image error: {e}")

    threading.Thread(target=_daily_loop, daemon=True).start()


def _generate_daily():
    """Generate the daily share image."""
    try:
        elx = compute_elx()
        hist = compute_elx_history(90)
        path = save_daily_image(elx, hist)
        print(f"[EarthOne] Daily image saved: {path}")
    except Exception as e:
        print(f"[EarthOne] Daily image generation error: {e}")


# ---------------------------------------------------------------------------
# Homepage — SaaS Landing Page
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    track_event("page_view", path="/", ip=request.client.host if request.client else "")
    return HTMLResponse(
        content=(BASE / "templates" / "landing.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Free Signal Page (old homepage)
# ---------------------------------------------------------------------------
@app.get("/signal", response_class=HTMLResponse)
def signal_page(request: Request):
    track_event("page_view", path="/signal", ip=request.client.host if request.client else "")
    return HTMLResponse(
        content=(BASE / "templates" / "index.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Analytics Dashboard Page
# ---------------------------------------------------------------------------
@app.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request):
    track_event("page_view", path="/analytics", ip=request.client.host if request.client else "")
    return HTMLResponse(
        content=(BASE / "templates" / "analytics.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Pricing Page
# ---------------------------------------------------------------------------
@app.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    track_event("page_view", path="/pricing", ip=request.client.host if request.client else "")
    return HTMLResponse(
        content=(BASE / "templates" / "pricing.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Success Page (after Stripe checkout)
# ---------------------------------------------------------------------------
@app.get("/success", response_class=HTMLResponse)
def success_page(request: Request, session_id: str = ""):
    track_event("page_view", path="/success", ip=request.client.host if request.client else "")
    # Verify session and get pro token
    if session_id:
        result = verify_session(session_id)
        if result.get("valid") and result.get("token"):
            # Return success page with token cookie
            content = (BASE / "templates" / "success.html").read_text()
            response = HTMLResponse(content=content, status_code=200)
            response.set_cookie(
                key="elx_pro_token",
                value=result["token"],
                max_age=365 * 24 * 3600,  # 1 year
                httponly=True,
                secure=True,
                samesite="lax",
            )
            return response
    return HTMLResponse(
        content=(BASE / "templates" / "success.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Dashboard — ELX Index Pro (premium layer with paywall)
# ---------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    track_event("page_view", path="/dashboard", ip=request.client.host if request.client else "")
    # Paywall: check for pro access via cookie
    pro_token = request.cookies.get("elx_pro_token", "")
    is_pro = verify_pro_token(pro_token)
    if not is_pro:
        return RedirectResponse("/pricing?from=dashboard", status_code=302)
    return HTMLResponse(
        content=(BASE / "templates" / "dashboard.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Admin — generate pro token (hidden, remove after use)
# ---------------------------------------------------------------------------
@app.get("/api/admin/grant-pro")
def admin_grant_pro(request: Request, secret: str = ""):
    if secret != "earthone2026":
        return JSONResponse(content={"error": "unauthorized"}, status_code=403)
    _ensure_pro_table()
    from pathlib import Path as P
    db = P(__file__).resolve().parent / "data" / "elx.db"
    token = secrets.token_urlsafe(32)
    import sqlite3 as sq
    conn = sq.connect(str(db))
    conn.execute(
        "INSERT INTO pro_subscribers (email, stripe_customer_id, stripe_subscription_id, status, pro_token) VALUES (?, ?, ?, 'active', ?)",
        ("admin@elxindex.com", "admin", "admin", token)
    )
    conn.commit()
    conn.close()
    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie(
        key="elx_pro_token",
        value=token,
        max_age=365 * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


# ---------------------------------------------------------------------------
# Dashboard API — Decision Engine, Hedge, Scenarios, Alerts
# ---------------------------------------------------------------------------
@app.get("/api/dashboard/decision")
def api_dashboard_decision(request: Request):
    """Compute the decision block from current ELX data."""
    track_event("api_call", path="/api/dashboard/decision", ip=request.client.host if request.client else "")
    elx = compute_elx()
    return JSONResponse(content=compute_decision(elx))


@app.get("/api/dashboard/hedge")
def api_dashboard_hedge(request: Request):
    """Compute hedge allocation from current ELX data."""
    track_event("api_call", path="/api/dashboard/hedge", ip=request.client.host if request.client else "")
    elx = compute_elx()
    return JSONResponse(content=compute_hedge(elx))


@app.get("/api/dashboard/scenarios")
def api_dashboard_scenarios(request: Request):
    """Compute scenario engine from current ELX data."""
    track_event("api_call", path="/api/dashboard/scenarios", ip=request.client.host if request.client else "")
    elx = compute_elx()
    return JSONResponse(content=compute_scenarios(elx))


@app.get("/api/dashboard/alerts")
def api_dashboard_alerts(request: Request):
    """Compute portfolio alerts from current ELX data."""
    track_event("api_call", path="/api/dashboard/alerts", ip=request.client.host if request.client else "")
    elx = compute_elx()
    warnings = compute_portfolio_warnings(elx)
    # Combine with regime alerts
    try:
        history = compute_elx_history(30)
        regime_alert = get_current_alert(elx, history)
    except Exception:
        regime_alert = None
    alerts = []
    for w in warnings:
        alerts.append({
            "type": "warning",
            "severity": w["severity"],
            "title": w["type"],
            "description": w["message"],
            "action": "Review allocation immediately" if w["severity"] == "high" else "Monitor and prepare",
        })
    if regime_alert:
        alerts.append({
            "type": "regime",
            "severity": "high",
            "title": f"Regime Change: {regime_alert.get('from', '?')} → {regime_alert.get('to', '?')}",
            "description": regime_alert.get("message", "Regime shift detected."),
            "action": "Reassess all positions.",
        })
    return JSONResponse(content=alerts)


# ---------------------------------------------------------------------------
# Copilot API — AI-powered verdict
# ---------------------------------------------------------------------------
@app.get("/api/copilot/latest")
def api_copilot_latest(request: Request):
    """Return the latest Copilot verdict (cached, rule-based fallback)."""
    track_event("api_call", path="/api/copilot/latest", ip=request.client.host if request.client else "")
    verdict = generate_verdict()
    return JSONResponse(content=verdict)


@app.post("/api/copilot/generate")
async def api_copilot_generate(request: Request):
    """Generate a fresh Copilot verdict. Accepts optional portfolio in body."""
    track_event("api_call", path="/api/copilot/generate", ip=request.client.host if request.client else "")
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    portfolio = body.get("portfolio") if body else None
    verdict = generate_verdict(portfolio=portfolio)
    return JSONResponse(content=verdict)


# ---------------------------------------------------------------------------
# PORTFOLIO ASSESSMENT
# ---------------------------------------------------------------------------
@app.post("/api/portfolio/assess")
async def api_portfolio_assess(request: Request):
    """Assess user portfolio against current ELX regime."""
    track_event("api_call", path="/api/portfolio/assess", ip=request.client.host if request.client else "")
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    if not body:
        return JSONResponse(content={"error": "Portfolio data required"}, status_code=400)
    result = assess_portfolio(body)
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# V18 — Profiles, Daily Tracking, Alerts, Performance
# ---------------------------------------------------------------------------
@app.get("/api/profiles")
def api_profiles():
    """List available investment profiles."""
    return JSONResponse(content={
        k: {"label": v["label"], "description": v["description"], "target": v["target"]}
        for k, v in PROFILES.items()
    })


@app.post("/api/profiles/score")
async def api_profile_score(request: Request):
    """Compute portfolio alignment score for a given profile."""
    body = await request.json()
    portfolio = body.get("portfolio", {})
    profile = body.get("profile", "balanced")
    elx = compute_elx()
    regime = elx.get("regime", "Neutral")
    result = compute_portfolio_score(portfolio, profile, regime)
    return JSONResponse(content=result)


@app.get("/api/profiles/targets")
def api_profile_targets(profile: str = "balanced"):
    """Get recommended allocation for a profile adjusted by current regime."""
    elx = compute_elx()
    regime = elx.get("regime", "Neutral")
    targets = get_profile_targets(profile, regime)
    return JSONResponse(content={"profile": profile, "regime": regime, "targets": targets})


@app.get("/api/daily/history")
def api_daily_history(days: int = 7):
    """Get last N days of ELX daily snapshots."""
    return JSONResponse(content=get_daily_history(days))


@app.get("/api/daily/today-vs-yesterday")
def api_today_vs_yesterday():
    """Get today vs yesterday ELX comparison."""
    return JSONResponse(content=get_today_vs_yesterday())


@app.post("/api/alerts")
async def api_alerts(request: Request):
    """Compute alerts for a portfolio + profile."""
    body = await request.json()
    portfolio = body.get("portfolio", {})
    profile = body.get("profile", "balanced")
    elx = compute_elx()
    regime = elx.get("regime", "Neutral")
    alerts = compute_alerts(portfolio, profile, regime)
    return JSONResponse(content=alerts)


@app.get("/api/performance")
def api_performance():
    """Get ELX-following vs market performance comparison."""
    return JSONResponse(content=compute_performance())


# ---------------------------------------------------------------------------
# SEO — robots.txt and sitemap.xml
# ---------------------------------------------------------------------------
@app.get("/robots.txt")
def robots_txt():
    path = BASE / "static" / "robots.txt"
    return Response(
        content=path.read_text() if path.exists() else "User-agent: *\nAllow: /\n",
        media_type="text/plain",
    )


@app.get("/sitemap.xml")
def sitemap_xml():
    path = BASE / "static" / "sitemap.xml"
    return Response(
        content=path.read_text() if path.exists() else "",
        media_type="application/xml",
    )


# ---------------------------------------------------------------------------
# PUBLIC API — Clean, stable, structured
# ---------------------------------------------------------------------------

@app.get("/api/elx")
@app.get("/api/elx/current")
def api_elx_current(request: Request):
    """Current ELX value with drivers, regime, bias, interpretation, regime_map."""
    track_event("api_call", path="/api/elx/current", ip=request.client.host if request.client else "")
    try:
        data = compute_elx()
        # Enrich with regime map
        data["regime_map"] = get_regime_map(data.get("value", 0))
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(
            content={
                "error": str(e), "value": 0, "regime": "Loading", "bias": "—",
                "interpretation": "Data is loading, please refresh.",
                "asset_bias": [], "drivers": [], "regime_map": get_regime_map(0),
            },
            status_code=200,
        )


@app.get("/api/elx/history")
def api_elx_history(request: Request, days: int = 365):
    """Historical ELX time series. Supports: 365, 1825, 3650, 7300 (MAX)."""
    track_event("api_call", path="/api/elx/history", meta=f"days={days}",
                ip=request.client.host if request.client else "")
    try:
        data = compute_elx_history(min(days, 7300))
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content={"dates": [], "values": [], "error": str(e)}, status_code=200)


@app.get("/api/elx/drivers")
def api_elx_drivers(request: Request):
    """Current macro driver scores and metadata."""
    track_event("api_call", path="/api/elx/drivers", ip=request.client.host if request.client else "")
    try:
        data = compute_elx()
        return JSONResponse(content={
            "drivers": data.get("drivers", []),
            "asset_bias": data.get("asset_bias", []),
            "updated_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse(content={"drivers": [], "error": str(e)}, status_code=200)


@app.get("/api/elx/markets")
def api_elx_markets(request: Request):
    """ELX vs Markets — correlations, prices, sparklines."""
    track_event("api_call", path="/api/elx/markets", ip=request.client.host if request.client else "")
    try:
        data = compute_correlations(90)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content=[], status_code=200)


@app.get("/api/elx/correlations")
def api_elx_correlations(request: Request, window: int = 90):
    """Dedicated correlations endpoint with configurable window."""
    track_event("api_call", path="/api/elx/correlations", meta=f"window={window}",
                ip=request.client.host if request.client else "")
    try:
        data = compute_correlations(min(window, 365))
        return JSONResponse(content={
            "window_days": min(window, 365),
            "correlations": data,
            "updated_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse(content={"correlations": [], "error": str(e)}, status_code=200)


# ---------------------------------------------------------------------------
# Regime Map + Alerts
# ---------------------------------------------------------------------------

@app.get("/api/elx/regime")
def api_elx_regime(request: Request):
    """Current regime map with visual scale data."""
    track_event("api_call", path="/api/elx/regime", ip=request.client.host if request.client else "")
    try:
        data = compute_elx()
        regime_map = get_regime_map(data.get("value", 0))
        return JSONResponse(content={
            "value": data.get("value", 0),
            "regime": data.get("regime", "—"),
            "bias": data.get("bias", "—"),
            "regime_map": regime_map,
            "updated_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=200)


@app.get("/api/elx/alerts")
def api_elx_alerts(request: Request):
    """Check for recent regime change alerts."""
    track_event("api_call", path="/api/elx/alerts", ip=request.client.host if request.client else "")
    try:
        elx = compute_elx()
        hist = compute_elx_history(90)
        alert = get_current_alert(elx, hist)
        changes = detect_regime_changes(hist)[:10]  # Last 10 changes
        return JSONResponse(content={
            "current_alert": alert,
            "recent_changes": changes,
            "updated_at": datetime.now().isoformat(),
        })
    except Exception as e:
        return JSONResponse(content={"current_alert": None, "recent_changes": [], "error": str(e)}, status_code=200)


# ---------------------------------------------------------------------------
# Share image — dynamic with mini chart
# ---------------------------------------------------------------------------
@app.get("/api/elx/share")
def api_elx_share(request: Request):
    """Generate a premium shareable PNG image card with mini chart."""
    track_event("share_click", path="/api/elx/share", ip=request.client.host if request.client else "")
    try:
        elx = compute_elx()
        hist = compute_elx_history(90)
        png_bytes = generate_daily_image(elx, hist)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": "attachment; filename=elx-share.png",
                "Cache-Control": "public, max-age=3600",
            },
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/share/elx_latest.png")
def share_image_static():
    """Serve the pre-generated daily share image for OG/Twitter cards."""
    path = BASE / "static" / "share" / "elx_latest.png"
    if path.exists():
        return Response(
            content=path.read_bytes(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    try:
        elx = compute_elx()
        hist = compute_elx_history(90)
        png_bytes = generate_daily_image(elx, hist)
        return Response(content=png_bytes, media_type="image/png")
    except Exception:
        return Response(content=b"", media_type="image/png", status_code=404)


# ---------------------------------------------------------------------------
# Social post generator (V4 — includes weekly thread + video script)
# ---------------------------------------------------------------------------
@app.get("/api/elx/social")
def api_social_post(request: Request):
    """Generate ready-to-post social media text for X/Twitter, Threads, weekly thread, and video script."""
    track_event("api_call", path="/api/elx/social", ip=request.client.host if request.client else "")
    try:
        elx = compute_elx()
        posts = generate_post(elx)
        return JSONResponse(content=posts)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/elx/report")
def api_daily_report():
    """Generate the daily ELX report (email/newsletter format)."""
    try:
        elx = compute_elx()
        report = generate_daily_report(elx)
        return JSONResponse(content={"report": report, "date": datetime.now().isoformat()})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Email subscribe
# ---------------------------------------------------------------------------
class SubscribeRequest(BaseModel):
    email: str
    source: str = "homepage"


@app.post("/api/subscribe")
def api_subscribe(req: SubscribeRequest, request: Request):
    """Subscribe an email to ELX updates."""
    track_event("subscribe", path="/api/subscribe", meta=req.email,
                ip=request.client.host if request.client else "")
    result = add_subscriber(req.email, req.source)
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@app.get("/api/analytics")
def api_analytics():
    """Get analytics summary (page views, shares, API calls, subscribers)."""
    return JSONResponse(content=get_analytics_summary())


@app.get("/api/subscribers")
def api_subscribers():
    """Get all email subscribers."""
    subs = get_subscribers()
    return JSONResponse(content={"count": len(subs), "subscribers": subs})


# ---------------------------------------------------------------------------
# Stripe — Checkout + Webhook
# ---------------------------------------------------------------------------
@app.post("/api/stripe/checkout")
def api_stripe_checkout(request: Request):
    """Create a Stripe Checkout session for ELX Index Pro."""
    track_event("checkout_start", path="/api/stripe/checkout", ip=request.client.host if request.client else "")
    result = create_checkout_session()
    return JSONResponse(content=result)


@app.post("/api/stripe/webhook")
async def api_stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    result = handle_webhook(payload, sig_header)
    if "error" in result:
        return JSONResponse(content=result, status_code=400)
    return JSONResponse(content=result)


@app.get("/api/stripe/verify")
def api_stripe_verify(request: Request):
    """Check if current user has pro access."""
    pro_token = request.cookies.get("elx_pro_token", "")
    is_pro = verify_pro_token(pro_token)
    return JSONResponse(content={"pro": is_pro})


@app.get("/api/pro/subscribers")
def api_pro_subscribers():
    """Get all pro subscribers (admin)."""
    subs = get_pro_subscribers()
    return JSONResponse(content={"count": len(subs), "subscribers": subs})


# ---------------------------------------------------------------------------
# Track events from frontend
# ---------------------------------------------------------------------------
class TrackRequest(BaseModel):
    event: str
    meta: str = ""


@app.post("/api/track")
def api_track(req: TrackRequest, request: Request):
    """Track a frontend event (share_click, range_change, etc.)."""
    track_event(req.event, meta=req.meta, ip=request.client.host if request.client else "")
    return JSONResponse(content={"ok": True})
