import random

import cairo

from buddy.matrix import PANEL_H, PANEL_W, TAIL, MatrixRain, format_stats


def test_format_stats():
    assert format_stats(92.4, 88.0) == ("CPU  92%", "RAM  88%")
    assert format_stats(100, 5) == ("CPU 100%", "RAM   5%")


def test_rain_stays_bounded_over_time():
    rain = MatrixRain(rng=random.Random(1))
    for _ in range(2000):
        rain.tick(1 / 30)
    assert all(-TAIL <= head <= rain.rows + TAIL for head in rain.heads)


def test_draw_paints_green_panel():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, PANEL_W, PANEL_H)
    cr = cairo.Context(surface)
    rain = MatrixRain(rng=random.Random(1))
    for _ in range(30):
        rain.tick(1 / 30)
    rain.draw(cr, 0, 0, 91, 77)
    surface.flush()
    data = surface.get_data()
    greenish = 0
    for i in range(0, len(data), 4):
        b, g, r, a = data[i], data[i + 1], data[i + 2], data[i + 3]
        if a > 0 and g > r + 40 and g > b + 40:
            greenish += 1
    assert greenish > 50
