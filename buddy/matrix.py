"""Matrix-style rain panel that shows CPU/RAM while the buddy is stressed (drawn with QPainter)."""
import random

PANEL_W = 120
PANEL_H = 70
CELL = 10
TAIL = 6
GLYPHS = "0123456789ABCDEF<>*+=#$%&"
GREEN = (0, 255, 64)


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

    def draw(self, painter, x: float, y: float, cpu: float, ram: float) -> None:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainterPath, QPen

        painter.save()
        painter.translate(x, y)
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        panel = QPainterPath()
        panel.addRoundedRect(QRectF(0.5, 0.5, self.width - 1, self.height - 1), 6, 6)
        painter.fillPath(panel, QColor(0, 13, 0, 217))
        painter.setPen(QPen(QColor(*GREEN, 230), 1))
        painter.drawPath(panel)
        painter.setClipPath(panel)

        glyph_font = QFont("monospace")
        glyph_font.setStyleHint(QFont.StyleHint.TypeWriter)
        glyph_font.setPixelSize(CELL)
        painter.setFont(glyph_font)
        for c in range(self.cols):
            head = int(self.heads[c])
            for k in range(TAIL):
                r = head - k
                if not 0 <= r < self.rows:
                    continue
                if k == 0:
                    painter.setPen(QColor(179, 255, 179, 255))
                else:
                    painter.setPen(QColor(*GREEN, int(255 * 0.6 * (1 - k / TAIL))))
                painter.drawText(c * CELL + 1, (r + 1) * CELL - 1, self.grid[c][r])

        stats_font = QFont("monospace")
        stats_font.setStyleHint(QFont.StyleHint.TypeWriter)
        stats_font.setBold(True)
        stats_font.setPixelSize(15)
        painter.setFont(stats_font)
        metrics = QFontMetricsF(stats_font)
        for i, line in enumerate(format_stats(cpu, ram)):
            width = metrics.horizontalAdvance(line)
            tx = (self.width - width) / 2
            ty = self.height / 2 + (i - 0.5) * 20 + 6
            painter.fillRect(QRectF(tx - 3, ty - 14, width + 6, 18), QColor(0, 0, 0, 191))
            painter.setPen(QColor(191, 255, 191, 255))
            painter.drawText(QRectF(tx, ty - 14, width + 1, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
        painter.restore()
