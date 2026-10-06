import pytest

from buddy.brain import (
    CLICK_SLOP,
    CONFUSED_SECONDS,
    FIDGET_RANGE,
    IDLE_SECONDS,
    LOVE_SECONDS,
    DIZZY_SECONDS,
    LONELY_SECONDS,
    NAP_SECONDS,
    SHAKE_SWINGS,
    SHAKE_TRAVEL,
    SHAKE_WINDOW,
    SYSTEM_IDLE_SECONDS,
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


# --- Claude Code reactions -------------------------------------------------

from buddy.brain import EXCLAIM_SECONDS, HOPS_WHEN_DONE, THINK_TIMEOUT  # noqa: E402


def count_hops(brain, seconds, step=1 / 30):
    hops, airborne = 0, brain.y < brain.ground_y
    for _ in range(round(seconds / step)):
        brain.tick(step)
        now_airborne = brain.y < brain.ground_y
        if now_airborne and not airborne:
            hops += 1
        airborne = now_airborne
    return hops


def test_thinking_spot_is_fifteen_percent_in_from_the_right():
    b = make()
    assert b.thinking_x == pytest.approx(BOUNDS.right - W - 0.15 * (BOUNDS.right - BOUNDS.left))


def test_thinking_walks_to_the_spot_and_shows_thinking_bubble():
    b = make()
    b.claude_thinking()
    assert b.state is State.THINKING
    assert b.bubble is Bubble.THINKING
    b.tick(1 / 30)
    assert b.moving and b.facing == 1
    run(b, 10.0)
    assert b.x == pytest.approx(b.thinking_x)
    assert not b.moving
    assert b.state is State.THINKING
    assert b.bubble is Bubble.THINKING


def test_done_shows_exclaim_and_hops_three_times_then_wanders():
    b = make()
    b.claude_thinking()
    run(b, 10.0)
    b.claude_done()
    assert b.bubble is Bubble.EXCLAIM
    hops = count_hops(b, EXCLAIM_SECONDS)
    assert hops == HOPS_WHEN_DONE  # counts take-offs, including the one claude_done() launched
    assert b.y == b.ground_y
    run(b, 0.2)
    assert b.bubble is None
    assert b.state in (State.IDLE, State.WALK)


def test_done_hops_exactly_three_times_in_total():
    b = make()
    b.claude_done()
    assert b.y == b.ground_y and b.vy < 0  # first hop launched
    assert count_hops(b, 5.0) == HOPS_WHEN_DONE


def test_dragging_while_thinking_returns_to_the_spot():
    b = make()
    b.claude_thinking()
    b.press(b.x, b.y)
    b.motion(100, 300)
    b.release(100, 300)
    run(b, 2.0)
    assert b.state is State.THINKING
    run(b, 10.0)
    assert b.x == pytest.approx(b.thinking_x)


def test_thinking_times_out():
    b = make()
    b.claude_thinking()
    for _ in range(int(THINK_TIMEOUT / 0.1) + 5):
        b.tick(0.1)
    assert b.state is not State.THINKING
    assert b.bubble is None


def test_stopped_puts_the_book_away_without_celebrating():
    b = make()
    b.claude_thinking()
    run(b, 10.0)
    b.claude_stopped()
    assert b.thinking is False
    assert b.state is not State.THINKING
    assert b.bubble is None
    assert b.y == b.ground_y and b.vy == 0  # no ❗ hops: the user cut it short


def test_stopped_while_not_thinking_changes_nothing():
    b = make()
    b.claude_done()
    b.claude_stopped()
    assert b.bubble is Bubble.EXCLAIM


def test_stress_while_thinking_keeps_thinking_with_thinking_bubble():
    b = make()
    b.claude_thinking()
    b.set_stressed(True)
    assert b.state is State.THINKING
    assert b.bubble is Bubble.THINKING
    run(b, 10.0)
    b.claude_done()
    run(b, EXCLAIM_SECONDS + 0.2)
    assert b.state is State.STRESSED
    assert b.bubble is Bubble.ANGRY


def test_love_outranks_thinking():
    b = make()
    b.claude_thinking()
    b.press(b.x + 1, b.y + 1)
    b.release(b.x + 1, b.y + 1)
    assert b.bubble is Bubble.LOVE


def test_moving_follows_state():
    b = make()
    assert not b.moving  # idle
    b = walking()
    assert b.moving


def shake(brain, swings, swing=SHAKE_TRAVEL + 15, seconds_per_swing=0.1, vertical=False):
    """Grab the pet in the air and swing the pointer back and forth `swings` times."""
    px, py = brain.x + 10, brain.y + 10
    brain.press(px, py)
    for i in range(swings + 1):  # the first move only starts the drag; each one after is a turn-back
        offset = swing if i % 2 == 0 else 0.0
        brain.motion(px, py + offset) if vertical else brain.motion(px + offset, py)
        run(brain, seconds_per_swing)
    return px, py


def test_shaking_while_held_makes_it_dizzy():
    b = make()
    shake(b, SHAKE_SWINGS)
    assert b.state is State.DRAGGED
    assert b.bubble is Bubble.DIZZY  # shown while still being held


def test_shaking_up_and_down_counts_too():
    b = make()
    shake(b, SHAKE_SWINGS, vertical=True)
    assert b.bubble is Bubble.DIZZY


def test_a_few_swings_are_just_a_drag():
    b = make()
    shake(b, SHAKE_SWINGS - 1)
    assert b.bubble is None


def test_tiny_wiggles_are_not_a_shake():
    b = make()
    shake(b, SHAKE_SWINGS * 3, swing=SHAKE_TRAVEL - 1)
    assert b.bubble is None


def test_slow_swings_are_not_a_shake():
    b = make()
    shake(b, SHAKE_SWINGS * 2, seconds_per_swing=SHAKE_WINDOW / (SHAKE_SWINGS - 1) + 0.05)
    assert b.bubble is None


def test_dizzy_after_landing_instead_of_confused():
    b = make()
    px, py = shake(b, SHAKE_SWINGS)
    b.release(px, py)
    run(b, 2.0)
    assert b.y == b.ground_y
    assert b.state is State.IDLE
    assert b.bubble is Bubble.DIZZY
    run(b, DIZZY_SECONDS)
    assert b.bubble is None  # not confused afterwards either


def test_dizziness_fades_if_held_still_after_shaking():
    b = make()
    px, py = shake(b, SHAKE_SWINGS)
    run(b, DIZZY_SECONDS + 0.1)
    assert b.bubble is None
    b.release(px, py)
    run(b, 0.2)
    assert b.y == b.ground_y
    assert b.bubble is Bubble.CONFUSED


# --- sleeping ---------------------------------------------------------------


def napping():
    """Left alone long enough and the nap roll succeeds (rand 0.0): asleep at the next stop."""
    b = make(rand=0.0)
    run(b, LONELY_SECONDS + 10)
    assert b.state is State.SLEEPING
    return b


def test_naps_when_left_alone_long_enough():
    b = napping()
    assert b.asleep
    assert b.bubble is Bubble.SLEEP
    assert not b.moving
    x = b.x
    run(b, 5.0)
    assert b.x == x and b.y == b.ground_y  # lies still


def test_no_nap_before_being_left_alone_long_enough():
    b = make(rand=0.0)
    for _ in range(round((LONELY_SECONDS - 1) * 30)):
        b.tick(1 / 30)
        assert b.state is not State.SLEEPING


def test_no_nap_when_the_roll_fails():
    b = make(rand=0.99)
    for _ in range(round(LONELY_SECONDS * 2 * 30)):
        b.tick(1 / 30)
        assert b.state is not State.SLEEPING


def test_attention_restarts_the_lonely_clock():
    b = make(rand=0.0)
    run(b, LONELY_SECONDS - 5)
    b.claude_thinking()
    b.claude_done()
    for _ in range(round((LONELY_SECONDS - 10) * 30)):
        b.tick(1 / 30)
        assert b.state is not State.SLEEPING


def test_wakes_up_after_the_nap_and_does_not_nap_again_right_away():
    b = napping()
    run(b, NAP_SECONDS[0] + 0.1)
    assert b.state is not State.SLEEPING
    assert b.bubble is not Bubble.SLEEP
    for _ in range(round((LONELY_SECONDS - 10) * 30)):
        b.tick(1 / 30)
        assert b.state is not State.SLEEPING


def test_click_wakes_it_with_love():
    b = napping()
    b.press(b.x + 1, b.y + 1)
    b.release(b.x + 1, b.y + 1)
    assert not b.asleep
    assert b.bubble is Bubble.LOVE


def test_drag_wakes_it():
    b = napping()
    b.press(b.x, b.y)
    b.motion(b.x + 100, b.y - 100)
    assert b.state is State.DRAGGED
    assert b.bubble is None


def test_claude_thinking_wakes_it():
    b = napping()
    b.claude_thinking()
    assert b.state is State.THINKING
    assert b.bubble is Bubble.THINKING


def test_stress_wakes_it():
    b = napping()
    b.set_stressed(True)
    assert b.state is State.STRESSED
    assert b.bubble is Bubble.ANGRY


def test_sleeps_while_the_computer_is_idle_and_wakes_when_you_are_back():
    b = make()
    b.set_system_idle(SYSTEM_IDLE_SECONDS - 1)
    assert not b.asleep
    b.set_system_idle(SYSTEM_IDLE_SECONDS)
    assert b.asleep
    assert b.bubble is Bubble.SLEEP
    run(b, NAP_SECONDS[1] + 5)
    assert b.asleep  # no nap timer: sleeps as long as you are away
    b.set_system_idle(0.5)
    assert not b.asleep
    assert b.state is State.IDLE


def test_computer_idle_also_puts_a_walking_buddy_to_sleep():
    b = walking()
    b.set_system_idle(SYSTEM_IDLE_SECONDS + 1)
    assert b.asleep


def test_unknown_idle_time_changes_nothing():
    b = make()
    b.set_system_idle(SYSTEM_IDLE_SECONDS)
    b.set_system_idle(None)
    assert b.asleep
    b2 = make()
    b2.set_system_idle(None)
    assert not b2.asleep


def test_computer_idle_does_not_interrupt_thinking_or_stress():
    b = make()
    b.claude_thinking()
    b.set_system_idle(SYSTEM_IDLE_SECONDS + 1)
    assert b.state is State.THINKING
    s = make()
    s.set_stressed(True)
    s.set_system_idle(SYSTEM_IDLE_SECONDS + 1)
    assert s.state is State.STRESSED


def test_falls_asleep_once_claude_is_done_if_you_are_still_away():
    b = make()
    b.claude_thinking()
    b.claude_done()
    run(b, 3.0)  # celebratory hops, then back on the ground
    b.set_system_idle(SYSTEM_IDLE_SECONDS + 1)
    assert b.asleep


def test_nap_turns_into_a_long_sleep_when_the_computer_goes_idle():
    b = napping()
    b.set_system_idle(SYSTEM_IDLE_SECONDS + 1)
    run(b, NAP_SECONDS[1] + 5)
    assert b.asleep
    b.set_system_idle(0.0)
    assert not b.asleep


def test_short_break_from_the_computer_does_not_cut_a_nap_short():
    b = napping()
    b.set_system_idle(0.0)  # you are at the computer: the nap goes on
    assert b.asleep


# --- speech ------------------------------------------------------------------


def test_free_to_talk_when_idle_or_walking():
    b = make()
    assert b.free_to_talk
    run(b, IDLE_SECONDS[0] + 0.05)
    assert b.state is State.WALK and b.free_to_talk


def test_says_something_for_a_while():
    b = make()
    b.say("hello", 2.0)
    assert b.speech == "hello" and not b.free_to_talk
    run(b, 1.9)
    assert b.speech == "hello"
    run(b, 0.2)
    assert b.speech is None and b.free_to_talk


def test_not_free_to_talk_while_a_bubble_shows_or_asleep():
    b = make()
    b.claude_thinking()
    assert not b.free_to_talk
    b = make()
    b.set_system_idle(SYSTEM_IDLE_SECONDS)
    assert not b.free_to_talk


def test_a_reaction_cuts_the_speech_short():
    b = make()
    b.say("hello", 5.0)
    b.press(10, 790)
    b.release(10, 790)  # a click: love
    b.tick(1 / 30)
    assert b.bubble is Bubble.LOVE and b.speech is None
    run(b, LOVE_SECONDS + 1)
    assert b.speech is None  # it doesn't come back afterwards


def test_dragging_cuts_the_speech_short():
    b = make()
    b.say("hello", 5.0)
    b.press(b.x + 5, b.y + 5)
    b.motion(b.x + 100, b.y - 100)
    b.tick(1 / 30)
    assert b.speech is None
