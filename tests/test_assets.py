from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"


def test_each_bubble_is_native_pixel_art():
    for name in ("love", "angry", "confused"):
        im = Image.open(BUBBLES / f"{name}.png")
        assert im.mode == "RGBA"
        assert im.size == (40, 32)  # one pixel per art pixel; the window enlarges by whole numbers
        assert set(im.getchannel("A").getextrema()) == {0, 255}
        assert all(a in (0, 255) for a in im.getchannel("A").tobytes())  # hard pixel edges, no blur
