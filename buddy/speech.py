"""Speech bubbles with words in them: a pixel cloud sized to the text, plus a little animation per style.

    frames(style, text) -> [(image, milliseconds), ...]

Styles:
  quote    – the words in a still cloud
  type     – the words type themselves out
  sparkle  – typed out while sparkles twinkle round the cloud ("Hi beautiful!")
  rizz     – typed out while little hearts float up
  wave     – a waving hand beside the words ("Hi!")
  smile    – a smiley that blinks and grins beside the words
An Animation plays through once, then loops its frames from `loop_from` on (a one-frame tail just holds).
"""
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from buddy import pixelfont
from buddy.timing import frame_at

INK = (15, 14, 18, 255)  # outline, as in the other bubbles
FILL = (255, 255, 255, 255)
SHADE = (215, 212, 248, 255)  # lilac underside of the cloud
TEXT = (52, 40, 64, 255)
WRAP = {"quote": 96}  # widest line in pixels; everything else wraps at DEFAULT_WRAP
DEFAULT_WRAP = 84
PAD_X, PAD_Y = 8, 6  # cloud edge to text
MARGIN = 7  # room round the cloud for sparkles and hearts
TAIL = 6  # rows the tail hangs below the cloud
TYPE_MS = 55  # per letter
HOLD_MS = 1200

PALETTE = {
    "K": INK,
    "S": (255, 212, 160, 255),  # skin
    "D": (226, 160, 112, 255),  # skin shade
    "Y": (255, 214, 64, 255),  # smiley / sparkle
    "O": (232, 160, 32, 255),  # smiley shade
    "P": (240, 110, 140, 255),  # cheeks, tongue, hearts
    "W": (255, 255, 255, 255),
}
HAND = [
    ".KK.KK.KK.....",
    "KSSKSSKSSK....",
    "KSSKSSKSSK.KK.",
    "KSSKSSKSSKKSSK",
    "KSSSSSSSSSKSDK",
    "KSSSSSSSSSSSK.",
    "KSSSSSSSSSSDK.",
    ".KSSSSSSSSSDK.",
    ".KSSSSSSSSDK..",
    "..KSSSSSSDK...",
    "...KKKKKKK....",
]
SMILEY = [
    "...KKKKK...",
    ".KKYYYYYKK.",
    ".KYYYYYYYK.",
    "KYYKYYYKYYK",
    "KYYKYYYKYYK",
    "KPYYYYYYYPK",
    "KYKYYYYYKYK",
    "KYYKKKKKYOK",
    ".KYYYYYYOK.",
    ".KKYYYYOKK.",
    "...KKKKK...",
]
SMILEY_BLINK = SMILEY[:3] + ["KYYYYYYYYYK", "KYKKYYYKKYK"] + SMILEY[5:]
SMILEY_GRIN = SMILEY[:5] + [
    "KPYYYYYYYPK",
    "KYKKKKKKKYK",
    "KYYKPPPKYOK",
    ".KYYKKKYOK.",
] + SMILEY[9:]
SPARKLE_SMALL = ["..Y..", ".YYY.", "YYWYY", ".YYY.", "..Y.."]
SPARKLE_BIG = ["...Y...", "...Y...", "..YYY..", "YYYWYYY", "..YYY..", "...Y...", "...Y..."]
HEART = [".PP.PP.", "PWPPPPP", "PPPPPPP", ".PPPPP.", "..PPP..", "...P..."]


@dataclass
class Animation:
    images: list
    durations: list[int]  # milliseconds per image
    loop_from: int

    @property
    def played_ms(self) -> int:
        """How long the first play-through takes."""
        return sum(self.durations)

    def index_at(self, elapsed_ms: float) -> int:
        if elapsed_ms < self.played_ms:
            return frame_at(elapsed_ms, self.durations)
        tail = self.durations[self.loop_from:]
        return self.loop_from + frame_at(elapsed_ms - self.played_ms, tail)


def frames(style: str, text: str) -> list[tuple[Image.Image, int]]:
    return _STYLES[style](text)


def animate(style: str, text: str) -> Animation:
    shots = frames(style, text)
    letters = _letters(pixelfont.wrap(text, WRAP.get(style, DEFAULT_WRAP)))
    loop_from = {"quote": 0, "smile": 0, "sparkle": letters, "rizz": letters}.get(style, len(shots) - 1)
    return Animation([im for im, _ in shots], [ms for _, ms in shots], loop_from)


