import pytest

from buddy import speech


@pytest.mark.parametrize("style", speech.STYLES)
def test_every_frame_of_a_bubble_is_the_same_size(style):
    anim = speech.animate(style, "Hi beautiful!")
    assert len({im.size for im in anim.images}) == 1
    assert len(anim.images) == len(anim.durations)


def test_smiley_on_its_own_makes_a_small_bubble():
    alone = speech.animate("smile", "").images[0]
    worded = speech.animate("smile", "You got this!").images[0]
    assert alone.width < worded.width
    assert alone.width < 50


def test_plays_through_once_then_loops_the_tail():
    anim = speech.Animation(images=["a", "b", "c", "d"], durations=[100, 100, 100, 100], loop_from=2)
    assert [anim.index_at(ms) for ms in (0, 150, 250, 350)] == [0, 1, 2, 3]
    assert [anim.index_at(ms) for ms in (400, 550, 600)] == [2, 3, 2]


def test_holds_the_last_frame_when_the_tail_is_one_frame():
    anim = speech.Animation(images=["a", "b"], durations=[100, 100], loop_from=1)
    assert anim.index_at(10_000) == 1


def test_typing_styles_twinkle_on_after_the_last_letter():
    anim = speech.animate("sparkle", "Hi!")
    assert anim.loop_from == 3  # one frame per letter, then the twinkle loops
    assert anim.played_ms == sum(anim.durations)
