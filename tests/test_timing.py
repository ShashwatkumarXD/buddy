import pytest

from buddy.timing import DRIFT_STEP_MS, SPIN_STEP_MS, bubble_durations, drift_durations, frame_at, spin_durations


def test_single_frame_bubble_never_changes():
    assert bubble_durations(1) == [1000]
    assert frame_at(0, [1000]) == 0
    assert frame_at(123456, [1000]) == 0


def test_animated_bubble_holds_then_flips():
    durations = bubble_durations(4)
    assert durations == [700, 110, 110, 110]
    assert [frame_at(ms, durations) for ms in (0, 699, 700, 809, 810, 920, 1029, 1030)] == [0, 0, 1, 1, 2, 3, 3, 0]


def test_spinning_bubble_never_rests_on_a_frame():
    assert spin_durations(6) == [SPIN_STEP_MS] * 6
    assert spin_durations(1) == [SPIN_STEP_MS]


def test_frame_at_rejects_empty_durations():
    with pytest.raises(ValueError):
        frame_at(0, [])


def test_drifting_bubble_moves_slowly_and_steadily():
    assert drift_durations(6) == [DRIFT_STEP_MS] * 6
    assert DRIFT_STEP_MS > SPIN_STEP_MS
