"""
One-off generator for the GitHub social-preview image (1280x640).
Not part of the app — run manually, upload the output by hand at
Settings -> General -> Social preview on the GitHub repo page.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
BG_TOP = (13, 17, 23)  # GitHub dark bg
BG_BOTTOM = (22, 27, 34)
ACCENT_GREEN = (63, 185, 80)
ACCENT_RED = (248, 81, 73)
ACCENT_BLUE = (88, 166, 255)
TEXT_WHITE = (230, 237, 243)
TEXT_DIM = (139, 148, 158)

FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def vertical_gradient(draw: ImageDraw.ImageDraw, top: tuple, bottom: tuple) -> None:
    for y in range(H):
        t = y / H
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def main() -> None:
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    vertical_gradient(draw, BG_TOP, BG_BOTTOM)

    pad = 72

    # A simple drawn bar-chart glyph instead of an emoji (emoji glyphs
    # aren't in the plain TTF fonts available here and render as a
    # missing-glyph box).
    bar_x = pad
    bar_y = 100
    bar_w = 22
    bar_gap = 14
    bar_heights = [34, 58, 46, 70]
    bar_colors = [ACCENT_RED, ACCENT_BLUE, ACCENT_BLUE, ACCENT_GREEN]
    max_h = max(bar_heights)
    for i, (h, color) in enumerate(zip(bar_heights, bar_colors)):
        x0 = bar_x + i * (bar_w + bar_gap)
        y1 = bar_y + max_h
        y0 = y1 - h
        draw.rounded_rectangle([x0, y0, x0 + bar_w, y1], radius=4, fill=color)

    # Title
    title_font = font("segoeuib.ttf", 76)
    title_x = bar_x + 4 * (bar_w + bar_gap) + 16
    draw.text((title_x, 60), "Hisaab", font=title_font, fill=TEXT_WHITE)

    # Tagline
    tagline_font = font("seguisb.ttf", 34)
    draw.text((pad, 190), "hisaab keeps the receipts", font=tagline_font, fill=ACCENT_BLUE)

    # Description
    desc_font = font("arial.ttf", 28)
    lines = [
        "Grades Indian YouTube finfluencer stock tips against",
        "actual market outcomes vs the NIFTY 50 \u2014 timestamped,",
        "verifiable, built on SerpApi.",
    ]
    y = 270
    for line in lines:
        draw.text((pad, y), line, font=desc_font, fill=TEXT_DIM)
        y += 40

    # A small "what it measures" strip \u2014 labels only, no invented numbers.
    # This is a hackathon README's social card; putting fabricated stats
    # on it would contradict the entire point of the project.
    strip_y = 440
    strip_h = 110
    draw.rounded_rectangle(
        [pad, strip_y, W - pad, strip_y + strip_h], radius=14, fill=(30, 36, 44)
    )
    stat_font_big = font("segoeuib.ttf", 30)
    stat_font_small = font("arial.ttf", 20)
    stats = [
        ("vs NIFTY 50", "Hit Rate", ACCENT_BLUE),
        ("Bootstrap CI", "Excess Return", ACCENT_BLUE),
        ("Click to verify", "Exact Timestamp", ACCENT_GREEN),
    ]
    col_w = (W - 2 * pad) // 3
    for i, (label, value, color) in enumerate(stats):
        x = pad + i * col_w + 30
        draw.text((x, strip_y + 20), value, font=stat_font_big, fill=color)
        draw.text((x, strip_y + 62), label, font=stat_font_small, fill=TEXT_DIM)

    # Footer badge
    footer_font = font("arial.ttf", 24)
    draw.text(
        (pad, H - 60),
        "Built for the SerpApi India Hackathon 2026",
        font=footer_font,
        fill=TEXT_DIM,
    )

    out_path = Path(__file__).parent.parent / "social_preview.png"
    img.save(out_path)
    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
