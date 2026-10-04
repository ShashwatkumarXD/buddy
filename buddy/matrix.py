"""Matrix-style rain panel that shows CPU/RAM while the buddy is stressed."""
import math
import random

import cairo

PANEL_W = 120
PANEL_H = 70
CELL = 10
TAIL = 6
GLYPHS = "0123456789ABCDEF<>*+=#$%&"
GREEN = (0.0, 1.0, 0.25)


def format_stats(cpu: float, ram: float) -> tuple[str, str]:
    return f"CPU {cpu:3.0f}%", f"RAM {ram:3.0f}%"


class MatrixRain:
    def __init__(self, width: int = PANEL_W, height: int = PANEL_H, rng=None):
        self.width = width
        self.height = height
        self.rng = rng or random.Random()
        self.cols = max(1, width // CELL)
        self.rows = max(1, height // CELL)
        self.heads = [self.rng.uniform(-TAIL, self.rows) for _ in range(self.cols)]
        self.speeds = [self.rng.uniform(4, 12) for _ in range(self.cols)]  # rows per second
        self.grid = [[self.rng.choice(GLYPHS) for _ in range(self.rows)] for _ in range(self.cols)]

    def tick(self, dt: float) -> None:
        dt = min(max(dt, 0.0), 0.1)
        for c in range(self.cols):
            self.heads[c] += self.speeds[c] * dt
            if self.heads[c] - TAIL > self.rows:
                self.heads[c] = self.rng.uniform(-TAIL, 0)
            if self.rng.random() < 0.3:
                self.grid[c][self.rng.randrange(self.rows)] = self.rng.choice(GLYPHS)

    def draw(self, cr: cairo.Context, x: float, y: float, cpu: float, ram: float) -> None:
        cr.save()
        cr.translate(x, y)
        _rounded_rect(cr, 0.5, 0.5, self.width - 1, self.height - 1, 6)
        cr.set_source_rgba(0.0, 0.05, 0.0, 0.85)
        cr.fill_preserve()
        cr.set_source_rgba(*GREEN, 0.9)
        cr.set_line_width(1)
        cr.stroke()
        _rounded_rect(cr, 0.5, 0.5, self.width - 1, self.height - 1, 6)
        cr.clip()

        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(CELL)
        for c in range(self.cols):
            head = int(self.heads[c])
            for k in range(TAIL):
                r = head - k
                if not 0 <= r < self.rows:
                    continue
                if k == 0:
                    cr.set_source_rgba(0.7, 1.0, 0.7, 1.0)
                else:
                    cr.set_source_rgba(*GREEN, 0.6 * (1 - k / TAIL))
                cr.move_to(c * CELL + 1, (r + 1) * CELL - 1)
                cr.show_text(self.grid[c][r])

        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(15)
        for i, line in enumerate(format_stats(cpu, ram)):
            ext = cr.text_extents(line)
            tx = (self.width - ext.x_advance) / 2
            ty = self.height / 2 + (i - 0.5) * 20 + 6
            cr.set_source_rgba(0, 0, 0, 0.75)
            cr.rectangle(tx - 3, ty - 14, ext.x_advance + 6, 18)
            cr.fill()
            cr.set_source_rgba(0.75, 1.0, 0.75, 1.0)
            cr.move_to(tx, ty)
            cr.show_text(line)
        cr.restore()


def _rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
