"""
EarthOne — FastAPI Application (V3 — Distribution Stack)
Serves the ELX (Earth Liquidity Index) with real data + distribution features.
"""

import io
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from engine.elx_engine import compute_elx, compute_elx_history, compute_correlations
from engine.database import init_db, track_event, add_subscriber, get_analytics_summary, get_subscribers
from engine.daily_image import generate_daily_image, save_daily_image
from engine.social_post import generate_post, generate_daily_report

app = FastAPI(title="EarthOne", version="3.0")

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
            # Generate daily share image
            _generate_daily()
        except Exception as e:
            print(f"[EarthOne] Startup error: {e}")

    threading.Thread(target=_warm, daemon=True).start()

    # Background thread: regenerate daily image every 6 hours
    def _daily_loop():
        while True:
            time.sleep(6 * 3600)
            try:
                _generate_daily()
            except Exception as e:
                print(f"[EarthOne] Daily image error: {e}")

    threading.Thread(target=_daily_loop, daemon=True).start()


def _generate_daily():
    """Generate the daily share image + social post."""
    try:
        elx = compute_elx()
        hist = compute_elx_history(90)
        path = save_daily_image(elx, hist)
        print(f"[EarthOne] Daily image saved: {path}")
    except Exception as e:
        print(f"[EarthOne] Daily image generation error: {e}")


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    track_event("page_view", path="/", ip=request.client.host if request.client else "")
    return HTMLResponse(
        content=(BASE / "templates" / "index.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# PUBLIC API — Clean, stable, structured
# ---------------------------------------------------------------------------

@app.get("/api/elx")
@app.get("/api/elx/current")
def api_elx_current(request: Request):
    """Current ELX value with drivers, regime, bias, interpretation."""
    track_event("api_call", path="/api/elx/current", ip=request.client.host if request.client else "")
    try:
        data = compute_elx()
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(
            content={
                "error": str(e), "value": 0, "regime": "Loading", "bias": "—",
                "interpretation": "Data is loading, please refresh.",
                "asset_bias": [], "drivers": [],
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
                "Content-Disposition": f"attachment; filename=elx-share.png",
                "Cache-Control": "public, max-age=3600",
            },
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Static share image for OG tags (pre-generated, fast)
# ---------------------------------------------------------------------------
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
    # Fallback: generate on the fly
    try:
        elx = compute_elx()
        hist = compute_elx_history(90)
        png_bytes = generate_daily_image(elx, hist)
        return Response(content=png_bytes, media_type="image/png")
    except Exception:
        return Response(content=b"", media_type="image/png", status_code=404)


# ---------------------------------------------------------------------------
# Social post generator
# ---------------------------------------------------------------------------
@app.get("/api/elx/social")
def api_social_post(request: Request):
    """Generate ready-to-post social media text for X/Twitter and Threads."""
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
