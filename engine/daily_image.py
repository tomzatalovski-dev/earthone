"""
EarthOne — Daily ELX Image Generator
Generates a premium 1200x675 PNG card with mini chart for social sharing.
Called daily by the scheduler or on-demand via API.
"""

import io
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
SHARE_DIR = Path(__file__).resolve().parent.parent / "static" / "share"
BOLD = str(FONT_DIR / "NotoSans-Bold.ttf")
REG = str(FONT_DIR / "NotoSans-Regular.ttf")


def _load_fonts() -> dict:
    """Load all fonts needed for the card."""
    try:
        return {
            "value":    ImageFont.truetype(BOLD, 140),
            "regime":   ImageFont.truetype(BOLD, 30),
            "bias":     ImageFont.truetype(BOLD, 18),
            "interp":   ImageFont.truetype(REG, 17),
            "driver_n": ImageFont.truetype(REG, 14),
            "driver_v": ImageFont.truetype(BOLD, 18),
            "brand":    ImageFont.truetype(BOLD, 22),
            "eyebrow":  ImageFont.truetype(REG, 12),
            "url":      ImageFont.truetype(REG, 14),
            "date":     ImageFont.truetype(REG, 14),
            "asset":    ImageFont.truetype(BOLD, 13),
            "chart_l":  ImageFont.truetype(REG, 9),
        }
    except Exception:
        fb = ImageFont.load_default()
        return {k: fb for k in ["value", "regime", "bias", "interp", "driver_n",
                                "driver_v", "brand", "eyebrow", "url", "date",
                                "asset", "chart_l"]}


def _draw_mini_chart(draw: ImageDraw.Draw, img: Image.Image,
                     values: list, dates: list,
                     x: int, y: int, w: int, h: int, accent: tuple):
    """Draw a mini ELX chart on the image."""
    if not values or len(values) < 2:
        return

    min_v = min(values) - 3
    max_v = max(values) + 3
    rng = max_v - min_v or 1

    # Grid lines (3 horizontal)
    for i in range(4):
        gy = y + int(h * i / 3)
        for gx in range(x, x + w, 3):
            draw.point((gx, gy), fill=(40, 40, 45))

    # Zero line if visible
    if min_v < 0 < max_v:
        zero_y = y + int(h - ((0 - min_v) / rng) * h)
        for gx in range(x, x + w, 4):
            draw.point((gx, zero_y), fill=(60, 60, 65))

    # Plot points
    pts = []
    for i, v in enumerate(values):
        px = x + int(i / (len(values) - 1) * w)
        py = y + int(h - ((v - min_v) / rng) * h)
        pts.append((px, py))

    # Area fill (gradient effect via transparency)
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        # Fill down to bottom
        for row in range(min(y1, y2), y + h):
            alpha = max(0, 0.15 - 0.15 * (row - min(y1, y2)) / max(1, (y + h - min(y1, y2))))
            if alpha > 0.01:
                cx = x1 + int((x2 - x1) * (row - y1) / max(1, y2 - y1)) if y2 != y1 else x1
                for col in range(x1, x2 + 1):
                    try:
                        r, g, b = img.getpixel((col, row))[:3]
                        nr = int(r + (accent[0] - r) * alpha)
                        ng = int(g + (accent[1] - g) * alpha)
                        nb = int(b + (accent[2] - b) * alpha)
                        img.putpixel((col, row), (nr, ng, nb))
                    except Exception:
                        pass

    # Line
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=accent, width=2)

    # Last point glow
    lx, ly = pts[-1]
    for r in range(12, 0, -1):
        alpha = int(60 * (1 - r / 12))
        draw.ellipse([(lx - r, ly - r), (lx + r, ly + r)],
                     fill=(accent[0], accent[1], accent[2], alpha) if img.mode == "RGBA" else accent)
    draw.ellipse([(lx - 3, ly - 3), (lx + 3, ly + 3)], fill=(255, 255, 255))


