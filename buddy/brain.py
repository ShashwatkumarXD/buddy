"""Pet behaviour state machine. Pure logic: no GTK; all positions are screen pixels."""
import random
from dataclasses import dataclass
from enum import Enum


class State(Enum):
    IDLE = "idle"
    WALK = "walk"
    DRAGGED = "dragged"
    FALLING = "falling"
    STRESSED = "stressed"


class Bubble(Enum):
    LOVE = "love"
    CONFUSED = "confused"
    ANGRY = "angry"


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    floor: int


CLICK_SLOP = 5
GRAVITY = 1500.0
HOP_SPEED = 350.0
LOVE_SECONDS = 2.0
CONFUSED_SECONDS = 1.5
EDGE_CONFUSED_CHANCE = 0.3
IDLE_SECONDS = (2.0, 6.0)
WALK_SECONDS = (3.0, 8.0)
FIDGET_SPEED = 15.0
FIDGET_RANGE = 4.0
MAX_DT = 0.1
_GROUND_STATES = (State.IDLE, State.WALK, State.STRESSED)


class Brain:
    def __init__(self, bounds: Bounds, width: int, height: int, walk_speed: float, rng=None):
        self.rng = rng or random.Random()
        self.bounds = bounds
        self.width = width
        self.height = height
        self.walk_speed = walk_speed
        self.x = float(bounds.left + (bounds.right - bounds.left - width) / 2)
        self.y = self.ground_y
        self.vy = 0.0
        self.facing = 1
        self.stressed = False
        self.state = State.IDLE
        self._timer = self.rng.uniform(*IDLE_SECONDS)
        self._love_left = 0.0
        self._confused_left = 0.0
        self._press = None
        self._confused_on_land = False
        self._fidget_origin = self.x

    @property
    def ground_y(self) -> float:
        return float(self.bounds.floor - self.height)

    @property
    def bubble(self) -> Bubble | None:
        if self.state is State.DRAGGED:
            return None
        if self._love_left > 0:
            return Bubble.LOVE
        if self._confused_left > 0:
            return Bubble.CONFUSED
        if self.stressed:
            return Bubble.ANGRY
        return None

    # --- external inputs -------------------------------------------------

    def set_stressed(self, stressed: bool) -> None:
        if stressed == self.stressed:
            return
        self.stressed = stressed
        if self.state in _GROUND_STATES:
            self._settle()

    def set_bounds(self, bounds: Bounds) -> None:
        self.bounds = bounds
        self._clamp_into_bounds()

    def resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._clamp_into_bounds()

    def press(self, px: float, py: float) -> None:
        self._press = (px, py, px - self.x, py - self.y)

    def motion(self, px: float, py: float) -> None:
        if self._press is None:
            return
        start_x, start_y, grab_x, grab_y = self._press
        if self.state is not State.DRAGGED:
            if abs(px - start_x) <= CLICK_SLOP and abs(py - start_y) <= CLICK_SLOP:
                return
            self.state = State.DRAGGED
            self.vy = 0.0
            self._love_left = 0.0
            self._confused_left = 0.0
        self.x, self.y = self._clamp(px - grab_x, py - grab_y)

    def release(self, px: float, py: float) -> None:
        if self._press is None:
            return
        self._press = None
        if self.state is State.DRAGGED:
            self.state = State.FALLING
            self.vy = 0.0
            self._confused_on_land = True
            return
        self._love_left = LOVE_SECONDS
        if self.state is not State.FALLING:
            self.state = State.FALLING
            self.vy = -HOP_SPEED
            self._confused_on_land = False

    # --- time ------------------------------------------------------------

    def tick(self, dt: float) -> None:
        dt = min(max(dt, 0.0), MAX_DT)
        self._love_left = max(0.0, self._love_left - dt)
        self._confused_left = max(0.0, self._confused_left - dt)
        if self.state is State.FALLING:
            self._fall(dt)
        elif self.state is State.STRESSED:
            self._fidget(dt)
        elif self.state is State.IDLE:
            self._idle(dt)
        elif self.state is State.WALK:
            self._walk(dt)

    def _fall(self, dt: float) -> None:
        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        if self.y >= self.ground_y:
            self.y = self.ground_y
            self.vy = 0.0
            if self._confused_on_land:
                self._confused_left = CONFUSED_SECONDS
            self._settle()

    def _idle(self, dt: float) -> None:
        self._timer -= dt
        if self._timer <= 0:
            self.state = State.WALK
            self.facing = self.rng.choice((-1, 1))
            self._timer = self.rng.uniform(*WALK_SECONDS)

    def _walk(self, dt: float) -> None:
        self.x += self.facing * self.walk_speed * dt
        lo, hi = self.bounds.left, self.bounds.right - self.width
        if self.x <= lo or self.x >= hi:
            self.x = float(min(max(self.x, lo), hi))
            self.facing = 1 if self.x <= lo else -1
            if self.rng.random() < EDGE_CONFUSED_CHANCE:
                self._confused_left = CONFUSED_SECONDS
        self._timer -= dt
        if self._timer <= 0:
            self.state = State.IDLE
            self._timer = self.rng.uniform(*IDLE_SECONDS)

    def _fidget(self, dt: float) -> None:
        self.x += self.facing * FIDGET_SPEED * dt
        lo, hi = self._fidget_origin - FIDGET_RANGE, self._fidget_origin + FIDGET_RANGE
        if self.x <= lo or self.x >= hi:
            self.x = min(max(self.x, lo), hi)
            self.facing = -self.facing

    # --- helpers ---------------------------------------------------------

    def _settle(self) -> None:
        """Enter the right on-the-ground state."""
        if self.stressed:
            self.state = State.STRESSED
            b = self.bounds
            self._fidget_origin = min(max(self.x, b.left + FIDGET_RANGE), b.right - self.width - FIDGET_RANGE)
        else:
            self.state = State.IDLE
            self._timer = self.rng.uniform(*IDLE_SECONDS)

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        b = self.bounds
        x = min(max(x, b.left), b.right - self.width)
        y = min(max(y, b.top), self.ground_y)
        return float(x), float(y)

    def _clamp_into_bounds(self) -> None:
        self.x, self.y = self._clamp(self.x, self.y)
        if self.state in _GROUND_STATES:
            self.y = self.ground_y
            if self.state is State.STRESSED:
                self._settle()
