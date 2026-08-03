#!/usr/bin/env python3
"""Gera a animação arcade "COMMIT ATTACK" para o README do perfil.

Estilo jogo de nave espacial dos anos 90: cada commit do grid de
contribuições vira um cometa-alvo e a nave atira neles um a um, com
explosões pixeladas e placa de SCORE contando os commits destruídos.

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

from PIL import Image, ImageDraw, ImageFont

USERNAME = "lucaskawatoko"
DEFAULT_OUTPUT = "imgs/contribution-animation.gif"

# --------------------------------------------------------------------------
# Layout do cenário (tela do arcade)
# --------------------------------------------------------------------------
CELL = 7
GAP = 2
WEEKS = 53
DAYS = 7

GRID_W = WEEKS * CELL + (WEEKS - 1) * GAP
GRID_H = DAYS * CELL + (DAYS - 1) * GAP
WIDTH = 740
HEIGHT = 360
GRID_X = 235
GRID_Y = 149
SHIP_X = 90
SHIP_Y = 180

FPS = 24
INTRO = 24       # frames da nave entrando em cena
FIRING = 88      # frames de tiroteio (destruição bloco a bloco)
OUTRO = 20       # frames finais (fade + reinício)
EXPLOSION_MS = 12  # frames de duração de cada explosão

TOTAL = INTRO + FIRING + OUTRO

# --------------------------------------------------------------------------
# Paleta retrô
# --------------------------------------------------------------------------
BG = (5, 8, 16)
GRID_LINE = (24, 34, 56)
EMPTY_CELL = (17, 22, 34)
LEVELS = {
    1: (15, 100, 88),
    2: (21, 148, 122),
    3: (33, 200, 158),
    4: (72, 255, 210),
}
CYAN = (121, 192, 255)
GREEN = (63, 185, 80)
YELLOW = (255, 205, 90)
ORANGE = (255, 150, 70)
STAR = (210, 224, 240)


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


def flat_cells(days: list[tuple[str, int]]) -> list[tuple[int, int]]:
    """Retorna (level, contagem real) por célula, na ordem (w, d)."""
    return [(level_for(count), count) for _, count in days]


# --------------------------------------------------------------------------
# Tipografia (fonte mono retrô)
# --------------------------------------------------------------------------
def load_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf",
    )
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# --------------------------------------------------------------------------
# Cenário estático: fundo + linhas de grade retrô + estrelas + scanlines
# --------------------------------------------------------------------------
def build_background() -> Image.Image:
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG + (255,))
    draw = ImageDraw.Draw(img)

    for x in range(0, WIDTH, 28):
        draw.line([(x, 0), (x, HEIGHT)], fill=GRID_LINE + (90,), width=1)
    for y in range(0, HEIGHT, 28):
        draw.line([(0, y), (WIDTH, y)], fill=GRID_LINE + (90,), width=1)

    rng = random.Random(11)
    for _ in range(90):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, HEIGHT - 1)
        alpha = rng.randint(30, 150)
        color = STAR if rng.random() < 0.85 else CYAN
        draw.ellipse((x, y, x + 1, y + 1), fill=color + (alpha,))

    for y in range(0, HEIGHT, 3):
        draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, 22), width=1)

    return img


def draw_panel(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle(
        (GRID_X - 6, GRID_Y - 6, GRID_X + GRID_W + 6, GRID_Y + GRID_H + 6),
        radius=4, outline=CYAN + (120,), width=1,
    )


def cell_geometry() -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    for w in range(WEEKS):
        for d in range(DAYS):
            gx = GRID_X + w * (CELL + GAP) + CELL / 2
            gy = GRID_Y + d * (CELL + GAP) + CELL / 2
            centers.append((gx, gy))
    return centers


def draw_grid(draw: ImageDraw.ImageDraw,
              centers: list[tuple[float, float]],
              cells: list[tuple[int, int]],
              destroyed: set[int]) -> None:
    for idx, (cx, cy) in enumerate(centers):
        level, _ = cells[idx]
        gx = cx - CELL / 2
        gy = cy - CELL / 2
        if level == 0:
            draw.rectangle((gx, gy, gx + CELL - 1, gy + CELL - 1),
                           fill=EMPTY_CELL)
        elif idx in destroyed:
            draw.rectangle((gx, gy, gx + CELL - 1, gy + CELL - 1),
                           fill=EMPTY_CELL)
        else:
            draw.rectangle((gx, gy, gx + CELL - 1, gy + CELL - 1),
                           fill=LEVELS[level])


def draw_cell_glow(overlay: Image.Image,
                   centers: list[tuple[float, float]],
                   cells: list[tuple[int, int]],
                   destroyed: set[int]) -> None:
    draw = ImageDraw.Draw(overlay)
    for idx, (cx, cy) in enumerate(centers):
        level, _ = cells[idx]
        if level == 0 or idx in destroyed:
            continue
        r = CELL + 2
        draw.rectangle((cx - r, cy - r, cx + r, cy + r),
                       fill=LEVELS[level] + (38,))


# --------------------------------------------------------------------------
# Nave espacial
# --------------------------------------------------------------------------
def draw_ship(draw: ImageDraw.ImageDraw, frame_i: int) -> tuple[float, float]:
    bob = math.sin(frame_i * 0.4) * 3
    yy = SHIP_Y + bob
    x = SHIP_X
    draw.polygon([(x + 30, yy), (x + 8, yy + 9), (x - 18, yy + 9),
                  (x - 18, yy - 9), (x + 8, yy - 9)],
                 fill=(13, 22, 44), outline=CYAN)
    draw.polygon([(x + 8, yy - 9), (x - 8, yy - 22), (x - 6, yy - 8)],
                 fill=CYAN)
    draw.polygon([(x + 8, yy + 9), (x - 8, yy + 22), (x - 6, yy + 8)],
                 fill=CYAN)
    draw.ellipse((x + 2, yy - 3, x + 12, yy + 3), fill=(80, 255, 220))
    flame = 12 + 5 * math.sin(frame_i * 0.8)
    draw.polygon([(x - 18, yy - 4), (x - 18, yy + 4), (x - 18 - flame, yy)],
                 fill=ORANGE)
    return x + 30, yy  # ponta da nave


def draw_beam(overlay: Image.Image, nose: tuple[float, float],
              target: tuple[float, float], frame_i: int) -> None:
    draw = ImageDraw.Draw(overlay)
    x0, y0 = nose
    x1, y1 = target
    draw.line((x0, y0, x1, y1), fill=CYAN + (60,), width=5)
    draw.line((x0, y0, x1, y1), fill=(255, 255, 255, 200), width=2)
    draw.line((x0, y0, x1, y1), fill=CYAN + (255,), width=1)
    # clarão no cano da nave
    draw.ellipse((x0 - 4, y0 - 4, x0 + 4, y0 + 4),
                 fill=(255, 255, 255, 220))


# --------------------------------------------------------------------------
# Explosão pixelada
# --------------------------------------------------------------------------
def draw_explosion(overlay: Image.Image, cell_idx: int,
                   center: tuple[float, float], level: int, age: float,
                   cell_count: int) -> None:
    draw = ImageDraw.Draw(overlay)
    t = min(1.0, age / EXPLOSION_MS)
    cx, cy = center
    r = 2 + 9 * t
    draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                 fill=(255, 255, 255, int(190 * (1 - t))))
    for k in range(8):
        angle = (cell_idx * 2.399 + k * 2.513) % (2 * math.pi)
        dist = 2 + 15 * t
        px = cx + math.cos(angle) * dist
        py = cy + math.sin(angle) * dist
        color = LEVELS[level] if k % 3 else ORANGE
        alpha = int(240 * (1 - t))
        size = 2
        draw.rectangle((px - size, py - size, px + size, py + size),
                       fill=color + (alpha,))


# --------------------------------------------------------------------------
# Placas de texto
# --------------------------------------------------------------------------
def draw_hud(frame: Image.Image, score: int, i: int, font_s: ImageFont.ImageFont,
             font_l: ImageFont.ImageFont) -> None:
    draw = ImageDraw.Draw(frame)
    draw.text((24, 16), "SCORE", font=font_s, fill=(150, 160, 180, 255))
    draw.text((24, 38), f"{score:05d}", font=font_l, fill=GREEN + (255,))
    draw.text((24, 78), f"COMMITS: {score}", font=font_s,
              fill=(150, 160, 180, 255))
    if i < INTRO:
        title = "COMMIT ATTACK"
        tw = draw.textlength(title, font=font_l)
        draw.text(((WIDTH - tw) / 2, 18), title, font=font_l,
                  fill=YELLOW + (255,))
        sub = "desvie dos cometas!"
        sw = draw.textlength(sub, font=font_s)
        draw.text(((WIDTH - sw) / 2, 48), sub, font=font_s,
                  fill=CYAN + (200,))


# --------------------------------------------------------------------------
# Renderização do GIF
# --------------------------------------------------------------------------
def render(counts: list[tuple[int, int]], output: str, preview: bool) -> None:
    background = build_background()
    centers = cell_geometry()
    active: list[dict] = []
    for idx, (level, count) in enumerate(counts):
        if level > 0:
            active.append({
                "idx": idx,
                "center": centers[idx],
                "level": level,
                "count": count,
            })
    n_active = len(active)
    font_s = load_font(14)
    font_l = load_font(20)
    frames: list[Image.Image] = []

    for i in range(TOTAL):
        frame = background.copy()

        if i < INTRO:
            n_hit = 0
            destroyed: set[int] = set()
            target: dict | None = None
        elif i < INTRO + FIRING:
            p = (i - INTRO) / FIRING
            n_hit = min(n_active, round(p * n_active))
            destroyed = {a["idx"] for a in active[:n_hit]}
            target = active[min(n_hit, n_active - 1)] if n_hit < n_active else None
        else:
            n_hit = n_active
            destroyed = {a["idx"] for a in active}
            target = None

        draw = ImageDraw.Draw(frame)
        draw_panel(draw)
        draw_grid(draw, centers, counts, destroyed)

        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw_cell_glow(overlay, centers, counts, destroyed)

        nose = draw_ship(draw, i)
        if target is not None:
            draw_beam(overlay, nose, target["center"], i)

        # Explosões (continuam no OUTRO até terminarem)
        if i >= INTRO:
            for k, a in enumerate(active):
                age = (i - INTRO) - k * (FIRING / n_active)
                if 0 <= age < EXPLOSION_MS:
                    draw_explosion(overlay, a["idx"], a["center"],
                                   a["level"], age, n_active)

        # Placa de score
        score = 0
        if i >= INTRO:
            for k, a in enumerate(active):
                age = (i - INTRO) - k * (FIRING / n_active)
                if age >= EXPLOSION_MS:
                    score += a["count"]
        draw_hud(frame, score, i, font_s, font_l)

        frame = Image.alpha_composite(frame, overlay).convert("RGB")

        # Fade de reinício no OUTRO
        if i >= INTRO + FIRING:
            t = (i - INTRO - FIRING) / OUTRO
            black = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            frame = Image.blend(frame, black, min(1.0, t * 1.1))

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

    counts = flat_cells(days)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    render(counts, args.output, args.preview)
    size = os.path.getsize(args.output) / 1024
    print(f"GIF gerado em {args.output} ({size:.0f} KB, {WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