def generate_daily_image(elx_data: dict, history_data: dict) -> bytes:
    """Generate the daily ELX share image with mini chart.
    
    Args:
        elx_data: Output of compute_elx()
        history_data: Output of compute_elx_history(90) — last 90 days for mini chart
    
    Returns:
        PNG image bytes
    """
    fonts = _load_fonts()

    value = elx_data.get("value", 0)
    regime = elx_data.get("regime", "—")
    bias = elx_data.get("bias", "—")
    interpretation = elx_data.get("interpretation", "")
    drivers = elx_data.get("drivers", [])
    asset_bias = elx_data.get("asset_bias", [])

    chart_values = history_data.get("values", [])[-90:]
    chart_dates = history_data.get("dates", [])[-90:]

    # Card dimensions (Twitter/OG optimal)
    W, H = 1200, 675
    img = Image.new("RGB", (W, H), "#0A0A0A")
    draw = ImageDraw.Draw(img)

    # Accent color
    if value >= 20:
        accent = (22, 163, 74)
    elif value >= -20:
        accent = (245, 158, 11)
    else:
        accent = (220, 38, 38)

    # Dark gradient background
    for y in range(H):
        t = y / H
        r = int(10 + t * 8)
        g = int(10 + t * 8)
        b = int(12 + t * 10)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Top accent line
    draw.rectangle([(0, 0), (W, 4)], fill=accent)

    left_x = 55
    right_col_x = 680

    # Brand + LIVE
    draw.text((left_x, 24), "EarthOne", fill="#FFFFFF", font=fonts["brand"])
    draw.ellipse([(left_x + 145, 32), (left_x + 155, 42)], fill=(22, 163, 74))
    draw.text((left_x + 162, 28), "LIVE", fill="#888888", font=fonts["eyebrow"])

    # Date
    date_str = datetime.now().strftime("%b %d, %Y")
    bbox = draw.textbbox((0, 0), date_str, font=fonts["date"])
    draw.text((W - 55 - (bbox[2] - bbox[0]), 30), date_str, fill="#666666", font=fonts["date"])

    # Eyebrow
    draw.text((left_x, 65), "ELX — EARTH LIQUIDITY INDEX", fill="#666666", font=fonts["eyebrow"])

    # ELX value — MASSIVE
    sign = "+" if value >= 0 else ""
    value_text = f"{sign}{value}"
    draw.text((left_x - 6, 80), value_text, fill="#FFFFFF", font=fonts["value"])

    # Regime + Bias badge
    draw.text((left_x, 235), regime, fill="#CCCCCC", font=fonts["regime"])

    bias_bbox = draw.textbbox((0, 0), bias, font=fonts["bias"])
    regime_bbox = draw.textbbox((0, 0), regime, font=fonts["regime"])
    badge_x = left_x + (regime_bbox[2] - regime_bbox[0]) + 18
    badge_y = 240
    bias_w = bias_bbox[2] - bias_bbox[0] + 20
    bias_h = bias_bbox[3] - bias_bbox[1] + 10
    draw.rectangle([(badge_x, badge_y), (badge_x + bias_w, badge_y + bias_h)],
                   fill=(accent[0] // 4, accent[1] // 4, accent[2] // 4))
    draw.text((badge_x + 10, badge_y + 3), bias, fill=accent, font=fonts["bias"])

    # Interpretation
    words = interpretation.split()
    lines, current = [], ""
    for w in words:
        test = f"{current} {w}".strip()
        bbox = draw.textbbox((0, 0), test, font=fonts["interp"])
        if bbox[2] - bbox[0] > 550:
            lines.append(current)
            current = w
        else:
            current = test
    if current:
        lines.append(current)

    y_pos = 285
    for line in lines[:2]:
        draw.text((left_x, y_pos), line, fill="#888888", font=fonts["interp"])
        y_pos += 24

    # Asset bias chips
    y_pos = 340
    for ab in asset_bias[:5]:
        name = ab.get("asset", "")
        direction = ab.get("direction", "")
        call = ab.get("call", "")
        chip_color = (22, 163, 74) if direction == "up" else (220, 38, 38) if direction == "down" else (150, 150, 150)
        draw.text((left_x, y_pos), f"{name} {'↑' if direction == 'up' else '↓' if direction == 'down' else '→'} {call}",
                  fill=chip_color, font=fonts["asset"])
        y_pos += 22

    # ---- MINI CHART (bottom left) ----
    chart_x, chart_y = left_x, 470
    chart_w, chart_h = 560, 140

    if chart_values:
        _draw_mini_chart(draw, img, chart_values, chart_dates,
                         chart_x, chart_y, chart_w, chart_h, accent)

        # Chart label
        draw.text((chart_x, chart_y - 16), "ELX 90D", fill="#555555", font=fonts["chart_l"])
        if chart_dates:
            draw.text((chart_x + chart_w - 80, chart_y + chart_h + 4),
                      chart_dates[-1], fill="#444444", font=fonts["chart_l"])

    # ---- Separator ----
    draw.line([(right_col_x - 35, 70), (right_col_x - 35, H - 70)], fill=(35, 35, 40), width=1)

    # ---- Right column: Drivers ----
    draw.text((right_col_x, 65), "MACRO DRIVERS", fill="#666666", font=fonts["eyebrow"])

    y_drv = 90
    for d in drivers:
        name = d["name"]
        score = d["score"]
        weight = d.get("weight", "")
        direction = d.get("direction", "")
        score_color = (22, 163, 74) if score >= 0 else (220, 38, 38)
        sign_d = "+" if score >= 0 else ""

        draw.text((right_col_x, y_drv), name, fill="#AAAAAA", font=fonts["driver_n"])
        draw.text((right_col_x, y_drv + 18), f"{sign_d}{score:.0f}", fill=score_color, font=fonts["driver_v"])

        info = f"{weight} · {direction}"
        draw.text((right_col_x + 70, y_drv + 20), info, fill="#555555", font=fonts["eyebrow"])

        # Progress bar
        bar_x = right_col_x + 240
        bar_w = 150
        bar_y = y_drv + 23
        draw.rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + 5)], fill=(30, 30, 35))
        fill_w = int(bar_w * min(max((score + 100) / 200, 0), 1))
        if fill_w > 0:
            draw.rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + 5)], fill=score_color)

        y_drv += 58

    # ---- Correlations ----
    try:
        from .elx_engine import compute_correlations
        corr_data = compute_correlations(90)
        draw.text((right_col_x, y_drv + 15), "ELX CORRELATION (90D)", fill="#666666", font=fonts["eyebrow"])
        corr_y = y_drv + 38
        label_map = {"spy.us": "SPX", "xauusd": "Gold", "btcusd": "BTC", "DTWEXBGS": "DXY",
                     "S&P 500": "SPX", "Gold": "Gold", "Bitcoin": "BTC", "US Dollar": "DXY"}
        cx = right_col_x
        for m in corr_data:
            sym = label_map.get(m.get("name", ""), label_map.get(m.get("ticker", ""), ""))
            corr = m.get("correlation", 0)
            if not sym:
                continue
            c_color = (22, 163, 74) if corr >= 0 else (220, 38, 38)
            sign_c = "+" if corr >= 0 else ""
            draw.text((cx, corr_y), sym, fill="#888888", font=fonts["driver_n"])
            draw.text((cx + 35, corr_y), f"{sign_c}{corr:.2f}", fill=c_color, font=fonts["driver_n"])
            cx += 105
    except Exception:
        pass

    # ---- Footer ----
    draw.line([(left_x, H - 42), (W - 55, H - 42)], fill=(30, 30, 35), width=1)
    draw.text((left_x, H - 32), "elxindex.com", fill="#555555", font=fonts["url"])

    # Export
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()


def save_daily_image(elx_data: dict, history_data: dict) -> str:
    """Generate and save the daily image to static/share/elx_latest.png.
    
    Returns the file path.
    """
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    png_bytes = generate_daily_image(elx_data, history_data)

    path = SHARE_DIR / "elx_latest.png"
    path.write_bytes(png_bytes)

    # Also save dated version
    dated = SHARE_DIR / f"elx_{datetime.now().strftime('%Y%m%d')}.png"
    dated.write_bytes(png_bytes)

    return str(path)
