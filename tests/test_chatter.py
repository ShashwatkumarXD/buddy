import json
from datetime import datetime, timedelta

import pytest

from buddy import pixelfont
from buddy.chatter import (
    AWAY_SECONDS,
    EDGE_DELAY,
    GREETING_GAP,
    OPEN_DELAY,
    REMINDER_GAP,
    Chatter,
    Lines,
    load_lines,
)

LINES = Lines(
    greetings={"wave": ["Hi!", "Hey!", "Yo!"], "sparkle": ["Hi beautiful!"], "smile": [""]},
    time={
        "morning": ["Good morning!"],
        "afternoon": ["Good afternoon!"],
        "evening": ["Good evening!"],
        "late_night": ["Are you still building something?"],
        "sleep": ["Time to sleep?"],
    },
)


class FakeRng:
    """uniform -> low end, choice -> first item."""

    def uniform(self, a, b):
        return a

    def choice(self, seq):
        return list(seq)[0]


def at(hour, minute=0, day=5):
    return datetime(2026, 10, day, hour, minute)


def make(**kw):
    kw.setdefault("rng", FakeRng())
    return Chatter(kw.pop("lines", LINES), **kw)


def run(chatter, start, seconds, idle=0.0, free=True, step=1):
    """Tick once per `step` seconds; returns [(time, Say)] for everything said."""
    said = []
    for s in range(0, int(seconds), step):
        now = start + timedelta(seconds=s)
        say = chatter.tick(now, idle, free)
        if say is not None:
            said.append((now, say))
    return said


def kinds(said, *wanted):
    return [(t, s) for t, s in said if s.kind in wanted]


def test_morning_greeting_comes_a_few_minutes_after_opening():
    said = run(make(), at(9), 10 * 60)
    (t, say), = kinds(said, "morning")
    assert t == at(9) + timedelta(seconds=OPEN_DELAY[0])
    assert (say.style, say.text) == ("wave", "Good morning!")


def test_each_period_greets_once_a_day():
    said = run(make(), at(9), 2 * 3600)
    assert len(kinds(said, "morning")) == 1


def test_new_period_greets_shortly_after_it_starts_when_already_open():
    said = run(make(), at(11, 30), 40 * 60)
    (t, say), = kinds(said, "afternoon")
    assert t == at(12) + timedelta(seconds=EDGE_DELAY[0])
    assert say.style == "smile"


def test_evening_is_a_wave():
    (_, say), = kinds(run(make(), at(18), 10 * 60), "evening")
    assert (say.style, say.text) == ("wave", "Good evening!")


def test_says_nothing_while_away_then_greets_after_coming_back():
    c = make()
    assert run(c, at(9), 10 * 60, idle=AWAY_SECONDS) == []
    said = run(c, at(9, 10), 10 * 60)
    (t, _), = kinds(said, "morning")
    assert t == at(9, 10) + timedelta(seconds=OPEN_DELAY[0])


def test_unknown_idle_counts_as_present():
    assert kinds(run(make(), at(9), 10 * 60, idle=None), "morning")


def test_waits_while_buddy_is_busy():
    c = make()
    assert run(c, at(9), 10 * 60, free=False) == []
    said = run(c, at(9, 10), 60)
    assert [s.kind for _, s in said] == ["morning"]
    assert said[0][0] == at(9, 10)


def test_waking_the_laptop_counts_as_opening_it():
    c = make()
    run(c, at(4, 30), 60)  # no period at 4:30
    said = run(c, at(9), 10 * 60)  # the clock jumped: laptop was asleep
    (t, _), = kinds(said, "morning")
    assert t == at(9) + timedelta(seconds=OPEN_DELAY[0])


def test_late_night_question_then_sleep_reminders():
    said = run(make(sleep_reminders=2), at(22, 50), 4 * 3600)
    (asked, say), = kinds(said, "late_night")
    assert asked == at(23) + timedelta(seconds=EDGE_DELAY[0])
    assert say.style == "type"
    reminders = [t for t, _ in kinds(said, "sleep")]
    gap = timedelta(seconds=REMINDER_GAP[0])
    assert reminders == [asked + gap, asked + 2 * gap]


