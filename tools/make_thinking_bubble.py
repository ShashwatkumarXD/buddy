"""Build the thinking bubble frames: the user's cloud with a pixel-art open book whose page flips.

Usage: .venv/bin/python tools/make_thinking_bubble.py
Reads  buddy/assets/bubbles/thinking.png (40x32 native cloud art) — only its cloud is kept.
Writes buddy/assets/bubbles/thinking.png (book at rest) and thinking_1..3.png (page flip).
"""
from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"
WHITE = (255, 255, 255, 255)
COLORS = {
    "K": (58, 36, 26, 255),  # outline
    "C": (252, 238, 196, 255),  # page
    "S": (214, 190, 146, 255),  # text line / page shade
    "R": (176, 62, 38, 255),  # cover
    "D": (112, 38, 24, 255),  # cover shadow
}
# Left half of the open book (11 columns); the right half is its mirror image. Spine = the two middle columns.
BOOK_LEFT = [
    ".KKK.......",
    "KCCCKK.....",
    "KCCCCCKK...",
    "KCSSCCCCKKK",
    "KCCCCCCCCCK",
    "KCSSSSSCCCK",
    "KCCCCCCCCCK",
    "KCSSSSCCCCK",
    "KCCCCCCCCCK",
    "RKKCCCCCCCK",
    "RRRKKKCCCCK",
    "DRRRRRKKKKK",
    ".KKKKKKDDDK",
]
BOOK_X, BOOK_Y = 9, 8  # top-left of the 22-wide book inside the 40x32 bubble
SPINE_X = BOOK_X + 10  # left spine column; the right one is SPINE_X + 1
PAGE_TOP = BOOK_Y + 3  # top of the pages at the spine


def clean_cloud(src: Image.Image) -> Image.Image:
    """Keep the cloud outline and shading; paint everything inside it white."""
    im = src.copy()
    px = im.load()
    for y in range(3, 25):
        row = [px[x, y] for x in range(im.width)]
        dark = [x for x, p in enumerate(row) if p[3] and max(p[:3]) < 80]
        if len(dark) < 2:
            continue
        left, right = dark[0], dark[-1]
        for x in range(left + 2, right - 2):
            r, g, b, a = px[x, y]
            cloud_shading = b > r + 10 and r > 150 and (y >= 18 or x - left <= 6 or right - x <= 6)
            if a and not cloud_shading:
                px[x, y] = WHITE
    return im


def draw_book(im: Image.Image) -> Image.Image:
    im = im.copy()
    px = im.load()
    for dy, half in enumerate(BOOK_LEFT):
        for dx, ch in enumerate(half + half[::-1]):
            if ch != ".":
                px[BOOK_X + dx, BOOK_Y + dy] = COLORS[ch]
    return im


def draw_page(im: Image.Image, cells: list[tuple[int, int]]) -> Image.Image:
    """A turning page: cream cells with a dark outline around them."""
    im = im.copy()
    px = im.load()
    cells_set = set(cells)
    for x, y in cells:
        for nx, ny in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)):
            if (nx, ny) not in cells_set and px[nx, ny] in (WHITE, COLORS["C"], COLORS["S"]):
                px[nx, ny] = COLORS["K"]
    for x, y in cells:
        px[x, y] = COLORS["C"]
    return im


def turning_pages() -> list[list[tuple[int, int]]]:
    lift_right = [(SPINE_X + 1 + i, PAGE_TOP - 1 - i // 2 - j) for i in range(1, 9) for j in range(2)]
    upright = [(SPINE_X + i, PAGE_TOP - 1 - j) for i in range(2) for j in range(1, 7)]
    lift_left = [(2 * SPINE_X + 1 - x, y) for x, y in lift_right]
    return [lift_right, upright, lift_left]


def main() -> None:
    src = Image.open(BUBBLES / "thinking.png").convert("RGBA")
    rest = draw_book(clean_cloud(src))
    rest.save(BUBBLES / "thinking.png")
    for i, cells in enumerate(turning_pages(), start=1):
        draw_page(rest, cells).save(BUBBLES / f"thinking_{i}.png")


if __name__ == "__main__":
    main()
