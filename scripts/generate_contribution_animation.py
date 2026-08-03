#!/usr/bin/env python3
"""Gera a animação do OVNI abduzindo commits para o README do perfil.

O OVNI sobrevoa o grid de contribuições e "abduz" as células de commits com
um raio trator, deixando um rastro vazio e estrelas pelo caminho.

Uso:
    python scripts/generate_contribution_animation.py [--mock] [--output PATH]

Requer Pillow. Para dados reais usa GH_TOKEN/GITHUB_TOKEN (GraphQL).
Sem token, gera dados fictícios (útil só para pré-visualizar localmente).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

USERNAME = "lucaskawatoko"
DEFAULT_OUTPUT = "imgs/contribution-animation.gif"

# --------------------------------------------------------------------------
# Layout do grid (escala do GitHub: 53 semanas x 7 dias)
# --------------------------------------------------------------------------
CELL = 10
GAP = 3
WEEKS = 53
DAYS = 7

GRID_W = WEEKS * CELL + (WEEKS - 1) * GAP
GRID_H = DAYS * CELL + (DAYS - 1) * GAP
PAD = 16
GRID_TOP = 150
BOTTOM_PAD = 24

WIDTH = GRID_W + 2 * PAD
HEIGHT = GRID_TOP + GRID_H + BOTTOM_PAD

FPS = 24
STEP = 9          # px por frame no deslocamento do OVNI
BW = 30           # meia largura do raio trator na altura do grid
CONSUME = 2 * BW  # distância até a célula ser totalmente abduzida
OUTRO_FRAMES = 16  # frames finais em que o grid "regenera"

# --------------------------------------------------------------------------
# Paleta "aurora espacial"
# --------------------------------------------------------------------------
BG_TOP = (13, 17, 23)
BG_BOTTOM = (1, 4, 9)
EMPTY_CELL = (22, 27, 34)
LEVELS = {
    1: (15, 70, 66),
    2: (21, 118, 100),
    3: (28, 165, 134),
    4: (45, 226, 183),
}
BEAM = (121, 192, 255)
STAR = (240, 246, 252)


# --------------------------------------------------------------------------
# Busca de contribuições via GitHub GraphQL
# --------------------------------------------------------------------------
def fetch_contributions(token: str) -> list[tuple[str, int]]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"login": USERNAME}}).encode()
    req = Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "contribution-animation",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Falha ao buscar contribuições via GraphQL: {exc}") from exc

    if "errors" in data:
        raise SystemExit(f"Erro da API GraphQL: {data['errors']}")

    calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days: list[tuple[str, int]] = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days.append((day["date"], int(day["contributionCount"])))
    return days


def mock_contributions() -> list[tuple[str, int]]:
    rng = random.Random(42)
    days: list[tuple[str, int]] = []
    for _ in range(WEEKS * DAYS):
        r = rng.random()
        if r < 0.55:
            count = 0
        elif r < 0.8:
            count = rng.randint(1, 3)
        elif r < 0.95:
            count = rng.randint(4, 9)
        else:
            count = rng.randint(10, 18)
        days.append(("", count))
    return days


def level_for(count: int) -> int:
    if count <= 0:
        return 0
    if count <= 3:
        return 1
    if count <= 7:
        return 2
    if count <= 13:
        return 3
    return 4


# --------------------------------------------------------------------------
# Elementos visuais
# --------------------------------------------------------------------------
def build_background() -> Image.Image:
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_BOTTOM + (255,))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        color = tuple(
            round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)
        )
        draw.line([(0, y), (WIDTH, y)], fill=color + (255,))
    return img


def build_star_layer() -> Image.Image:
    rng = random.Random(7)
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for _ in range(140):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, GRID_TOP - 26)
        alpha = rng.randint(50, 200)
        radius = rng.choice((1, 1, 1, 2))
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=STAR + (alpha,),
        )
    for _ in range(10):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(10, GRID_TOP - 40)
        alpha = rng.randint(80, 160)
        r = 1.6
        draw.line([(x - 3, y), (x + 3, y)], fill=STAR + (alpha,), width=1)
        draw.line([(x, y - 3), (x, y + 3)], fill=STAR + (alpha,), width=1)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=STAR + (alpha + 40,))
    planet = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(planet)
    pdraw.ellipse((WIDTH - 130, 22, WIDTH - 50, 102), fill=(47, 129, 247, 22))
    pdraw.arc(
        (WIDTH - 130, 22, WIDTH - 50, 102), 20, 160,
        fill=(121, 192, 255, 50), width=2,
    )
    layer = Image.alpha_composite(layer, planet)
    return layer


def draw_panel(draw: ImageDraw.ImageDraw) -> None:
    x0 = PAD - 5
    y0 = GRID_TOP - 5
    x1 = PAD + GRID_W + 5
    y1 = GRID_TOP + GRID_H + 5
    draw.rounded_rectangle(
        (x0, y0, x1, y1), radius=8, outline=(48, 54, 61, 140), width=1
    )


def draw_grid(
    draw: ImageDraw.ImageDraw, counts: list[list[int]]
) -> list[tuple[float, float, int]]:
    cells: list[tuple[float, float, int]] = []
    for w in range(WEEKS):
        for d in range(DAYS):
            gx = PAD + w * (CELL + GAP)
            gy = GRID_TOP + d * (CELL + GAP)
            level = counts[w][d]
            color = LEVELS[level] if level > 0 else EMPTY_CELL
            draw.rectangle((gx, gy, gx + CELL - 1, gy + CELL - 1), fill=color)
            cells.append((gx + CELL / 2, gy + CELL / 2, level))
    return cells


def draw_ufo(
    frame: Image.Image,
    overlay: Image.Image,
    bx: float,
    ufo_y: float,
    frame_i: int,
) -> None:
    draw = ImageDraw.Draw(frame)
    odraw = ImageDraw.Draw(overlay)
    bob = math.sin(frame_i * 0.45) * 3

    # Corpo da nave
    y = ufo_y + bob
    draw.ellipse((bx - 30, y - 7, bx + 30, y + 13), fill=(154, 165, 177, 255))
    draw.ellipse((bx - 30, y - 7, bx + 30, y + 13), outline=(110, 118, 129, 255), width=2)
    draw.ellipse((bx - 26, y + 4, bx + 26, y + 14), fill=(57, 63, 74, 255))

    # Luzes piscando
    blink = 1 if (frame_i // 4) % 2 == 0 else -1
    light_colors = [(255, 123, 114), (63, 185, 80), (123, 140, 255)]
    for i, cx in enumerate((-20, 0, 20)):
        color = light_colors[i] if blink > 0 else light_colors[-1 - i]
        draw.ellipse((bx + cx - 3, y + 9, bx + cx + 3, y + 15), fill=color + (255,))

    # Cúpula translúcida + alien no interior
    odraw.ellipse((bx - 13, y - 22, bx + 13, y - 2), fill=(121, 192, 255, 170))
    odraw.ellipse((bx - 6, y - 19, bx + 6, y - 9), fill=(17, 45, 42, 220))
    odraw.ellipse((bx - 3, y - 16, bx - 1, y - 13), fill=(80, 255, 220, 230))
    odraw.ellipse((bx + 1, y - 16, bx + 3, y - 13), fill=(80, 255, 220, 230))
    odraw.ellipse((bx - 8, y - 20, bx + 2, y - 15), fill=(255, 255, 255, 110))

    # Rastro de faíscas
    rng = random.Random(frame_i)
    for i, dist in enumerate((16, 34, 52, 72)):
        tx = bx - dist
        ty = y + rng.randint(-4, 10)
        alpha = int((math.sin(frame_i * 0.7 + i * 1.7) + 1) / 2 * 160)
        radius = 1 + (i % 2)
        odraw.ellipse((tx - radius, ty - radius, tx + radius, ty + radius),
                      fill=STAR + (alpha,))


def draw_beam(overlay: Image.Image, bx: float, ufo_y: float, frame_i: int) -> None:
    draw = ImageDraw.Draw(overlay)
    top_y = ufo_y + 12
    bottom_y = GRID_TOP + 8
    pulse = 0.85 + math.sin(frame_i * 0.5) * 0.15

    draw.polygon(
        [(bx - 9, top_y), (bx + 9, top_y),
         (bx + BW, bottom_y), (bx - BW, bottom_y)],
        fill=BEAM + (26,),
    )
    inner = BW * 0.55
    draw.polygon(
        [(bx - 5, top_y), (bx + 5, top_y),
         (bx + inner, bottom_y), (bx - inner, bottom_y)],
        fill=BEAM + (40,),
    )
    for scale, alpha in ((1.15, 20), (0.75, 38), (0.42, 60)):
        r = BW * scale * pulse
        draw.ellipse(
            (bx - r, GRID_TOP - 4 - r, bx + r, GRID_TOP - 4 + r),
            fill=BEAM + (alpha,),
        )


def draw_cells_effects(
    overlay: Image.Image,
    cells: list[tuple[float, float, int]],
    bx: float,
    outro: float,
) -> None:
    """Aplica brilho/abdução às células conforme o raio passa por elas."""
    draw = ImageDraw.Draw(overlay)
    for cx, cy, level in cells:
        p = (bx - cx) / CONSUME
        p = max(0.0, min(1.0, p)) * outro

        ahead = (cx - bx) / CONSUME
        if 0 < ahead <= 1:
            q = 1 - ahead
            size = CELL - 2
            draw.rectangle(
                (cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2),
                fill=(255, 255, 255, int(q * 70)),
            )

        if p <= 0:
            continue
        color = LEVELS[level] if level > 0 else EMPTY_CELL
        s = CELL * (1 - 0.4 * p)
        oy = cy - p * 48
        glow = 4 + p * 10
        draw.ellipse(
            (cx - glow, oy - glow, cx + glow, oy + glow),
            fill=color + (int((1 - p) * 120),),
        )
        draw.rectangle(
            (cx - s / 2, oy - s / 2, cx + s / 2, oy + s / 2),
            fill=color + (int((1 - p) * 235),),
        )
        core = 2.5
        draw.ellipse(
            (cx - core, oy - core, cx + core, oy + core),
            fill=(255, 255, 255, int((1 - p) * 200)),
        )


# --------------------------------------------------------------------------
# Renderização do GIF
# --------------------------------------------------------------------------
def render(
    counts: list[list[int]], output: str, preview: bool
) -> None:
    background = build_background()
    star_layer = build_star_layer()

    consume_frames = math.ceil((WIDTH + 80) / STEP)
    total = consume_frames + OUTRO_FRAMES
    frames: list[Image.Image] = []

    for i in range(total):
        base = background.copy()
        base = Image.alpha_composite(base, star_layer)
        draw = ImageDraw.Draw(base)
        draw_panel(draw)
        cells = draw_grid(draw, counts)

        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

        if i < consume_frames:
            bx = -40 + i * STEP
        else:
            bx = -40 + consume_frames * STEP

        if bx < WIDTH + 60:
            ufo_y = 82
            draw_ufo(base, overlay, bx, ufo_y, i)
            draw_beam(overlay, bx, ufo_y, i)

        outro = min(1.0, max(0.0, 1.0 - (i - consume_frames) / OUTRO_FRAMES))
        draw_cells_effects(overlay, cells, bx, outro)

        frame = Image.alpha_composite(base, overlay).convert("RGB")
        frames.append(frame)

    if preview and frames:
        frames[0].save(output.replace(".gif", ".png"))

    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=1000 // FPS,
        loop=0,
        optimize=True,
        disposal=2,
    )


# --------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------
def build_counts(days: list[tuple[str, int]]) -> list[list[int]]:
    counts = [[0] * DAYS for _ in range(WEEKS)]
    for week_idx in range(WEEKS):
        for day_idx in range(DAYS):
            pos = week_idx * DAYS + day_idx
            if pos < len(days):
                counts[week_idx][day_idx] = level_for(days[pos][1])
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true",
                        help="usa dados fictícios em vez da API")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--preview", action="store_true",
                        help="salva também um PNG do primeiro frame")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if args.mock or not token:
        if not token:
            print("Aviso: sem GH_TOKEN/GITHUB_TOKEN. Usando dados fictícios (preview).",
                  file=sys.stderr)
        days = mock_contributions()
    else:
        days = fetch_contributions(token)

    counts = build_counts(days)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    render(counts, args.output, args.preview)
    size = os.path.getsize(args.output) / 1024
    print(f"GIF gerado em {args.output} ({size:.0f} KB, {WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
