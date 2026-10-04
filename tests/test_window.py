"""Off-screen smoke tests for the real Qt windows (run on Linux, macOS and Windows in CI)."""
import threading
import time

import pytest
from PIL import Image

from buddy import config, ipc, sprites


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def cached(tmp_path):
    frames = {}
    for key, color in (("walk", (255, 0, 0, 255)), ("idle", (0, 0, 255, 255))):
        frames[key] = []
        for i in range(2):
            im = Image.new("RGBA", (12, 10), (0, 0, 0, 0))
            im.paste(color, (i, 0, 12, 10))
            path = tmp_path / f"{key}_{i}.png"
            im.save(path)
            frames[key].append((path, 100))
    return sprites.CachedSprite(anims=frames, faces=1)


@pytest.fixture
def buddy(qapp, runtime, cached):
    from buddy import window

    pet = window.Buddy(qapp, config.Config(scale=2), cached)
    yield pet
    pet.shutdown()


def pump(buddy, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        buddy.on_tick()
        buddy.on_ipc()
        time.sleep(0.01)


def test_window_smoke(buddy):
    pump(buddy, 0.5)
    assert buddy.pet.width() == 24 and buddy.pet.height() == 20  # 12x10 sprite at scale 2
    assert (buddy.pet.x(), buddy.pet.y()) == (int(buddy.brain.x), int(buddy.brain.y))


def test_running_buddy_answers_and_reacts_to_agents(buddy):
    assert ipc.port_file().exists()
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("ok", ipc.send("thinking")))
    thread.start()
    end = time.monotonic() + 3
    while thread.is_alive() and time.monotonic() < end:
        buddy.on_ipc()
        time.sleep(0.01)
    thread.join(1)
    assert result["ok"] is True
    assert buddy.brain.thinking is True


def test_click_shows_love(buddy):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from buddy.brain import Bubble

    QTest.mouseClick(buddy.pet, Qt.MouseButton.LeftButton)
    assert buddy.brain.bubble is Bubble.LOVE


def test_stressed_decor_draws_the_panel(buddy):
    buddy.brain.set_stressed(True)
    buddy.on_tick()
    image = buddy.decor.grab().toImage()
    greenish = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if c.alpha() > 0 and c.green() > c.red() + 40 and c.green() > c.blue() + 40:
                greenish += 1
    assert greenish > 20


def test_shutdown_removes_the_contact_file(qapp, runtime, cached):
    from buddy import window

    pet = window.Buddy(qapp, config.Config(), cached)
    assert ipc.port_file().exists()
    pet.shutdown()
    assert not ipc.port_file().exists()


def test_missing_x11_libraries_are_reported(monkeypatch):
    from buddy import window

    monkeypatch.setattr(window, "_loadable", lambda soname: soname != "libxcb-cursor.so.0")
    assert window.missing_x11_libraries() == ["libxcb-cursor0"]


def test_x11_library_check_tries_to_load_the_real_files():
    from buddy import window

    assert window._loadable("libc.so.6") is True
    assert window._loadable("libdefinitely-not-here.so.9") is False



@pytest.mark.parametrize(
    "pixels, scale, dpr, device",
    [(12, 2, 1.0, 24), (12, 1.5, 1.0, 18), (12, 2, 1.25, 30), (12, 3, 1.5, 54), (1, 0.5, 1.0, 1)],
)
def test_images_are_scaled_straight_to_screen_pixels(pixels, scale, dpr, device):
    """Scaling once, to the screen's real pixels, avoids Qt resampling the art again (shimmer at 125%/150%)."""
    from buddy import window

    assert window.device_pixels(pixels, scale, dpr) == device
