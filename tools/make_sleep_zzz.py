"""Build the sleep frames: little "Z"s drifting up and to the right above buddy's head.

Usage: .venv/bin/python tools/make_sleep_zzz.py
Writes buddy/assets/bubbles/sleep.png and sleep_1..5.png. Each Z rises along a gently swaying path and
grows as it goes (small, medium, big, then gone). Three Zs spaced evenly along the path means 1/3 of the
journey loops seamlessly, so the frames cover that.
"""
import math
from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"
SIZE = (40, 38)
START = (14.0, 33.0)  # where a Z appears (its centre)
END = (34.0, 4.0)  # where it disappears
SWAY = 1.0  # pixels left/right along the way
ZS = 3
FRAMES = 6
INK = (15, 14, 18, 255)  # outline, as in the other bubbles
FILL = (196, 226, 255, 255)  # pale sleepy blue
# Z shapes ("#" = filled); the outline is added around them.
SMALL = [
    "####",
    "..#.",
    ".#..",
    "####",
]
MEDIUM = [
    "######",
    "....##",
    "...##.",
    "..##..",
    ".##...",
    "######",
]
BIG = [
    "#######",
    ".....##",
    "....##.",
    "...##..",
    "..##...",
    ".##....",
    "#######",
]


def stamp(im: Image.Image, shape: list[str], cx: float, cy: float) -> None:
    left, top = round(cx - len(shape[0]) / 2), round(cy - len(shape) / 2)
    filled = {(left + i, top + j) for j, row in enumerate(shape) for i, c in enumerate(row) if c == "#"}
    outline = {(x + dx, y + dy) for x, y in filled for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - filled
    for points, paint in ((outline, INK), (filled, FILL)):
        for x, y in points:
            if 0 <= x < SIZE[0] and 0 <= y < SIZE[1]:
                im.putpixel((x, y), paint)


def frame(step: int) -> Image.Image:
    im = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    for k in range(ZS):
        p = (k + step / FRAMES) / ZS  # 0 = just appeared, 1 = gone
        x = START[0] + (END[0] - START[0]) * p + SWAY * math.sin(2 * math.pi * p)
        y = START[1] + (END[1] - START[1]) * p
        stamp(im, SMALL if p < 1 / 3 else MEDIUM if p < 2 / 3 else BIG, x, y)
    return im


def main() -> None:
    for step in range(FRAMES):
        frame(step).save(BUBBLES / ("sleep.png" if step == 0 else f"sleep_{step}.png"))


if __name__ == "__main__":
    main()
