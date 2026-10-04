import pytest

from buddy.brain import (
    CLICK_SLOP,
    CONFUSED_SECONDS,
    FIDGET_RANGE,
    IDLE_SECONDS,
    LOVE_SECONDS,
    Bounds,
    Brain,
    Bubble,
    State,
)

BOUNDS = Bounds(left=0, top=0, right=1000, floor=800)
W, H = 50, 40


class FakeRng:
    """uniform -> low end, choice -> last item (+1 = right), random -> fixed value."""

    def __init__(self, rand=0.99):
        self.rand = rand

    def uniform(self, a, b):
        return a

    def choice(self, seq):
        return seq[-1]

    def random(self):
        return self.rand


def make(rand=0.99):
    return Brain(BOUNDS, W, H, walk_speed=20.0, rng=FakeRng(rand))


def run(brain, seconds, step=1 / 30):
    for _ in range(round(seconds / step)):
        brain.tick(step)


def walking(rand=0.99):
    brain = make(rand)
    run(brain, IDLE_SECONDS[0] + 0.05)
    assert brain.state is State.WALK
    return brain


def test_starts_idle_on_ground_without_bubble():
    b = make()
    assert b.state is State.IDLE
    assert b.y == BOUNDS.floor - H
    assert BOUNDS.left <= b.x <= BOUNDS.right - W
    assert b.bubble is None


def test_idle_then_walks_right_at_walk_speed():
    b = walking()
    assert b.facing == 1
    x0 = b.x
    run(b, 1.0)
    assert b.x - x0 == pytest.approx(20.0, abs=1.0)


def test_walking_into_edge_turns_around_without_bubble_on_unlucky_roll():
    b = walking(rand=0.99)
    b.x = BOUNDS.right - W - 1.0
    run(b, 0.2)
    assert b.facing == -1
    assert b.x <= BOUNDS.right - W
    assert b.bubble is None


def test_edge_turn_sometimes_shows_confused():
    b = walking(rand=0.0)
    b.x = BOUNDS.right - W - 1.0
    run(b, 0.2)
    assert b.facing == -1
    assert b.bubble is Bubble.CONFUSED


def test_click_shows_love_and_hops_back_to_ground():
    b = make()
    px, py = b.x + 10, b.y + 10
    b.press(px, py)
    b.release(px, py)
    assert b.bubble is Bubble.LOVE
    b.tick(1 / 30)
    assert b.y < b.ground_y
    run(b, 1.0)
    assert b.y == b.ground_y
    assert b.state is State.IDLE
    assert b.bubble is Bubble.LOVE
    run(b, LOVE_SECONDS)
    assert b.bubble is None


def test_tiny_movement_is_still_a_click():
    b = make()
    px, py = b.x + 10, b.y + 10
    b.press(px, py)
    b.motion(px + CLICK_SLOP, py - CLICK_SLOP)
    b.release(px + CLICK_SLOP, py - CLICK_SLOP)
    assert b.state is State.FALLING
    assert b.bubble is Bubble.LOVE


def test_drag_follows_pointer_then_falls_and_is_confused():
    b = make()
    gx, gy = 10, 15
    b.press(b.x + gx, b.y + gy)
    b.motion(300 + gx, 200 + gy)
    assert b.state is State.DRAGGED
    assert (b.x, b.y) == (300, 200)
    assert b.bubble is None
    b.release(300 + gx, 200 + gy)
    assert b.state is State.FALLING
    run(b, 2.0)
    assert b.y == b.ground_y
    assert b.x == 300
    assert b.bubble is Bubble.CONFUSED
    run(b, CONFUSED_SECONDS)
    assert b.bubble is None


def test_drag_is_clamped_to_screen():
    b = make()
    b.press(b.x, b.y)
    b.motion(5000, -5000)
    assert b.x == BOUNDS.right - W
    assert b.y == BOUNDS.top


def test_stressed_shows_angry_and_fidgets_in_place():
    b = make()
    x0 = b.x
    b.set_stressed(True)
    assert b.state is State.STRESSED
    assert b.bubble is Bubble.ANGRY
    for _ in range(300):
        b.tick(1 / 30)
        assert abs(b.x - x0) <= FIDGET_RANGE + 1e-6
        assert b.y == b.ground_y


def test_click_while_stressed_shows_love_then_angry_again():
    b = make()
    b.set_stressed(True)
    b.press(b.x + 1, b.y + 1)
    b.release(b.x + 1, b.y + 1)
    assert b.bubble is Bubble.LOVE
    run(b, LOVE_SECONDS + 0.1)
    assert b.state is State.STRESSED
    assert b.bubble is Bubble.ANGRY


def test_calming_down_returns_to_idle():
    b = make()
    b.set_stressed(True)
    b.set_stressed(False)
    assert b.state is State.IDLE
    assert b.bubble is None


def test_becoming_stressed_mid_drag_waits_until_landing():
    b = make()
    b.press(b.x, b.y)
    b.motion(300, 200)
    b.set_stressed(True)
    assert b.state is State.DRAGGED
    assert b.bubble is None
    b.release(300, 200)
    run(b, 2.0)
    assert b.state is State.STRESSED
    assert b.bubble is Bubble.CONFUSED  # confused outranks angry
    run(b, CONFUSED_SECONDS)
    assert b.bubble is Bubble.ANGRY


def test_huge_time_step_does_not_escape_screen():
    b = walking()
    b.tick(3600.0)
    assert BOUNDS.left <= b.x <= BOUNDS.right - W
    assert b.y == b.ground_y
    b.press(b.x, b.y)
    b.motion(300, 100)
    b.release(300, 100)
    b.tick(3600.0)
    assert BOUNDS.top <= b.y <= b.ground_y


def test_screen_shrink_pulls_pet_back_into_view():
    b = make()
    b.x = 900.0
    b.set_bounds(Bounds(left=0, top=0, right=640, floor=480))
    assert b.x == 640 - W
    assert b.y == 480 - H


def test_resize_keeps_pet_on_ground():
    b = make()
    b.resize(100, 120)
    assert b.y == BOUNDS.floor - 120
