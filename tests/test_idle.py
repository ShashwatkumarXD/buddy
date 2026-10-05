import sys

import pytest

from buddy import idle
from buddy.idle import IdleClock, default_backends


def broken():
    raise OSError("not here")


def test_keeps_the_first_backend_that_answers():
    calls = []

    def second():
        calls.append("second")
        return 12.5

    def third():
        calls.append("third")
        return 99.0

    clock = IdleClock([broken, second, third])
    assert clock.seconds() == 12.5
    assert clock.seconds() == 12.5
    assert calls == ["second", "second"]  # never falls through to the third once one works


def test_unknown_when_no_backend_answers():
    clock = IdleClock([broken, broken])
    assert clock.seconds() is None
    assert clock.seconds() is None


def test_unknown_while_the_chosen_backend_fails():
    answers = iter([3.0, OSError("bus hiccup"), 4.0])

    def flaky():
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    clock = IdleClock([flaky])
    assert clock.seconds() == 3.0
    assert clock.seconds() is None
    assert clock.seconds() == 4.0


def test_negative_or_garbage_answers_are_unknown():
    assert IdleClock([lambda: -1.0]).seconds() is None
    assert IdleClock([lambda: "soon"]).seconds() is None


@pytest.mark.parametrize(
    "platform, expected",
    [
        ("win32", [idle.windows_idle]),
        ("darwin", [idle.mac_idle]),
        ("linux", [idle.gnome_idle, idle.freedesktop_idle, idle.x11_idle]),
    ],
)
def test_backends_per_platform(platform, expected):
    assert default_backends(platform) == expected


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux backends")
def test_linux_backends_fail_cleanly_without_a_desktop(monkeypatch):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    clock = IdleClock([idle.x11_idle])
    assert clock.seconds() is None  # raises inside, reported as unknown
