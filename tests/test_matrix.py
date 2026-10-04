import random

from buddy.matrix import PANEL_H, PANEL_W, TAIL, MatrixRain, format_stats


def test_format_stats():
    assert format_stats(92.4, 88.0) == ("CPU  92%", "RAM  88%")
    assert format_stats(100, 5) == ("CPU 100%", "RAM   5%")


def test_rain_stays_bounded_over_time():
    rain = MatrixRain(rng=random.Random(1))
    for _ in range(2000):
        rain.tick(1 / 30)
    assert all(-TAIL <= head <= rain.rows + TAIL for head in rain.heads)


def test_draw_paints_green_panel(qapp):
    from PySide6.QtGui import QImage, QPainter

    image = QImage(PANEL_W, PANEL_H, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    rain = MatrixRain(rng=random.Random(1))
    for _ in range(30):
        rain.tick(1 / 30)
    painter = QPainter(image)
    rain.draw(painter, 0, 0, 91, 77)
    painter.end()
    greenish = 0
    for y in range(PANEL_H):
        for x in range(PANEL_W):
            c = image.pixelColor(x, y)
            if c.alpha() > 0 and c.green() > c.red() + 40 and c.green() > c.blue() + 40:
                greenish += 1
    assert greenish > 50
