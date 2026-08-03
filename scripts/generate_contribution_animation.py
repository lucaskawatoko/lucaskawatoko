#!/usr/bin/env python3
"""Gera a animação "ASTRO REPOS" para o README do perfil.

Estilo Asteroids dos anos 90: uma nave fica no centro da arena enquanto os
repositórios públicos do usuário viram cometas que convergem pra cima dela.
A nave gira, atira com laser e explode cada cometa, com placa de SCORE
contando os repositórios destruídos. Cometas maiores = repositórios maiores
(tamanho em KB, por ranking) e o nome do alvo aparece no canto superior.

Qualquer usuário pode usar: o nome é resolvido via --username, env GH_USER
ou o padrão deste repositório.

Uso:
    python scripts/generate_contribution_animation.py [--mock] [--output PATH] [--username USUARIO]

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
WIDTH = 700
HEIGHT = 420
CX = WIDTH // 2
CY = HEIGHT // 2

R0 = 196           # raio em que os cometas nascem (borda da arena)
RH_BASE = 64       # raio mínimo de destruição (perto da nave)
TRAVEL = 40        # frames que cada cometa leva da borda até o impacto
EXPLOSION_MS = 12  # frames de duração de cada explosão

FPS = 24
INTRO = 18            # frames de título
OUTRO = 14            # frames finais (fade + reinício)
TARGET_TOTAL = 210    # duração alvo do loop em frames (~8,7s)
FIRING_SPAN = TARGET_TOTAL - INTRO - OUTRO - TRAVEL - EXPLOSION_MS

# --------------------------------------------------------------------------
# Paleta retrô
# --------------------------------------------------------------------------
BG = (5, 8, 16)
GRID_LINE = (24, 34, 56)
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
# Busca de repositórios públicos via GitHub GraphQL
# --------------------------------------------------------------------------
def fetch_repos(token: str, login: str) -> list[dict]:
    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(privacy: PUBLIC, affiliations: OWNER, first: 100) {
          totalCount
          nodes {
            name
            stargazerCount
            diskUsage
          }
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"login": login}}).encode()
    req = Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "astrogifs",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Falha ao buscar repositórios via GraphQL: {exc}") from exc

    if "errors" in data:
        raise SystemExit(f"Erro da API GraphQL: {data['errors']}")

    nodes = data["data"]["user"]["repositories"]["nodes"] or []
    return rank_repos(nodes)


def rank_repos(nodes: list[dict]) -> list[dict]:
    """Ordena por tamanho (KB) e atribui nível 1-4 por ranking."""
    repos = [{
        "name": n["name"],
        "stars": n["stargazerCount"] or 0,
        "size": n["diskUsage"] or 0,
    } for n in nodes]
    repos.sort(key=lambda r: r["size"], reverse=True)
    total = len(repos)
    for i, repo in enumerate(repos):
        repo["level"] = 1 + min(3, (i * 4) // max(1, total)) if total else 1
    return repos


def mock_repos() -> list[dict]:
    names = [
        "api-orders", "django-blog", "portfolio", "todo-api", "pomodoro-cli",
        "infra-docs", "ml-notebooks", "ecommerce-api", "pixel-art", "dotfiles",
        "web-scraper", "financas-cli", "imgs-utils", "nest-crm", "scripts",
    ]
    rng = random.Random(42)
    repos = [{
        "name": name,
        "stargazerCount": rng.randint(0, 30),
        "diskUsage": rng.randint(100, 40000),
    } for name in names]
    return rank_repos(repos)


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
# Cometa (núcleo + cauda apontando pra fora; maior = repositório maior)
# --------------------------------------------------------------------------
def draw_comet(overlay: Image.Image, cx: float, cy: float,
               theta: float, level: int) -> None:
    draw = ImageDraw.Draw(overlay)
    tail = 8 + 5 * level
    for seg in range(4):
        a0, a1 = 0.25 * seg, 0.25 * (seg + 1)
        x0 = cx + math.cos(theta) * tail * a0
        y0 = cy + math.sin(theta) * tail * a0
        x1 = cx + math.cos(theta) * tail * a1
        y1 = cy + math.sin(theta) * tail * a1
        alpha = int(150 * (1 - seg * 0.25))
        draw.line((x0, y0, x1, y1), fill=LEVELS[level] + (alpha,), width=1)
    r = 2 + level
    draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                 outline=LEVELS[level] + (170,))
    draw.ellipse((cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1),
                 fill=(255, 255, 255, 210))


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
    r = 2 + (6 + level) * t
    draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                 fill=(255, 255, 255, int(190 * (1 - t))))
    for k in range(7):
        angle = seed * 2.399 + k * 2.399
        dist = 3 + (11 + level) * t
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
def draw_hud(frame: Image.Image, score: int, total_repos: int,
             target_name: str | None, i: int,
             font_s: ImageFont.ImageFont, font_l: ImageFont.ImageFont) -> None:
    draw = ImageDraw.Draw(frame)
    draw.text((24, 16), "SCORE", font=font_s, fill=(150, 160, 180, 255))
    draw.text((24, 38), f"{score:03d}", font=font_l, fill=GREEN + (255,))
    draw.text((24, 78), f"REPOS PÚBLICOS: {total_repos}", font=font_s,
              fill=(150, 160, 180, 255))
    if target_name:
        tw = draw.textlength(target_name, font=font_s)
        draw.text((WIDTH - 24 - tw, 16), target_name, font=font_s,
                  fill=CYAN + (255,))
    if i < INTRO:
        title = "ASTRO REPOS"
        tw = draw.textlength(title, font=font_l)
        draw.text(((WIDTH - tw) / 2, 16), title, font=font_l,
                  fill=YELLOW + (255,))
        sub = "seus repositórios viraram cometas!"
        sw = draw.textlength(sub, font=font_s)
        draw.text(((WIDTH - sw) / 2, 46), sub, font=font_s,
                  fill=CYAN + (200,))


# --------------------------------------------------------------------------
# Preparação dos cometas (um por repositório público)
# --------------------------------------------------------------------------
def build_comets(repos: list[dict]) -> list[dict]:
    rng = random.Random(7)
    n = len(repos)
    gap = max(1.0, FIRING_SPAN / max(1, n - 1)) if n > 1 else 0.0
    comets: list[dict] = []
    for i, repo in enumerate(repos):
        theta = rng.uniform(0, 2 * math.pi)
        rh = RH_BASE + (i % 5) * 13
        comets.append({
            "name": repo["name"],
            "level": repo["level"],
            "count": 1,
            "ts": INTRO + i * gap,
            "theta": theta,
            "rh": rh,
            "speed": (R0 - rh) / TRAVEL,
            "hit_pos": (CX + math.cos(theta) * rh,
                        CY + math.sin(theta) * rh),
        })
    return comets


def comet_pos(comet: dict, t: float) -> tuple[float, float]:
    r = R0 - comet["speed"] * t
    return (CX + math.cos(comet["theta"]) * r,
            CY + math.sin(comet["theta"]) * r)


def closest_angle(cur: float, target: float) -> float:
    d = (target - cur + math.pi) % (2 * math.pi) - math.pi
    return d


# --------------------------------------------------------------------------
# Renderização do GIF
# --------------------------------------------------------------------------
def render(repos: list[dict], output: str, preview: bool) -> None:
    background = build_background()
    comets = build_comets(repos)
    n = len(comets)
    last_ts = comets[-1]["ts"] if n else INTRO
    TOTAL = int(round(last_ts + TRAVEL + EXPLOSION_MS)) + OUTRO

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

        for k, c in enumerate(comets):
            t = i - c["ts"]
            if 0 <= t < TRAVEL:
                px, py = comet_pos(c, t)
                draw_comet(overlay, px, py, c["theta"], c["level"])
            elif TRAVEL <= t < TRAVEL + EXPLOSION_MS:
                draw_explosion(overlay, c["hit_pos"], c["level"],
                               t - TRAVEL, k)

        if target is not None:
            p = (i - target["ts"]) / TRAVEL
            draw_laser(overlay, nose, comet_pos(target, i - target["ts"]), p)

        score = sum(c["count"] for c in comets if (i - c["ts"]) >= TRAVEL)
        target_name = target["name"] if target else None
        draw_hud(frame, score, len(repos), target_name, i, font_s, font_l)

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
    parser.add_argument("--username", default=None,
                        help="usuário do GitHub (padrão: GH_USER ou lucaskawatoko)")
    parser.add_argument("--preview", action="store_true",
                        help="salva também um PNG do primeiro frame")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    username = args.username or os.environ.get("GH_USER") or USERNAME
    if args.mock or not token:
        if not token:
            print("Aviso: sem GH_TOKEN/GITHUB_TOKEN. Usando dados fictícios (preview).",
                  file=sys.stderr)
        repos = mock_repos()
    else:
        repos = fetch_repos(token, username)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    render(repos, args.output, args.preview)
    size = os.path.getsize(args.output) / 1024
    print(f"GIF gerado em {args.output} ({size:.0f} KB, {WIDTH}x{HEIGHT})"
          f" para @{username} ({len(repos)} repos)")


if __name__ == "__main__":
    main()
