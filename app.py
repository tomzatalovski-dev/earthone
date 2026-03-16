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
# Share image endpoint — premium PNG card for social sharing
# ---------------------------------------------------------------------------
@app.get("/api/elx/share")
def api_elx_share():
    """Generate a premium shareable PNG image card with current ELX value."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        from datetime import datetime

        data = compute_elx()
        value = data["value"]
        regime = data["regime"]
        bias = data["bias"]
        interpretation = data["interpretation"]
        drivers = data.get("drivers", [])
        asset_bias = data.get("asset_bias", [])

        # Card dimensions (Twitter/X optimal: 1200x630)
        W, H = 1200, 630
        img = Image.new("RGB", (W, H), "#0A0A0A")
        draw = ImageDraw.Draw(img)

        # Load fonts
        FONT_DIR = BASE / "static" / "fonts"
        BOLD = str(FONT_DIR / "NotoSans-Bold.ttf")
        REG = str(FONT_DIR / "NotoSans-Regular.ttf")
        try:
            font_value = ImageFont.truetype(BOLD, 160)
            font_regime = ImageFont.truetype(BOLD, 34)
            font_bias = ImageFont.truetype(BOLD, 20)
            font_interp = ImageFont.truetype(REG, 19)
            font_driver_name = ImageFont.truetype(REG, 16)
            font_driver_val = ImageFont.truetype(BOLD, 20)
            font_brand = ImageFont.truetype(BOLD, 24)
            font_eyebrow = ImageFont.truetype(REG, 13)
            font_url = ImageFont.truetype(REG, 15)
            font_date = ImageFont.truetype(REG, 15)
            font_asset = ImageFont.truetype(BOLD, 15)
        except Exception:
            font_value = ImageFont.load_default()
            font_regime = font_value
            font_bias = font_value
            font_interp = font_value
            font_driver_name = font_value
            font_driver_val = font_value
            font_brand = font_value
            font_eyebrow = font_value
            font_url = font_value
            font_date = font_value
            font_asset = font_value

        # Subtle dark gradient background
        for y in range(H):
            t = y / H
            r = int(10 + t * 8)
            g = int(10 + t * 8)
            b = int(12 + t * 10)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Accent color based on regime
        if value >= 20:
            accent = (22, 163, 74)       # green
            accent_hex = "#16A34A"
        elif value >= -20:
            accent = (245, 158, 11)      # amber
            accent_hex = "#F59E0B"
        else:
            accent = (220, 38, 38)       # red
            accent_hex = "#DC2626"

        # Top accent line
        draw.rectangle([(0, 0), (W, 4)], fill=accent)

        # Left column: ELX value (takes ~60% of width)
        left_x = 60
        right_col_x = 720

        # Brand + LIVE dot
        draw.text((left_x, 30), "EarthOne", fill="#FFFFFF", font=font_brand)
        # Green dot for LIVE
        draw.ellipse([(left_x + 155, 38), (left_x + 167, 50)], fill=(22, 163, 74))
        draw.text((left_x + 175, 34), "LIVE", fill="#888888", font=font_eyebrow)

        # Date top right
        date_str = datetime.now().strftime("%b %d, %Y")
        bbox = draw.textbbox((0, 0), date_str, font=font_date)
        draw.text((W - 60 - (bbox[2] - bbox[0]), 36), date_str, fill="#666666", font=font_date)

        # Eyebrow
        draw.text((left_x, 75), "ELX — EARTH LIQUIDITY INDEX", fill="#666666", font=font_eyebrow)

# ELX value — MASSIVE
        sign = "+" if value >= 0 else ""
        value_text = f"{sign}{value}"
        draw.text((left_x - 8, 90), value_text, fill="#FFFFFF", font=font_value)

        # Regime
        draw.text((left_x, 280), regime, fill="#CCCCCC", font=font_regime)

        # Bias badge
        bias_bbox = draw.textbbox((0, 0), bias, font=font_bias)
        bias_w = bias_bbox[2] - bias_bbox[0] + 24
        bias_h = bias_bbox[3] - bias_bbox[1] + 12
        regime_bbox = draw.textbbox((0, 0), regime, font=font_regime)
        badge_x = left_x + (regime_bbox[2] - regime_bbox[0]) + 20
        badge_y = 285
        # Badge background
        for by in range(badge_y, badge_y + bias_h + 4):
            for bx in range(int(badge_x), int(badge_x + bias_w)):
                img.putpixel((bx, by), (accent[0] // 4, accent[1] // 4, accent[2] // 4))
        draw.text((badge_x + 12, badge_y + 4), bias, fill=accent, font=font_bias)

        # Interpretation (word-wrapped)
        words = interpretation.split()
        lines = []
        current = ""
        for w in words:
            test = f"{current} {w}".strip()
            bbox = draw.textbbox((0, 0), test, font=font_interp)
            if bbox[2] - bbox[0] > 580:
                lines.append(current)
                current = w
            else:
                current = test
        if current:
            lines.append(current)

        y_pos = 335
        for line in lines[:2]:
            draw.text((left_x, y_pos), line, fill="#888888", font=font_interp)
            y_pos += 26

        # Asset bias chips
        y_pos = 400
        for ab in asset_bias[:5]:
            name = ab.get("asset", "")
            direction = ab.get("direction", "")
            call = ab.get("call", "")
            chip_color = (22, 163, 74) if direction == "↑" else (220, 38, 38) if direction == "↓" else (150, 150, 150)
            chip_text = f"{name} {direction} {call}"
            draw.text((left_x, y_pos), chip_text, fill=chip_color, font=font_asset)
            y_pos += 24

        # Separator line
        draw.line([(right_col_x - 40, 80), (right_col_x - 40, H - 80)], fill=(40, 40, 45), width=1)

        # Right column: Drivers
        draw.text((right_col_x, 75), "MACRO DRIVERS", fill="#666666", font=font_eyebrow)

        y_drv = 105
        for d in drivers:
            name = d["name"]
            score = d["score"]
            weight = d.get("weight", "")
            direction = d.get("direction", "")
            score_color = (22, 163, 74) if score >= 0 else (220, 38, 38)
            sign_d = "+" if score >= 0 else ""

            draw.text((right_col_x, y_drv), name, fill="#AAAAAA", font=font_driver_name)
            draw.text((right_col_x, y_drv + 20), f"{sign_d}{score:.0f}", fill=score_color, font=font_driver_val)

            # Weight and direction
            info_text = f"{weight} · {direction}"
            draw.text((right_col_x + 80, y_drv + 22), info_text, fill="#555555", font=font_eyebrow)

            # Progress bar
            bar_x = right_col_x + 260
            bar_w = 150
            bar_y = y_drv + 25
            draw.rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + 6)], fill=(30, 30, 35))
            fill_w = int(bar_w * min(max((score + 100) / 200, 0), 1))
            if fill_w > 0:
                draw.rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + 6)], fill=score_color)

            y_drv += 65

        # Correlations at bottom right
        try:
            corr_data = compute_correlations(90)
            draw.text((right_col_x, y_drv + 20), "ELX CORRELATION (90D)", fill="#666666", font=font_eyebrow)
            corr_y = y_drv + 45
            corr_items = []
            for m in corr_data:
                sym = m.get("symbol", "")
                corr = m.get("correlation", 0)
                if sym == "spy.us":
                    corr_items.append(("SPX", corr))
                elif sym == "xauusd":
                    corr_items.append(("Gold", corr))
                elif sym == "btcusd":
                    corr_items.append(("BTC", corr))
                elif sym == "DTWEXBGS":
                    corr_items.append(("DXY", corr))

            cx = right_col_x
            for sym, corr in corr_items:
                c_color = (22, 163, 74) if corr >= 0 else (220, 38, 38)
                sign_c = "+" if corr >= 0 else ""
                draw.text((cx, corr_y), sym, fill="#888888", font=font_driver_name)
                draw.text((cx + 40, corr_y), f"{sign_c}{corr:.2f}", fill=c_color, font=font_driver_name)
                cx += 110
        except Exception:
            pass

        # Footer
        draw.line([(left_x, H - 50), (W - 60, H - 50)], fill=(30, 30, 35), width=1)
        draw.text((left_x, H - 38), "elxindex.com", fill="#555555", font=font_url)

        # Export to PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        return Response(
            content=buf.getvalue(),
            media_type="image/png",
            headers={
                "Content-Disposition": f"attachment; filename=elx-share-{value}.png",
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
