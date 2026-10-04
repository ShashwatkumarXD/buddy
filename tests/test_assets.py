from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"


def test_each_bubble_is_native_pixel_art():
    for name in ("love", "angry", "confused", "exclaim", "thinking"):
        im = Image.open(BUBBLES / f"{name}.png")
        assert im.mode == "RGBA"
        assert im.width == 40 and im.height <= 40  # one pixel per art pixel; the window enlarges them
        assert set(im.getchannel("A").getextrema()) == {0, 255}
        assert all(a in (0, 255) for a in im.getchannel("A").tobytes())  # hard pixel edges, no blur


def test_thinking_bubble_has_page_flip_frames_matching_its_size():
    rest = Image.open(BUBBLES / "thinking.png")
    for i in (1, 2, 3):
        frame = Image.open(BUBBLES / f"thinking_{i}.png")
        assert frame.size == rest.size
        assert frame.tobytes() != rest.tobytes()  # each frame actually shows the turning page
