"""Build the scribble bubble frames: the user's cloud with a pixel-art tangle that spins (dizzy buddy).

Usage: .venv/bin/python tools/make_scribble_bubble.py
Reads  buddy/assets/bubbles/scribble.png: the user's drawing (any size; shrunk to 40x32) or a previous
       output of this script. Only its cloud is kept.
Writes buddy/assets/bubbles/scribble.png and scribble_1..5.png: the tangle turning a little each frame.
"""
import math
from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"
SIZE = (40, 32)
CLEAR = (0, 0, 0, 0)
INK = (4, 4, 6, 255)
WHITE = (254, 254, 254, 255)
SHADE = (208, 207, 239, 255)
TANGLE_AREA = (9, 5, 31, 23)  # inside the cloud: wiped, then the tangle is drawn here
CENTER = (20.0, 13.5)
FRAMES = 6
LOOPS = 5


def shrink(src: Image.Image) -> Image.Image:
    """Cell-by-cell: mostly transparent -> clear, enough dark ink -> outline, else white or shade."""
    if src.size == SIZE:
        return src.copy()
    left, top, right, bottom = src.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox()
    cw, ch = (right - left) / SIZE[0], (bottom - top) / SIZE[1]
    px = src.load()
    out = Image.new("RGBA", SIZE, CLEAR)
    for j in range(SIZE[1]):
        for i in range(SIZE[0]):
            cells = [px[x, y] for y in range(int(top + j * ch), int(top + (j + 1) * ch))
                     for x in range(int(left + i * cw), int(left + (i + 1) * cw))]
            solid = [p for p in cells if p[3] > 128]
            if len(solid) < len(cells) / 2:
                continue
            dark = sum(1 for p in solid if max(p[:3]) < 90)
            shade = sum(1 for p in solid if max(p[:3]) >= 90 and p[2] > p[0] + 12)
            if dark >= 0.3 * len(cells):
                out.putpixel((i, j), INK)
            else:
                out.putpixel((i, j), SHADE if shade >= 0.4 * (len(solid) - dark) else WHITE)
    return out


def clean_cloud(im: Image.Image) -> Image.Image:
    """One-pixel outline (ink touching the outside), and an empty white middle for the tangle."""
    im = im.copy()
    px = im.load()
    w, h = im.size

    def outside(x, y):
        return not (0 <= x < w and 0 <= y < h) or px[x, y][3] == 0

    def on_edge(x, y):
        return any(outside(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))

    x0, y0, x1, y1 = TANGLE_AREA
    for y in range(h):
        for x in range(w):
            if px[x, y][3] == 0 or on_edge(x, y):
                continue
            if px[x, y] == INK or (x0 <= x < x1 and y0 <= y < y1):
                px[x, y] = WHITE
    return im


def ring(cx: float, cy: float, rx: float, ry: float) -> set[tuple[int, int]]:
    steps = 400
    return {(round(cx + rx * math.cos(2 * math.pi * n / steps)), round(cy + ry * math.sin(2 * math.pi * n / steps)))
            for n in range(steps)}


def tangle(frame: int) -> set[tuple[int, int]]:
    """A ball of overlapping loops (like the drawing), turning a little each frame. The loops are equal
    and evenly spread, so after FRAMES steps they are back where they started: the animation loops."""
    turn = 2 * math.pi / LOOPS * frame / FRAMES
    cells = set()
    for k in range(LOOPS):
        a = turn + 2 * math.pi * k / LOOPS
        cells |= ring(CENTER[0] + 4.8 * math.cos(a), CENTER[1] + 3.7 * math.sin(a), 4.3, 3.5)
    return cells


def draw(cloud: Image.Image, cells: set[tuple[int, int]]) -> Image.Image:
    im = cloud.copy()
    for cell in cells:
        im.putpixel(cell, INK)
    return im


def main() -> None:
    cloud = clean_cloud(shrink(Image.open(BUBBLES / "scribble.png").convert("RGBA")))
    for i in range(FRAMES):
        frame = draw(cloud, tangle(i))
        frame.save(BUBBLES / ("scribble.png" if i == 0 else f"scribble_{i}.png"))


if __name__ == "__main__":
    main()
