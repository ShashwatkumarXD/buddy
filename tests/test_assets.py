from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"


def test_each_bubble_exists_as_small_transparent_png():
    for name in ("love", "angry", "confused"):
        im = Image.open(BUBBLES / f"{name}.png")
        assert im.mode == "RGBA"
        assert max(im.size) == 96
        assert im.getchannel("A").getextrema()[0] == 0  # has transparent pixels
