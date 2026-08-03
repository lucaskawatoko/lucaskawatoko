#!/usr/bin/env python3
"""Gera a animação "ASTRO COMMITS" para o README do perfil.

Estilo Asteroids dos anos 90: uma nave fica no centro da arena enquanto os
commits do grid de contribuições viram cometas que convergem pra cima dela.
A nave gira, atira com laser e explode cada cometa, com placa de SCORE
somando as contribuições reais destruídas.

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
# Cenário (arena espacial)
# --------------------------------------------------------------------------
WEEKS = 53
DAYS = 7

WIDTH = 700
HEIGHT = 420
CX = WIDTH // 2
CY = HEIGHT // 2

R0 = 196           # raio em que os cometas nascem (borda da arena)
RH_BASE = 64       # raio mínimo de destruição (perto da nave)
TRAVEL = 20        # frames que cada cometa leva da borda até o impacto
EXPLOSION_MS = 12  # frames de duração de cada explosão

FPS = 24
INTRO = 18       # frames de título
OUTRO = 14       # frames finais (fade + reinício)

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
# Cenário estático: espaço + estrelas + grade tênue + scanlines
# --------------------------------------------------------------------------
def build_background() -> Image.Image:
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG + (255,))
    draw = ImageDraw.Draw(img)

    for x in range(0, WIDTH, 28):
        draw.line([(x, 0), (x, HEIGHT)], fill=GRID_LINE + (70,), width=1)
    for y in range(0, HEIGHT, 28):
        draw.line([(0, y), (WIDTH, y)], fill=GRID_LINE + (70,), width=1)

    rng = random.Random(11)
    for _ in range(110):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, HEIGHT - 1)
        alpha = rng.randint(30, 150)
        color = STAR if rng.random() < 0.85 else CYAN
        draw.ellipse((x, y, x + 1, y + 1), fill=color + (alpha,))

    for y in range(0, HEIGHT, 3):
        draw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, 22), width=1)

    return img


# --------------------------------------------------------------------------
# Nave ao centro (Asteroids)
# --------------------------------------------------------------------------
def ship_points(cx: float, cy: float, ang: float) -> tuple[tuple, tuple, tuple, tuple]:
    nose = (cx + 22 * math.cos(ang), cy + 22 * math.sin(ang))
    bl = (cx + 14 * math.cos(ang + 2.45), cy + 14 * math.sin(ang + 2.45))
    br = (cx + 14 * math.cos(ang - 2.45), cy + 14 * math.sin(ang - 2.45))
    rear = (cx + 6 * math.cos(ang + math.pi), cy + 6 * math.sin(ang + math.pi))
    return nose, bl, rear, br


def draw_ship(draw: ImageDraw.ImageDraw, ang: float, i: int) -> tuple[float, float]:
    nose, bl, rear, br = ship_points(CX, CY, ang)
    draw.polygon([nose, bl, rear, br], fill=(13, 22, 44), outline=CYAN)
    cockpit = (CX + 10 * math.cos(ang), CY + 10 * math.sin(ang))
    draw.ellipse((cockpit[0] - 2, cockpit[1] - 2, cockpit[0] + 2, cockpit[1] + 2),
                 fill=(80, 255, 220))
    flame = 8 + 4 * math.sin(i * 0.9)
    fx, fy = -math.cos(ang), -math.sin(ang)
    px, py = -fy, fx
    tip = (rear[0] + fx * flame, rear[1] + fy * flame)
    draw.polygon([rear,
                  (rear[0] + px * 3, rear[1] + py * 3),
                  tip,
                  (rear[0] - px * 3, rear[1] - py * 3)],
                 fill=ORANGE)
    return nose


# --------------------------------------------------------------------------
# Cometa (núcleo + cauda apontando pra fora)
# --------------------------------------------------------------------------
def draw_comet(overlay: Image.Image, cx: float, cy: float,
               theta: float, level: int) -> None:
    draw = ImageDraw.Draw(overlay)
    tail = 8 + 4 * level
    for seg in range(3):
        a0, a1 = 0.25 * seg, 0.25 * (seg + 1)
        x0 = cx + math.cos(theta) * tail * a0
        y0 = cy + math.sin(theta) * tail * a0
        x1 = cx + math.cos(theta) * tail * a1
        y1 = cy + math.sin(theta) * tail * a1
        alpha = int(150 * (1 - seg * 0.28))
        draw.line((x0, y0, x1, y1), fill=LEVELS[level] + (alpha,), width=1)
    draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=(255, 255, 255, 230))
    draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3),
                 outline=LEVELS[level] + (170,))


# --------------------------------------------------------------------------
# Laser (bolinha de energia que viaja até o alvo)
# --------------------------------------------------------------------------
def draw_laser(overlay: Image.Image, nose: tuple[float, float],
               target: tuple[float, float], p: float) -> None:
    draw = ImageDraw.Draw(overlay)
    hx = nose[0] + (target[0] - nose[0]) * p
    hy = nose[1] + (target[1] - nose[1]) * p
    dx, dy = target[0] - nose[0], target[1] - nose[1]
    d = math.hypot(dx, dy) or 1
    ux, uy = dx / d, dy / d
    bx, by = hx - ux * 10, hy - uy * 10
    draw.line((bx, by, hx, hy), fill=CYAN + (220,), width=1)
    draw.ellipse((hx - 2, hy - 2, hx + 2, hy + 2), fill=(255, 255, 255, 240))


# --------------------------------------------------------------------------
# Explosão pixelada
# --------------------------------------------------------------------------
def draw_explosion(overlay: Image.Image, pos: tuple[float, float],
                   level: int, age: float, seed: int) -> None:
    draw = ImageDraw.Draw(overlay)
    t = min(1.0, age / EXPLOSION_MS)
    cx, cy = pos
    r = 2 + 7 * t
    draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                 fill=(255, 255, 255, int(190 * (1 - t))))
    for k in range(7):
        angle = seed * 2.399 + k * 2.399
        dist = 3 + 13 * t
        px = cx + math.cos(angle) * dist
        py = cy + math.sin(angle) * dist
        color = LEVELS[level] if k % 3 else ORANGE
        size = 2 if k % 2 else 1
        alpha = int(220 * (1 - t))
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
    draw.text((24, 78), f"CONTRIB: {score}", font=font_s,
              fill=(150, 160, 180, 255))
    if i < INTRO:
        title = "ASTRO COMMITS"
        tw = draw.textlength(title, font=font_l)
        draw.text(((WIDTH - tw) / 2, 16), title, font=font_l,
                  fill=YELLOW + (255,))
        sub = "os commits vêm pra cima de você!"
        sw = draw.textlength(sub, font=font_s)
        draw.text(((WIDTH - sw) / 2, 46), sub, font=font_s,
                  fill=CYAN + (200,))


# --------------------------------------------------------------------------
# Preparação dos cometas (ordem dos dias de contribuição)
# --------------------------------------------------------------------------
def build_comets(counts: list[tuple[int, int]]) -> list[dict]:
    rng = random.Random(7)
    comets: list[dict] = []
    cell_idx = 0
    for level, count in counts:
        if level <= 0:
            cell_idx += 1
            continue
        theta = rng.uniform(0, 2 * math.pi)
        rh = RH_BASE + (cell_idx % 5) * 13
        comets.append({
            "idx": cell_idx,
            "theta": theta,
            "level": level,
            "count": count,
            "ts": INTRO + len(comets),
            "rh": rh,
            "speed": (R0 - rh) / TRAVEL,
            "hit_pos": (CX + math.cos(theta) * rh,
                        CY + math.sin(theta) * rh),
        })
        cell_idx += 1
    return comets


def comet_pos(comet: dict, i: float) -> tuple[float, float]:
    r = R0 - comet["speed"] * i
    return (CX + math.cos(comet["theta"]) * r,
            CY + math.sin(comet["theta"]) * r)


def closest_angle(cur: float, target: float) -> float:
    d = (target - cur + math.pi) % (2 * math.pi) - math.pi
    return d


# --------------------------------------------------------------------------
# Renderização do GIF
# --------------------------------------------------------------------------
def render(counts: list[tuple[int, int]], output: str, preview: bool) -> None:
    background = build_background()
    comets = build_comets(counts)
    n_active = len(comets)
    FIRING = max(1, n_active)
    TOTAL = INTRO + FIRING + TRAVEL + EXPLOSION_MS + OUTRO

    font_s = load_font(14)
    font_l = load_font(20)
    frames: list[Image.Image] = []

    cur_angle = -math.pi / 2
    for i in range(TOTAL):
        frame = background.copy()
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

        # alvo: primeiro cometa vivo (menor ts => será atingido primeiro)
        target = None
        for c in comets:
            t = i - c["ts"]
            if 0 <= t < TRAVEL:
                target = c
                break

        # rotação da nave
        if target is not None:
            tx, ty = comet_pos(target, i - target["ts"])
            wanted = math.atan2(ty - CY, tx - CX)
            d = closest_angle(cur_angle, wanted)
            cur_angle += d * 0.30
            if abs(d) < 0.05:
                cur_angle = wanted
        else:
            cur_angle += 0.015

        draw = ImageDraw.Draw(frame)
        nose = draw_ship(draw, cur_angle, i)

        for c in comets:
            t = i - c["ts"]
            if 0 <= t < TRAVEL:
                px, py = comet_pos(c, t)
                draw_comet(overlay, px, py, c["theta"], c["level"])
            elif TRAVEL <= t < TRAVEL + EXPLOSION_MS:
                draw_explosion(overlay, c["hit_pos"], c["level"],
                               t - TRAVEL, c["idx"])

        if target is not None:
            p = (i - target["ts"]) / TRAVEL
            draw_laser(overlay, nose, comet_pos(target, i - target["ts"]), p)

        score = sum(c["count"] for c in comets if (i - c["ts"]) >= TRAVEL)
        draw_hud(frame, score, i, font_s, font_l)

        frame = Image.alpha_composite(frame, overlay).convert("RGB")

        if i >= TOTAL - OUTRO:
            t = (i - (TOTAL - OUTRO)) / OUTRO
            black = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            frame = Image.blend(frame, black, min(1.0, t * 1.05))

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
