"""Off-screen smoke tests for the real Qt windows (run on Linux, macOS and Windows in CI)."""
import json
import sys
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


def test_interrupting_the_agent_stops_the_thinking(buddy, tmp_path):
    log = tmp_path / "session.jsonl"
    log.write_text("")
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("ok", ipc.send(f"thinking {log}")))
    thread.start()
    end = time.monotonic() + 3
    while thread.is_alive() and time.monotonic() < end:
        buddy.on_ipc()
        time.sleep(0.01)
    thread.join(1)
    assert buddy.brain.thinking is True
    buddy.on_monitor()
    assert buddy.brain.thinking is True
    entry = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}}
    log.write_text(json.dumps(entry) + "\n")
    buddy.on_monitor()
    assert buddy.brain.thinking is False


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


def test_idle_computer_puts_it_to_sleep_with_still_sprite_and_zzz(buddy):
    from buddy.brain import SYSTEM_IDLE_SECONDS, Bubble
    from buddy.idle import IdleClock

    buddy.idle = IdleClock([lambda: SYSTEM_IDLE_SECONDS + 1])
    buddy.on_monitor()
    assert buddy.brain.bubble is Bubble.SLEEP
    pump(buddy, 0.4)  # longer than a 100 ms sprite frame
    assert buddy.sprite.index == 0
    image = buddy.decor.grab().toImage()
    sleepy_blue = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if (c := image.pixelColor(x, y)).alpha() > 0 and c.blue() > 230 and c.red() < c.blue() - 30
    )
    assert sleepy_blue > 10
    buddy.idle = IdleClock([lambda: 0.0])
    buddy.on_monitor()
    assert not buddy.brain.asleep


def test_shutdown_removes_the_contact_file(qapp, runtime, cached):
    from buddy import window

    pet = window.Buddy(qapp, config.Config(), cached)
    assert ipc.port_file().exists()
    pet.shutdown()
    assert not ipc.port_file().exists()


def test_mac_tweaks_only_touch_real_macos_windows(qapp, runtime, cached, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from buddy import window

    monkeypatch.setattr(window.sys, "platform", "darwin")
    monkeypatch.setattr(window.signal, "signal", lambda *args: None)  # keep pytest's Ctrl+C
    monkeypatch.setattr(QApplication, "exec", lambda *args: 0)  # return instead of looping
    tweaked = []
    monkeypatch.setattr(window, "_mac_tweaks", tweaked.append)
    assert window.run(config.Config(), cached) == 0
    assert tweaked == []  # offscreen windows aren't NSViews; messaging them crashes buddy


def test_missing_x11_libraries_are_reported(monkeypatch):
    from buddy import window

    monkeypatch.setattr(window, "_loadable", lambda soname: soname != "libxcb-cursor.so.0")
    assert window.missing_x11_libraries() == ["libxcb-cursor0"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the X11 library check only runs on Linux")
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


# --- speech ------------------------------------------------------------------


def _opaque(widget) -> int:
    image = widget.grab().toImage()
    return sum(1 for y in range(0, image.height(), 2) for x in range(0, image.width(), 2) if image.pixelColor(x, y).alpha() > 0)


def test_speech_shows_in_its_own_window_above_buddy(buddy):
    from buddy.chatter import Say

    buddy.speak(Say("greeting", "sparkle", "Hi beautiful!"))
    pump(buddy, 0.2)
    win = buddy.speech_window
    assert buddy.brain.speech is not None
    assert win.width() > buddy.pet.width()
    assert win.y() + win.height() <= buddy.pet.y()
    assert _opaque(win) > 50


def test_speech_window_empties_when_a_reaction_takes_over(buddy):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from buddy.chatter import Say

    buddy.speak(Say("greeting", "wave", "Hi!"))
    buddy.on_tick()
    QTest.mouseClick(buddy.pet, Qt.MouseButton.LeftButton)
    buddy.on_tick()
    assert buddy.brain.speech is None
    assert _opaque(buddy.speech_window) == 0


def test_speech_stays_on_screen_at_the_edge(buddy):
    from buddy.chatter import Say

    buddy.brain.x = float(buddy.brain.bounds.left)
    buddy.speak(Say("time", "type", "Even servers need downtime. Sleep!"))
    buddy.on_tick()
    assert buddy.speech_window.x() >= buddy.brain.bounds.left


def test_monitor_tick_asks_the_chatter(buddy, monkeypatch):
    from buddy.chatter import Say
    from buddy.idle import IdleClock

    # Pin the machine's state: a CI runner nobody has touched for hours would put buddy to sleep
    # (Windows reports real idle time), and a busy runner could make it stressed; either way it's not free.
    buddy.idle = IdleClock([lambda: 0.0])
    monkeypatch.setattr(buddy.monitor, "tick", lambda: False)
    asked = []

    def tick(now, idle, free):
        asked.append(free)
        return Say("morning", "wave", "Good morning!")

    monkeypatch.setattr(buddy.chatter, "tick", tick)
    buddy.on_monitor()
    assert asked == [True]
    assert buddy.brain.speech is not None


def test_talking_can_be_switched_off(qapp, runtime, cached):
    from buddy import window

    pet = window.Buddy(qapp, config.Config(talk=config.TalkConfig(enabled=False)), cached)
    try:
        assert pet.chatter is None
        pet.on_monitor()
    finally:
        pet.shutdown()


@pytest.mark.parametrize("sprite_scale, factor", [(1, 2), (2, 2), (4, 2), (6, 3)])
def test_words_are_drawn_at_least_twice_native_size(sprite_scale, factor):
    from buddy import window

    assert window.speech_scale(sprite_scale) == factor


def test_greeting_settings_reach_the_chatter_and_follow_a_reload(qapp, runtime, cached, monkeypatch):
    from buddy import window

    cfg = config.Config(talk=config.TalkConfig(greetings=["wave"], greeting_minutes=[60, 90], quick_minutes=[2, 4]))
    pet = window.Buddy(qapp, cfg, cached)
    try:
        assert pet.chatter.greetings == ["wave"]
        assert pet.chatter.greeting_gap == (3600, 5400)
        assert pet.chatter.quick_gap == (120, 240)
        talk = config.TalkConfig(greetings=["smile"], greeting_minutes=[5, 10], quick_minutes=[7, 8], sleep_reminders=1)
        config.save(config.Config(talk=talk))
        monkeypatch.setattr(window.sprites, "load_cached", lambda *a, **k: cached)
        pet.reload()
        assert pet.chatter.greetings == ["smile"]
        assert pet.chatter.greeting_gap == (300, 600)
        assert pet.chatter.quick_gap == (420, 480)
        assert pet.chatter.sleep_reminders == 1
    finally:
        pet.shutdown()
