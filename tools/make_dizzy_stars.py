"""Build the dizzy frames: three little yellow stars circling above buddy's head.

Usage: .venv/bin/python tools/make_dizzy_stars.py
Writes buddy/assets/bubbles/dizzy.png and dizzy_1..7.png. The stars travel along a flat oval (a halo
seen from the front): the ones passing in front are big, the ones behind are small. Three stars spaced
evenly means 1/3 of a turn loops seamlessly, so the frames cover that.
"""
import math
from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"
SIZE = (40, 19)
CENTER = (19.5, 8.5)
RADIUS = (14.0, 4.0)  # the oval's half width and half height
STARS = 3
FRAMES = 8
INK = (15, 14, 18, 255)  # outline, as in the other bubbles
SHINE = (255, 247, 196, 255)
YELLOW = (253, 209, 24, 255)  # the yellow of the ❓ bubble
DIM = (214, 160, 20, 255)  # behind the head
# Star shapes ("#" = filled); the outline is added around them.
FRONT = [
    "...#...",
    "...#...",
    "#######",
    ".#####.",
    "..###..",
    ".##.##.",
    ".#...#.",
]
SIDE = [
    "..#..",
    ".###.",
    "#####",
    ".###.",
    ".#.#.",
]
BACK = [
    ".#.",
    "###",
    ".#.",
]


def stamp(im: Image.Image, shape: list[str], cx: float, cy: float, color: tuple) -> None:
    left, top = round(cx - len(shape[0]) / 2), round(cy - len(shape) / 2)
    filled = {(left + i, top + j) for j, row in enumerate(shape) for i, c in enumerate(row) if c == "#"}
    outline = {(x + dx, y + dy) for x, y in filled for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - filled
    shine = (left + len(shape[0]) // 2, top + len(shape) // 2 - 1) if shape is not BACK else None
    for points, paint in ((outline, INK), (filled, color)):
        for x, y in points:
            if 0 <= x < SIZE[0] and 0 <= y < SIZE[1]:
                im.putpixel((x, y), SHINE if (x, y) == shine else paint)


def frame(step: int) -> Image.Image:
    im = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    turn = 2 * math.pi / STARS * step / FRAMES
    stars = []
    for k in range(STARS):
        angle = turn + 2 * math.pi * k / STARS
        depth = math.sin(angle)  # > 0: passing in front (lower on the oval)
        stars.append((depth, CENTER[0] + RADIUS[0] * math.cos(angle), CENTER[1] + RADIUS[1] * depth))
    for depth, x, y in sorted(stars):  # back to front
        if depth > 0.3:
            stamp(im, FRONT, x, y, YELLOW)
        elif depth > -0.5:
            stamp(im, SIDE, x, y, YELLOW)
        else:
            stamp(im, BACK, x, y, DIM)
    return im


def main() -> None:
    for step in range(FRAMES):
        frame(step).save(BUBBLES / ("dizzy.png" if step == 0 else f"dizzy_{step}.png"))


if __name__ == "__main__":
    main()