@pytest.mark.parametrize("count", [0, 1, 3])
def test_number_of_sleep_reminders_is_configurable(count):
    said = run(make(sleep_reminders=count), at(23, 30), 4 * 3600, step=5)
    assert len(kinds(said, "late_night")) == 1
    assert len(kinds(said, "sleep")) == count


def test_night_carries_over_midnight():
    c = make(sleep_reminders=1)
    said = run(c, at(23, 30), 3600, step=5) + run(c, at(0, 30, day=6), 2 * 3600, step=5)
    assert len(kinds(said, "late_night")) == 1
    assert len(kinds(said, "sleep")) == 1


def test_late_opening_after_midnight_still_asks():
    said = run(make(), at(0, 30, day=6), 10 * 60)
    (t, _), = kinds(said, "late_night")
    assert t == at(0, 30, day=6) + timedelta(seconds=OPEN_DELAY[0])


def test_nothing_between_4_and_5_am():
    assert kinds(run(make(), at(4, 5), 30 * 60), "morning", "late_night", "sleep") == []


def test_greetings_are_spaced_out():
    said = run(make(), at(14), 3600)
    times = [t for t, _ in said]
    gap = timedelta(seconds=GREETING_GAP[0])
    assert [s.kind for _, s in said] == ["afternoon", "greeting", "greeting"]
    assert times[1] - times[0] == gap and times[2] - times[1] == gap


def test_a_greeting_waits_for_two_others_before_repeating():
    c = make()
    run(c, at(14), 10 * 60)  # afternoon hello out of the way
    said = run(c, at(14, 10), 4 * GREETING_GAP[0] + 60, step=5)
    assert [s.text for _, s in said] == ["Hi!", "Hey!", "Yo!", "Hi!"]


def test_moves_to_another_style_when_one_has_nothing_fresh():
    lines = Lines(greetings={"wave": ["Hi!"], "smile": [""]}, time=LINES.time)
    c = make(lines=lines)
    run(c, at(14), 10 * 60)
    said = run(c, at(14, 10), 3 * GREETING_GAP[0] + 60, step=5)
    assert [(s.style, s.text) for _, s in said] == [("wave", "Hi!"), ("smile", ""), ("wave", "Hi!")]


def test_greeting_due_while_busy_is_skipped_not_queued():
    c = make()
    run(c, at(14), 10 * 60)
    assert run(c, at(14, 10), GREETING_GAP[0], free=False, step=5) == []
    said = run(c, at(14, 10) + timedelta(seconds=GREETING_GAP[0]), 60, step=5)
    assert said == []  # it starts counting again rather than blurting the missed one


def test_greeting_clock_stops_while_away():
    c = make()
    run(c, at(14), 10 * 60)
    run(c, at(14, 10), 3600, idle=AWAY_SECONDS, step=5)
    said = run(c, at(15, 10), 15 * 60, step=5)
    assert kinds(said, "greeting") == []


def test_said_today_survives_a_restart(tmp_path):
    state = tmp_path / "chatter.json"
    run(make(state_path=state), at(9), 10 * 60)
    assert kinds(run(make(state_path=state), at(10), 10 * 60), "morning") == []
    assert kinds(run(make(state_path=state), at(9, day=6), 10 * 60), "morning")


def test_sleep_reminder_count_survives_a_restart(tmp_path):
    state = tmp_path / "chatter.json"
    run(make(state_path=state, sleep_reminders=1), at(23), 3600, step=5)
    said = run(make(state_path=state, sleep_reminders=1), at(0, 30, day=6), 2 * 3600, step=5)
    assert kinds(said, "late_night", "sleep") == []


def test_broken_state_file_is_ignored(tmp_path):
    state = tmp_path / "chatter.json"
    state.write_text("{not json")
    assert kinds(run(make(state_path=state), at(9), 10 * 60), "morning")
    assert json.loads(state.read_text())["said"]["morning"] == "2026-10-05"


def test_bundled_lines_load_and_can_all_be_drawn():
    lines = load_lines()
    assert lines.greetings["smile"] == [""]  # the smiley alone for now
    assert lines.greetings["wave"] and lines.greetings["sparkle"]
    assert set(lines.time) == {"morning", "afternoon", "evening", "late_night", "sleep"}
    for group in (*lines.greetings.values(), *lines.time.values()):
        assert group
        for text in group:
            assert pixelfont.supports(text), text
