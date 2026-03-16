"""
EarthOne — FastAPI Application (V2 — Real Data)
Serves the ELX (Earth Liquidity Index) backed by real FRED + Stooq data.
"""

import io
import threading
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pathlib import Path

from engine.elx_engine import compute_elx, compute_elx_history, compute_correlations

app = FastAPI(title="EarthOne", version="2.1")

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
            compute_elx_history(7300)  # warm MAX history
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
    """Historical ELX time series. Supports: 365, 1825, 3650, 7300 (MAX)."""
    try:
        data = compute_elx_history(min(days, 7300))
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
        import traceback
        traceback.print_exc()
        return JSONResponse(content=[], status_code=200)


# ---------------------------------------------------------------------------
# Share image endpoint — generates a PNG card for social sharing
# ---------------------------------------------------------------------------
@app.get("/api/elx/share")
def api_elx_share():
    """Generate a shareable PNG image card with current ELX value."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import math

        data = compute_elx()
        value = data["value"]
        regime = data["regime"]
        bias = data["bias"]
        interpretation = data["interpretation"]

        # Card dimensions (Twitter/X optimal: 1200x675)
        W, H = 1200, 675
        img = Image.new("RGB", (W, H), "#FFFFFF")
        draw = ImageDraw.Draw(img)

        # Try to load a clean font, fallback to default
        try:
            font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 120)
            font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
            font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except Exception:
            font_xl = ImageFont.load_default()
            font_lg = font_xl
            font_md = font_xl
            font_sm = font_xl
            font_brand = font_xl

        # Subtle gradient background
        for y in range(H):
            r = int(255 - (y / H) * 8)
            g = int(255 - (y / H) * 8)
            b = int(255 - (y / H) * 5)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Accent color based on regime
        if value >= 20:
            accent = "#16A34A"  # green
        elif value >= -20:
            accent = "#F59E0B"  # amber
        else:
            accent = "#DC2626"  # red

        # Left accent bar
        draw.rectangle([(0, 0), (6, H)], fill=accent)

        # Brand
        draw.text((60, 45), "EarthOne", fill="#111111", font=font_brand)

        # Eyebrow
        draw.text((60, 95), "ELX — EARTH LIQUIDITY INDEX", fill="#888888", font=font_sm)

        # ELX value
        sign = "+" if value >= 0 else ""
        value_text = f"{sign}{value}"
        draw.text((60, 135), value_text, fill="#111111", font=font_xl)

        # Regime + Bias
        draw.text((60, 280), regime, fill="#333333", font=font_lg)
        draw.text((60, 330), bias, fill=accent, font=font_md)

        # Interpretation
        # Word wrap
        words = interpretation.split()
        lines = []
        current = ""
        for w in words:
            test = f"{current} {w}".strip()
            bbox = draw.textbbox((0, 0), test, font=font_md)
            if bbox[2] - bbox[0] > 900:
                lines.append(current)
                current = w
            else:
                current = test
        if current:
            lines.append(current)

        y_pos = 390
        for line in lines[:3]:
            draw.text((60, y_pos), line, fill="#666666", font=font_md)
            y_pos += 34

        # Drivers summary
        drivers = data.get("drivers", [])
        y_pos = 500
        for d in drivers:
            score = d["score"]
            name = d["name"]
            arrow = "+" if score >= 0 else ""
            color = "#16A34A" if score >= 0 else "#DC2626"
            draw.text((60, y_pos), f"{name}", fill="#888888", font=font_sm)
            draw.text((280, y_pos), f"{arrow}{score}", fill=color, font=font_sm)
            y_pos += 28

        # Footer
        draw.text((60, H - 40), "earthone-production.up.railway.app", fill="#AAAAAA", font=font_sm)

        # Date
        from datetime import datetime
        date_str = datetime.now().strftime("%b %d, %Y")
        bbox = draw.textbbox((0, 0), date_str, font=font_sm)
        draw.text((W - 60 - (bbox[2] - bbox[0]), 50), date_str, fill="#888888", font=font_sm)

        # Export to PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG", quality=95)
        buf.seek(0)

        return Response(
            content=buf.getvalue(),
            media_type="image/png",
            headers={
                "Content-Disposition": f"inline; filename=elx-{value}-{date_str}.png",
                "Cache-Control": "public, max-age=3600",
            },
        )

    except ImportError:
        return JSONResponse(
            content={"error": "Pillow not installed on server"},
            status_code=500,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500,
        )
