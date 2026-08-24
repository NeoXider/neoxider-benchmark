# -*- coding: utf-8 -*-
"""Build the Neoxider Benchmark GitHub social preview.

Run from any directory:
    python docs/make_cover.py

The composition is rendered at 2x and downsampled for clean type and curves.
It intentionally uses only Pillow, Windows system fonts, and the canonical
Neoxider mascot master.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH, HEIGHT = 1280, 640
SCALE = 2
SIZE = (WIDTH * SCALE, HEIGHT * SCALE)

BACKGROUND = (15, 17, 21)
PANEL = (18, 22, 28)
TEXT = (230, 230, 230)
MUTED = (139, 147, 161)
GREEN = (74, 222, 128)
CYAN = (34, 211, 238)
BLUE = (59, 130, 246)

MASCOT_PATH = Path(
    r"C:\Users\User\.codex\skills\neoxider-video-studio\assets\masters"
    r"\neoxider_slime_master_transparent.png"
)
OUTPUT_PATH = Path(__file__).resolve().with_name("cover.png")


def px(value: float) -> int:
    return round(value * SCALE)


def box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
    return px(x0), px(y0), px(x1), px(y1)


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    candidates = {
        "regular": ("segoeui.ttf", "arial.ttf"),
        "semibold": ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"),
        "bold": ("seguibl.ttf", "segoeuib.ttf", "arialbd.ttf"),
    }[weight]
    font_dir = Path(r"C:\Windows\Fonts")
    for filename in candidates:
        path = font_dir / filename
        if path.is_file():
            return ImageFont.truetype(str(path), px(size))
    raise FileNotFoundError("Segoe UI and Arial were not found in C:\\Windows\\Fonts")


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def alpha_layer() -> Image.Image:
    return Image.new("RGBA", SIZE, (0, 0, 0, 0))


def add_soft_glow(
    image: Image.Image,
    center: tuple[float, float],
    radius: float,
    color: tuple[int, int, int],
    opacity: int,
) -> None:
    layer = alpha_layer()
    draw = ImageDraw.Draw(layer)
    cx, cy = map(px, center)
    core = px(radius * 0.42)
    draw.ellipse((cx - core, cy - core, cx + core, cy + core), fill=(*color, opacity))
    layer = layer.filter(ImageFilter.GaussianBlur(px(radius * 0.42)))
    image.alpha_composite(layer)


def add_background_depth(image: Image.Image) -> None:
    add_soft_glow(image, (1055, 300), 345, CYAN, 54)
    add_soft_glow(image, (905, 455), 280, GREEN, 27)
    add_soft_glow(image, (300, -40), 260, BLUE, 22)

    # A quiet drafting grid that fades into the base color.
    grid = alpha_layer()
    gd = ImageDraw.Draw(grid)
    for x in range(800, 1281, 40):
        gd.line((px(x), 0, px(x), px(590)), fill=(*BLUE, 16), width=px(1))
    for y in range(40, 601, 40):
        gd.line((px(760), px(y), px(1280), px(y)), fill=(*CYAN, 13), width=px(1))
    grid = grid.filter(ImageFilter.GaussianBlur(px(0.35)))
    image.alpha_composite(grid)

    # Low-contrast topographic traces make the background feel measured, not decorative.
    traces = alpha_layer()
    td = ImageDraw.Draw(traces)
    for offset in range(5):
        points = []
        for x in range(-20, 820, 10):
            y = 565 - offset * 19 + 8 * math.sin((x + offset * 45) / 92)
            points.append((px(x), px(y)))
        td.line(points, fill=(*GREEN, 10 + offset * 2), width=px(1))
    image.alpha_composite(traces)

    # Subtle vignette preserves contrast at the crop edges.
    vignette_mask = Image.radial_gradient("L").resize(SIZE, Image.Resampling.BICUBIC)
    vignette_mask = vignette_mask.point(lambda value: round(value * 0.20))
    vignette = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    vignette.putalpha(vignette_mask)
    image.alpha_composite(vignette)


def add_mascot_stage(image: Image.Image) -> None:
    layer = alpha_layer()
    draw = ImageDraw.Draw(layer)
    center = (1042, 302)

    # Glassy field and broken orbital arcs frame the mascot without boxing it in.
    draw.ellipse(box(818, 77, 1266, 525), fill=(15, 21, 27, 94), outline=(*CYAN, 32), width=px(1))
    draw.arc(box(800, 59, 1284, 543), 202, 335, fill=(*GREEN, 115), width=px(3))
    draw.arc(box(800, 59, 1284, 543), 22, 122, fill=(*CYAN, 125), width=px(3))
    draw.arc(box(837, 96, 1247, 506), 138, 191, fill=(*BLUE, 80), width=px(2))
    for angle in (16, 58, 112, 164, 218, 278, 326):
        radians = math.radians(angle)
        inner = 232
        outer = 239
        x0 = center[0] + math.cos(radians) * inner
        y0 = center[1] + math.sin(radians) * inner
        x1 = center[0] + math.cos(radians) * outer
        y1 = center[1] + math.sin(radians) * outer
        draw.line((px(x0), px(y0), px(x1), px(y1)), fill=(*MUTED, 62), width=px(1))
    image.alpha_composite(layer)

    # A soft floor shadow and two-color aura ground the glossy sphere.
    shadow = alpha_layer()
    sd = ImageDraw.Draw(shadow)
    sd.ellipse(box(865, 481, 1216, 548), fill=(0, 0, 0, 145))
    shadow = shadow.filter(ImageFilter.GaussianBlur(px(21)))
    image.alpha_composite(shadow)
    add_soft_glow(image, (965, 330), 215, GREEN, 65)
    add_soft_glow(image, (1110, 306), 210, CYAN, 72)

    if not MASCOT_PATH.is_file():
        raise FileNotFoundError(f"Canonical mascot not found: {MASCOT_PATH}")
    mascot = Image.open(MASCOT_PATH).convert("RGBA")
    alpha_bbox = mascot.getchannel("A").getbbox()
    if alpha_bbox is None:
        raise ValueError(f"Mascot has no visible pixels: {MASCOT_PATH}")
    mascot = mascot.crop(alpha_bbox)
    visible_size = px(426)
    mascot.thumbnail((visible_size, visible_size), Image.Resampling.LANCZOS)
    x = px(1042) - mascot.width // 2
    y = px(302) - mascot.height // 2
    image.alpha_composite(mascot, (x, y))


def gradient_text(
    image: Image.Image,
    position: tuple[int, int],
    value: str,
    text_font: ImageFont.FreeTypeFont,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> None:
    x, y = map(px, position)
    mask = Image.new("L", SIZE, 0)
    md = ImageDraw.Draw(mask)
    md.text((x, y), value, font=text_font, fill=255, stroke_width=px(1), stroke_fill=255)
    bounds = mask.getbbox()
    if bounds is None:
        return
    gradient = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    gd = ImageDraw.Draw(gradient)
    left, _, right, _ = bounds
    width = max(1, right - left - 1)
    for column in range(left, right):
        color = mix(start, end, (column - left) / width)
        gd.line((column, bounds[1], column, bounds[3]), fill=(*color, 255))
    gradient.putalpha(mask)
    image.alpha_composite(gradient)


def add_text_and_categories(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    x = px(76)

    # Eyebrow and title share one strong left edge; the rule is a brand-color anchor.
    rule = alpha_layer()
    rd = ImageDraw.Draw(rule)
    for row in range(px(145)):
        color = mix(GREEN, CYAN, row / max(1, px(144)))
        rd.line((px(76), px(82) + row, px(81), px(82) + row), fill=(*color, 255))
    image.alpha_composite(rule)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(box(76, 48, 97, 53), radius=px(2.5), fill=GREEN)
    draw.text((px(108), px(37)), "OPEN-SOURCE AGENT EVALUATION", font=font(20, "semibold"), fill=MUTED)

    draw.text((x, px(72)), "NEOXIDER", font=font(64, "bold"), fill=TEXT)
    gradient_text(image, (76, 135), "BENCHMARK", font(72, "bold"), GREEN, CYAN)
    draw = ImageDraw.Draw(image)

    draw.text(
        (x, px(241)),
        "Agentic CLI models, measured honestly.",
        font=font(30, "semibold"),
        fill=TEXT,
    )
    draw.text(
        (x, px(293)),
        "Not facts recalled, but work carried through — format intact,",
        font=font(23),
        fill=MUTED,
    )
    draw.text(
        (x, px(327)),
        "including the honesty to admit when an attempt didn't work.",
        font=font(23),
        fill=MUTED,
    )

    draw.text((x, px(383)), "EVALUATION AXES", font=font(20, "semibold"), fill=(*MUTED, 255))

    labels = ("instruction", "logic", "spatial", "math", "agentic", "honesty")
    card_width, card_height = 196, 42
    gap_x, gap_y = 12, 10
    for index, label in enumerate(labels):
        column, row = index % 3, index // 3
        left = 76 + column * (card_width + gap_x)
        top = 416 + row * (card_height + gap_y)
        accent = mix(GREEN, CYAN, index / (len(labels) - 1))
        draw.rounded_rectangle(
            box(left, top, left + card_width, top + card_height),
            radius=px(10),
            fill=(*PANEL, 224),
            outline=(*mix(accent, PANEL, 0.52), 255),
            width=px(1),
        )
        draw.rounded_rectangle(
            box(left + 12, top + 10, left + 16, top + 32),
            radius=px(2),
            fill=accent,
        )
        draw.text((px(left + 28), px(top + 8)), label, font=font(21, "semibold"), fill=TEXT)

    # Footer is separated from the content, giving it room while surviving thumbnail scale.
    draw.line((px(76), px(550), px(1204), px(550)), fill=(59, 66, 77, 150), width=px(1))
    draw.ellipse(box(76, 581, 84, 589), fill=GREEN)
    draw.ellipse(box(92, 581, 100, 589), fill=CYAN)
    draw.text(
        (px(116), px(568)),
        "8 tasks x 10 levels  ·  procedurally generated from a seed  ·  MIT",
        font=font(21, "semibold"),
        fill=MUTED,
    )


def build() -> Path:
    image = Image.new("RGBA", SIZE, (*BACKGROUND, 255))
    add_background_depth(image)
    add_mascot_stage(image)
    add_text_and_categories(image)
    image = image.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    image.save(OUTPUT_PATH, "PNG", optimize=True)
    return OUTPUT_PATH


if __name__ == "__main__":
    print(build())
