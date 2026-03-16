"""
EarthOne — FastAPI Application (V2 — Real Data)
Serves the ELX (Earth Liquidity Index) backed by real FRED + Yahoo Finance data.
"""

import threading
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

from engine.elx_engine import compute_elx, compute_elx_history, compute_correlations

app = FastAPI(title="EarthOne", version="2.0")

BASE = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


# ---------------------------------------------------------------------------
# Pre-warm cache in background on startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
def warm_cache():
    def _warm():
        try:
            print("[EarthOne] Warming data cache...")
            compute_elx()
            compute_elx_history(365)
            compute_correlations(90)
            print("[EarthOne] Cache warm complete.")
        except Exception as e:
            print(f"[EarthOne] Cache warm error: {e}")
    threading.Thread(target=_warm, daemon=True).start()


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def homepage():
    return HTMLResponse(
        content=(BASE / "templates" / "index.html").read_text(),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/elx")
def api_elx():
    """Current ELX value with drivers, regime, bias, interpretation."""
    try:
        data = compute_elx()
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(
            content={
                "error": str(e),
                "value": 0,
                "regime": "Loading",
                "bias": "—",
                "interpretation": "Data is loading, please refresh in a moment.",
                "asset_bias": [],
                "drivers": [],
            },
            status_code=200,
        )


@app.get("/api/elx/history")
def api_elx_history(days: int = 365):
    """Historical ELX time series."""
    try:
        data = compute_elx_history(min(days, 730))
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(
            content={"dates": [], "values": [], "error": str(e)},
            status_code=200,
        )


@app.get("/api/elx/markets")
def api_elx_markets():
    """ELX vs Markets — correlations, prices, sparklines."""
    try:
        data = compute_correlations(90)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content=[], status_code=200)
