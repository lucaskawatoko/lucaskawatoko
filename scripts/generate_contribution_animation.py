#!/usr/bin/env python3
"""Gera a animação do buraco negro devorando os commits do perfil.

Uma singularidade no grid de contribuições suga os bloquinhos um a um: uma
frente de consumo varre o grid da esquerda para a direita e cada célula é
puxada numa espiral (spaghettification), acelerando, esticando e brilhando
até ser absorvida pelo anel de acreção.

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
BOTTOM_PAD = 64  # espaço extra abaixo do grid para o disco do buraco negro

WIDTH = GRID_W + 2 * PAD
HEIGHT = GRID_TOP + GRID_H + BOTTOM_PAD

FPS = 24
STEP = 8          # px por frame no deslocamento da frente de consumo
CONSUME = 90      # largura da frente que "engole" cada coluna
OUTRO_FRAMES = 18  # frames finais em que o grid "regenera"

# --------------------------------------------------------------------------
# Buraco negro (posição relativa à grade) e paleta "cosmos"
# --------------------------------------------------------------------------
BH_X = PAD + GRID_W / 2
BH_Y = GRID_TOP + GRID_H + 16
EVENT_HORIZON = 13  # raio em que a célula é absorvida

BG_TOP = (10, 12, 20)
BG_BOTTOM = (1, 2, 6)
EMPTY_CELL = (22, 27, 34)
LEVELS = {
    1: (15, 70, 66),
    2: (21, 118, 100),
    3: (28, 165, 134),
    4: (45, 226, 183),
}
GOLD = (255, 205, 120)
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


def build_counts(days: list[tuple[str, int]]) -> list[list[int]]:
    counts = [[0] * DAYS for _ in range(WEEKS)]
    for week_idx in range(WEEKS):
        for day_idx in range(DAYS):
            pos = week_idx * DAYS + day_idx
            if pos < len(days):
                counts[week_idx][day_idx] = level_for(days[pos][1])
    return counts


# --------------------------------------------------------------------------
# Fundo estático: gradiente + nebulosas + estrelas
# --------------------------------------------------------------------------
def build_background() -> Image.Image:
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_BOTTOM + (255,))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
        draw.line([(0, y), (WIDTH, y)], fill=color + (255,))
    return img


def _radial_glow(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: int,
                 color: tuple[int, int, int], peak: int) -> None:
    for r in range(radius, 0, -1):
        alpha = int((1 - r / radius) * peak)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (alpha,))


def build_nebula_layer() -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    _radial_glow(draw, 90, 60, 210, (74, 62, 158), 16)
    _radial_glow(draw, WIDTH - 120, 90, 200, (30, 130, 160), 14)
    return layer


def build_star_layer() -> Image.Image:
    rng = random.Random(7)
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for _ in range(150):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, GRID_TOP - 20)
        alpha = rng.randint(50, 200)
        radius = rng.choice((1, 1, 1, 2))
        color = STAR if rng.random() < 0.85 else GOLD
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     fill=color + (alpha,))
    for _ in range(8):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(10, GRID_TOP - 40)
        alpha = rng.randint(80, 160)
        r = 1.6
        draw.line([(x - 3, y), (x + 3, y)], fill=STAR + (alpha,), width=1)
        draw.line([(x, y - 3), (x, y + 3)], fill=STAR + (alpha,), width=1)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=STAR + (alpha + 40,))
    return layer


# --------------------------------------------------------------------------
# Grade de contribuições
# --------------------------------------------------------------------------
def draw_panel(draw: ImageDraw.ImageDraw) -> None:
    x0 = PAD - 5
    y0 = GRID_TOP - 5
    x1 = PAD + GRID_W + 5
    y1 = GRID_TOP + GRID_H + 5
    draw.rounded_rectangle((x0, y0, x1, y1), radius=8,
                           outline=(48, 54, 61, 150), width=1)


# --------------------------------------------------------------------------
# Buraco negro: horizonte de eventos + anel de acreção
# --------------------------------------------------------------------------
def draw_black_hole(overlay: Image.Image, frame_i: int) -> None:
    draw = ImageDraw.Draw(overlay)
    pulse = 1 + 0.06 * math.sin(frame_i * 0.35)
    tilt = 0.72  # achatamento do disco (perspectiva)

    def ring(rx: float, alpha: int, color: tuple[int, int, int],
             width: int) -> None:
        r = rx * pulse
        draw.ellipse((BH_X - r, BH_Y - r * tilt,
                      BH_X + r, BH_Y + r * tilt),
                     outline=color + (alpha,), width=width)

    ring(40, 14, (255, 190, 110), 10)
    ring(26, 90, (255, 185, 105), 7)
    ring(19, 150, (255, 215, 150), 4)
    ring(15, 220, (255, 240, 210), 2)

    # Partículas quentes em órbita (anel "irradiado")
    for i in range(3):
        a = frame_i * 0.5 + i * (2 * math.pi / 3)
        px = BH_X + math.cos(a) * 21
        py = BH_Y + math.sin(a) * 21 * tilt
        alpha = int(170 + 70 * math.sin(frame_i * 0.9 + i))
        draw.ellipse((px - 2, py - 2, px + 2, py + 2),
                     fill=(255, 235, 190, alpha))

    # Horizonte de eventos
    r = EVENT_HORIZON
    draw.ellipse((BH_X - r, BH_Y - r, BH_X + r, BH_Y + r),
                 fill=(0, 0, 0, 255))
    draw.ellipse((BH_X - r, BH_Y - r, BH_X + r, BH_Y + r),
                 outline=(255, 255, 255, 200), width=1)


# --------------------------------------------------------------------------
# Frente de consumo e vórtice espiral (spaghettification)
# --------------------------------------------------------------------------
def draw_front(overlay: Image.Image, bx: float) -> None:
    draw = ImageDraw.Draw(overlay)
    if bx < PAD - 4 or bx > PAD + GRID_W + 4:
        return
    draw.line([(bx, GRID_TOP), (bx, GRID_TOP + GRID_H)],
              fill=GOLD + (36,), width=2)
    for off, alpha in ((3, 22), (6, 12), (10, 8)):
        draw.line([(bx - off, GRID_TOP), (bx - off, GRID_TOP + GRID_H)],
                  fill=GOLD + (alpha,), width=2)
        draw.line([(bx + off, GRID_TOP), (bx + off, GRID_TOP + GRID_H)],
                  fill=GOLD + (alpha,), width=2)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int],
          t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def cell_geometry() -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    for w in range(WEEKS):
        for d in range(DAYS):
            gx = PAD + w * (CELL + GAP)
            gy = GRID_TOP + d * (CELL + GAP)
            centers.append((gx + CELL / 2, gy + CELL / 2))
    return centers


def flat_levels(counts: list[list[int]]) -> list[int]:
    return [counts[w][d] for w in range(WEEKS) for d in range(DAYS)]


def draw_grid(draw: ImageDraw.ImageDraw, levels: list[int],
              centers: list[tuple[float, float]],
              pvals: list[float]) -> None:
    for (cx, cy), level, p in zip(centers, levels, pvals):
        gx = cx - CELL / 2
        gy = cy - CELL / 2
        full = LEVELS[level] if level > 0 else EMPTY_CELL
        if p > 0.6:
            t = min(1.0, (p - 0.6) / 0.4)
            full = _lerp(full, EMPTY_CELL, t)
        draw.rectangle((gx, gy, gx + CELL - 1, gy + CELL - 1), fill=full)


def consumption(cells: list[tuple[float, float]], bx: float,
                outro: float) -> list[float]:
    return [max(0.0, min(1.0, (bx - cx) / CONSUME)) * outro
            for cx, _ in cells]


def draw_vortex(overlay: Image.Image, levels: list[int],
                centers: list[tuple[float, float]],
                pvals: list[float]) -> None:
    draw = ImageDraw.Draw(overlay)
    for (cx, cy), level, p in zip(centers, levels, pvals):
        if p <= 0 or p >= 1:
            continue

        dx = cx - BH_X
        dy = cy - BH_Y
        r0 = math.hypot(dx, dy)
        if r0 <= EVENT_HORIZON:
            continue
        theta0 = math.atan2(dy, dx)

        tt = p
        r = r0 * (1 - tt ** 1.6)
        if r <= 3:
            continue
        theta = theta0 + 4.6 * tt * tt
        x = BH_X + r * math.cos(theta)
        y = BH_Y + r * math.sin(theta)

        # Estica na direção tangencial (spaghettification)
        tx = -math.sin(theta)
        ty = math.cos(theta)
        length = CELL * (1 + 1.6 * tt)
        width = max(1, round(CELL * (1 - 0.55 * tt)))

        fade = max(0.0, min(1.0, (r - 4) / 9))
        base = LEVELS[level] if level > 0 else (60, 90, 85)
        color = _lerp(base, GOLD, min(1.0, tt * 1.25))
        color = _lerp(color, (255, 245, 225), max(0.0, tt - 0.75))
        alpha = int(255 * fade)

        draw.line((x - tx * length / 2, y - ty * length / 2,
                   x + tx * length / 2, y + ty * length / 2),
                  fill=color + (alpha,), width=width)
        core = 1.5 + 2.2 * tt
        draw.ellipse((x - core, y - core, x + core, y + core),
                     fill=(255, 255, 255, alpha))
        glow = 4 + 5 * tt
        draw.ellipse((x - glow, y - glow, x + glow, y + glow),
                     fill=GOLD + (int(alpha * 0.28),))


# --------------------------------------------------------------------------
# Renderização do GIF
# --------------------------------------------------------------------------
def render(counts: list[list[int]], output: str, preview: bool) -> None:
    background = build_background()
    star_layer = build_star_layer()
    nebula_layer = build_nebula_layer()
    centers = cell_geometry()
    levels = flat_levels(counts)

    consume_frames = math.ceil((WIDTH + 80) / STEP)
    total = consume_frames + OUTRO_FRAMES
    frames: list[Image.Image] = []

    for i in range(total):
        if i < consume_frames:
            bx = -40 + i * STEP
        else:
            bx = -40 + consume_frames * STEP
        outro = min(1.0, max(0.0, 1.0 - (i - consume_frames) / OUTRO_FRAMES))
        pvals = consumption(centers, bx, outro)

        base = background.copy()
        base = Image.alpha_composite(base, nebula_layer)
        base = Image.alpha_composite(base, star_layer)
        draw = ImageDraw.Draw(base)
        draw_panel(draw)
        draw_grid(draw, levels, centers, pvals)

        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw_black_hole(overlay, i)
        draw_front(overlay, bx)
        draw_vortex(overlay, levels, centers, pvals)

        frame = Image.alpha_composite(base, overlay).convert("RGB")
        frames.append(frame.quantize(colors=128, method=Image.FASTOCTREE))

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