def _stamp(im: Image.Image, art: list[str], x: int, y: int, outline: bool = False) -> None:
    """Paint pixel art (letters from PALETTE, "." = clear); outline=True rings the shape in INK."""
    filled = {(x + i, y + j): PALETTE[c] for j, row in enumerate(art) for i, c in enumerate(row) if c != "."}
    if outline:
        ring = {(px + dx, py + dy) for px, py in filled for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - filled.keys()
        filled = {**{p: INK for p in ring}, **filled}
    for (px, py), paint in filled.items():
        if 0 <= px < im.width and 0 <= py < im.height:
            im.putpixel((px, py), paint)


def _skew(art: list[str], k: float) -> list[str]:
    """Lean pixel art about its bottom row (a hand pivoting at the wrist)."""
    shift = [round((len(art) - 1 - j) * k) for j in range(len(art))]
    lo = min(shift)
    width = len(art[0]) + max(shift) - lo
    return [("." * (s - lo) + row).ljust(width, ".") for s, row in zip(shift, art)]


class _Cloud:
    """A cloud with room for a w×h block of content; `inner` is that block's top-left on the canvas."""

    def __init__(self, w: int, h: int):
        bw, bh = w + 2 * PAD_X, h + 2 * PAD_Y
        self.size = (bw + 2 * MARGIN, bh + 2 * MARGIN + TAIL)
        left, top = MARGIN, MARGIN
        self.inner = (left + PAD_X, top + PAD_Y)
        self.body = (left, top, left + bw - 1, top + bh - 1)
        mask = Image.new("1", self.size, 0)
        d = ImageDraw.Draw(mask)
        d.rectangle((left + 4, top + 4, left + bw - 5, top + bh - 5), fill=1)
        # Round puffs all the way round (big on top, smaller underneath) so it reads as a cloud, not a box.
        n = max(2, round((bw - 12) / 10))
        for i in range(n + 1):
            cx = left + 6 + (bw - 13) * i / n
            r = (6, 7)[i % 2] if 0 < i < n else 6
            d.ellipse((cx - r, top, cx + r, top + 2 * r), fill=1)
            r = (5, 4)[i % 2]
            d.ellipse((cx - r, top + bh - 1 - 2 * r, cx + r, top + bh - 1), fill=1)
        m = max(1, round((bh - 12) / 9))
        for i in range(m + 1):
            cy = top + 6 + (bh - 13) * i / m
            for cx in (left + 5, left + bw - 6):
                d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=1)
        # Tail, hanging down just right of centre, like the picture bubbles.
        tx, ty = left + bw // 2 + 2, top + bh - 1
        d.polygon([(tx, ty - 6), (tx + 7, ty - 6), (tx + 5, ty + TAIL - 1), (tx + 4, ty + TAIL - 1)], fill=1)
        self.mask = mask

    def draw(self) -> Image.Image:
        im = Image.new("RGBA", self.size, (0, 0, 0, 0))
        w, h = self.size
        inside = self.mask.load()
        for y in range(h):
            for x in range(w):
                if inside[x, y]:
                    below = all(y + k < h and inside[x, y + k] for k in (1, 2))
                    right = x + 1 < w and inside[x + 1, y]
                    im.putpixel((x, y), FILL if below and right else SHADE)
                elif any(0 <= x + dx < w and 0 <= y + dy < h and inside[x + dx, y + dy]
                         for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    im.putpixel((x, y), INK)
        return im


def _text_cloud(text: str, style: str, icon_w: int = 0, icon_h: int = 0):
    lines = pixelfont.wrap(text, WRAP.get(style, DEFAULT_WRAP))
    tw, th = pixelfont.block_size(lines)
    gap = 5 if icon_w and lines else 0
    cloud = _Cloud(icon_w + gap + tw, max(th, icon_h))
    ix, iy = cloud.inner
    text_at = (ix + icon_w + gap, iy + (max(th, icon_h) - th) // 2)
    icon_at = (ix, iy + (max(th, icon_h) - icon_h) // 2)
    return cloud, cloud.draw(), lines, text_at, icon_at


def _typed(base: Image.Image, lines: list[str], at: tuple[int, int], count: int) -> Image.Image:
    im = base.copy()
    pixelfont.draw(im, lines, *at, TEXT, limit=count)
    return im


def _letters(lines: list[str]) -> int:
    return sum(len(line) for line in lines)


def _quote(text: str):
    _, base, lines, at, _ = _text_cloud(text, "quote")
    return [(_typed(base, lines, at, _letters(lines)), HOLD_MS)]


def _type(text: str):
    _, base, lines, at, _ = _text_cloud(text, "type")
    n = _letters(lines)
    return [(_typed(base, lines, at, i), TYPE_MS) for i in range(1, n + 1)] + [(_typed(base, lines, at, n), HOLD_MS)]


def _around(cloud: _Cloud) -> list[tuple[int, int]]:
    """Spots just outside the cloud's corners for sparkles: top-left, top-right, right side, left side."""
    l, t, r, b = cloud.body
    return [(l - 3, t - 3), (r - 1, t - 4), (r + 2, (t + b) // 2 - 1), (l - 4, b - 6)]


def _sparkle(text: str):
    cloud, base, lines, at, _ = _text_cloud(text, "sparkle")
    n = _letters(lines)
    spots = _around(cloud)
    steps = n + 18  # one full twinkle cycle after the last letter (it loops from there)

    def frame(step: int) -> Image.Image:
        im = _typed(base, lines, at, min(step + 1, n))
        for k, (x, y) in enumerate(spots):
            phase = (step // 3 + k * 2) % 6  # each sparkle: small, big, small, gone…
            if phase in (0, 2):
                _stamp(im, SPARKLE_SMALL, x + 1, y + 1, outline=True)
            elif phase == 1:
                _stamp(im, SPARKLE_BIG, x, y, outline=True)
        return im

    return [(frame(s), TYPE_MS if s < n else 110) for s in range(steps)]


def _rizz(text: str):
    cloud, base, lines, at, _ = _text_cloud(text, "rizz")
    n = _letters(lines)
    l, t, r, b = cloud.body
    starts = [(r - 2, t + 6), (l - 2, t + 10), (r + 1, b - 4)]
    rise = 10
    steps = n + 14

    def frame(step: int) -> Image.Image:
        im = _typed(base, lines, at, min(step + 1, n))
        for k, (x, y) in enumerate(starts):
            p = ((step + k * 5) % 14) / 14  # 0 = just appeared, 1 = gone
            if p < 0.8:
                _stamp(im, HEART, x + round(1.5 * math.sin(p * 2 * math.pi)), round(y - rise * p), outline=True)
        return im

    return [(frame(s), TYPE_MS if s < n else 110) for s in range(steps)]


def _wave(text: str):
    poses = [_skew(HAND, k) for k in (0.0, 0.35, 0.0, -0.35)]
    pw = max(len(p[0]) for p in poses)
    cloud, base, lines, at, (hx, hy) = _text_cloud(text, "wave", pw, len(HAND))
    base = _typed(base, lines, at, _letters(lines))
    out = []
    for _ in range(3):
        for k, pose in zip((0.0, 0.35, 0.0, -0.35), poses):
            im = base.copy()
            lean = min(0, round((len(HAND) - 1) * k))  # leaning left moves the art's left edge left
            _stamp(im, pose, hx + (pw - len(HAND[0])) // 2 + lean, hy)
            out.append((im, 140))
    im = base.copy()
    _stamp(im, HAND, hx + (pw - len(HAND[0])) // 2, hy)
    return out + [(im, HOLD_MS)]


def _smile(text: str):
    cloud, base, lines, at, (sx, sy) = _text_cloud(text, "smile", len(SMILEY[0]), len(SMILEY))
    base = _typed(base, lines, at, _letters(lines))
    out = []
    for face, ms, bob in ((SMILEY, 500, 0), (SMILEY_BLINK, 120, 0), (SMILEY, 400, 0),
                          (SMILEY_GRIN, 180, -1), (SMILEY_GRIN, 180, 0), (SMILEY_GRIN, 180, -1), (SMILEY_GRIN, 600, 0)):
        im = base.copy()
        _stamp(im, face, sx, sy + bob)
        out.append((im, ms))
    return out


_STYLES = {"quote": _quote, "type": _type, "sparkle": _sparkle, "rizz": _rizz, "wave": _wave, "smile": _smile}
STYLES = tuple(_STYLES)
