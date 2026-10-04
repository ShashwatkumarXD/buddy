"""Frame timing for animated reaction bubbles (pure logic, no GTK)."""

BUBBLE_HOLD_MS = 700  # first frame: the bubble at rest
BUBBLE_STEP_MS = 110  # each following frame (e.g. a turning page)


def bubble_durations(frame_count: int) -> list[int]:
    if frame_count <= 1:
        return [1000]
    return [BUBBLE_HOLD_MS] + [BUBBLE_STEP_MS] * (frame_count - 1)


def frame_at(elapsed_ms: float, durations: list[int]) -> int:
    """Index of the frame showing `elapsed_ms` into a looping animation."""
    if not durations:
        raise ValueError("an animation needs at least one frame")
    t = elapsed_ms % sum(durations)
    for index, ms in enumerate(durations):
        if t < ms:
            return index
        t -= ms
    return len(durations) - 1
