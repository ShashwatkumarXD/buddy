"""What buddy says on its own, and when: time-of-day hellos, late-night nudges and the odd random greeting.

Pure logic: give it the wall-clock time, how long the computer has gone untouched and whether buddy is free to
talk, once a second or so; it answers with something to say, or None.

- "Opening the laptop" = buddy starting, the user coming back after AWAY_SECONDS, or the clock jumping (the
  laptop slept). The greeting for the time of day follows OPEN_DELAY later.
- Morning, afternoon and evening are each greeted once a day; if the laptop is already open when one starts,
  the greeting comes EDGE_DELAY in.
- From 11 PM to 4 AM it asks once whether you're still building, then nudges you to bed `sleep_reminders` times.
- Every GREETING_GAP of use it says hello (wave, sparkle or a smiley); a greeting doesn't come back until
  NO_REPEAT others have. One due while buddy is busy is skipped, not saved up.
What has been said today is kept in a small JSON file so a restart doesn't repeat it.
"""
import json
import random
import tomllib
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from importlib import resources
from pathlib import Path

from buddy.brain import SYSTEM_IDLE_SECONDS

AWAY_SECONDS = SYSTEM_IDLE_SECONDS  # untouched this long = the user is away (buddy is asleep too)
WAKE_GAP = 120.0  # seconds between ticks that mean the laptop was asleep
OPEN_DELAY = (180.0, 240.0)
EDGE_DELAY = (60.0, 300.0)
PERIODS = (("morning", 5, 12), ("afternoon", 12, 17), ("evening", 17, 23))  # name, from hour, to hour
NIGHT_FROM, NIGHT_TO = 23, 4
REMINDER_GAP = (30 * 60.0, 45 * 60.0)
GREETING_GAP = (20 * 60.0, 40 * 60.0)
NO_REPEAT = 2
MAX_STEP = 5.0  # longest tick counted towards the greeting clock
TIME_STYLES = {"morning": "wave", "afternoon": "smile", "evening": "wave", "late_night": "type", "sleep": "type"}
GREETING_STYLES = ("wave", "sparkle", "smile")


@dataclass(frozen=True)
class Say:
    kind: str  # "morning", "afternoon", "evening", "late_night", "sleep" or "greeting"
    style: str  # a buddy.speech style
    text: str


@dataclass
class Lines:
    greetings: dict[str, list[str]] = field(default_factory=dict)  # style -> lines
    time: dict[str, list[str]] = field(default_factory=dict)  # kind -> lines


def load_lines(path: Path | None = None) -> Lines:
    """The lines in buddy/assets/messages.toml that are in use so far."""
    if path is None:
        text = (resources.files("buddy") / "assets" / "messages.toml").read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    data = tomllib.loads(text)
    greetings = {style: list(data["greetings"][style]) for style in ("wave", "sparkle")}
    greetings["smile"] = [""]  # just the smiley; its lines come later
    return Lines(greetings=greetings, time={kind: list(data["time"][kind]) for kind in TIME_STYLES})


def _night_of(now: datetime) -> date:
    """The evening a night belongs to: 1 AM on the 6th is still the night of the 5th."""
    return (now - timedelta(hours=NIGHT_TO)).date()


def _at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour)


class Chatter:
    def __init__(self, lines: Lines, sleep_reminders: int = 2, state_path: Path | None = None, rng=None):
        self.lines = lines
        self.sleep_reminders = sleep_reminders
        self.rng = rng or random.Random()
        self.state_path = Path(state_path) if state_path else None
        self._said: dict[str, str] = {}  # kind -> ISO date it was last said (the night's date for late_night)
        self._night = {"date": "", "count": 0}  # sleep reminders given that night
        self._load()
        self._last: datetime | None = None
        self._away = False
        self._opened = datetime.min
        self._open_delay = 0.0
        self._edge_delay = self.rng.uniform(*EDGE_DELAY)
        self._next_reminder: datetime | None = None
        self._greet_clock = 0.0
        self._greet_gap = self.rng.uniform(*GREETING_GAP)
        self._recent: deque = deque(maxlen=NO_REPEAT)

    def tick(self, now: datetime, idle: float | None, free: bool) -> Say | None:
        step = (now - self._last).total_seconds() if self._last else None
        self._last = now
        away = idle is not None and idle >= AWAY_SECONDS
        if step is None or step > WAKE_GAP or (self._away and not away):
            self._open(now)
        self._away = away
        if away:
            return None
        self._greet_clock += min(max(step or 0.0, 0.0), MAX_STEP)
        say = self._timely(now)
        if say is not None:
            if not free:
                return None  # it keeps until buddy is free
            return self._said_it(say, now)
        if self._greet_clock >= self._greet_gap:
            if not free:
                self._restart_greet_clock()
                return None
            return self._said_it(self._greeting(), now)
        return None

    # --- what's due -------------------------------------------------------

    def _open(self, now: datetime) -> None:
        self._opened = now
        self._open_delay = self.rng.uniform(*OPEN_DELAY)
        self._next_reminder = None
        self._restart_greet_clock()

    def _ready(self, start: datetime) -> datetime:
        return max(self._opened + timedelta(seconds=self._open_delay), start + timedelta(seconds=self._edge_delay))

    def _timely(self, now: datetime) -> Say | None:
        today = now.date()
        for kind, start, end in PERIODS:
            if start <= now.hour < end and self._said.get(kind) != today.isoformat():
                return self._time_say(kind) if now >= self._ready(_at(today, start)) else None
        if now.hour >= NIGHT_FROM or now.hour < NIGHT_TO:
            night = _night_of(now)
            if self._said.get("late_night") != night.isoformat():
                return self._time_say("late_night") if now >= self._ready(_at(night, NIGHT_FROM)) else None
            given = self._night["count"] if self._night["date"] == night.isoformat() else 0
            if given < self.sleep_reminders:
                if self._next_reminder is None:
                    self._next_reminder = self._ready(_at(night, NIGHT_FROM))
                if now >= self._next_reminder:
                    return self._time_say("sleep")
        return None

    def _time_say(self, kind: str) -> Say:
        return Say(kind, TIME_STYLES[kind], self.rng.choice(self.lines.time[kind]))

    def _greeting(self) -> Say:
        fresh = {
            style: [text for text in self.lines.greetings.get(style, []) if (style, text) not in self._recent]
            for style in GREETING_STYLES
        }
        styles = [style for style in GREETING_STYLES if fresh[style]]
        if styles:
            style = self.rng.choice(styles)
            text = self.rng.choice(fresh[style])
        else:  # fewer greetings than NO_REPEAT + 1: take the one heard longest ago
            style, text = self._recent[0]
        return Say("greeting", style, text)

    def _said_it(self, say: Say, now: datetime) -> Say:
        if say.kind == "greeting":
            self._recent.append((say.style, say.text))
        elif say.kind == "sleep":
            night = _night_of(now).isoformat()
            given = self._night["count"] if self._night["date"] == night else 0
            self._night = {"date": night, "count": given + 1}
            self._next_reminder = now + timedelta(seconds=self.rng.uniform(*REMINDER_GAP))
            self._save()
        else:
            self._said[say.kind] = (_night_of(now) if say.kind == "late_night" else now.date()).isoformat()
            if say.kind == "late_night":
                self._next_reminder = now + timedelta(seconds=self.rng.uniform(*REMINDER_GAP))
            self._edge_delay = self.rng.uniform(*EDGE_DELAY)
            self._save()
        self._restart_greet_clock()
        return say

    def _restart_greet_clock(self) -> None:
        self._greet_clock = 0.0
        self._greet_gap = self.rng.uniform(*GREETING_GAP)

    # --- memory between runs ------------------------------------------------

    def _load(self) -> None:
        if self.state_path is None:
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            said, night = data.get("said", {}), data.get("night", {})
            self._said = {str(k): str(v) for k, v in said.items()}
            self._night = {"date": str(night.get("date", "")), "count": int(night.get("count", 0))}
        except (OSError, ValueError, TypeError, AttributeError):
            pass  # missing or broken: start fresh

    def _save(self) -> None:
        if self.state_path is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"said": self._said, "night": self._night}), encoding="utf-8")
        except OSError:
            pass  # forgetting is harmless: at worst a hello is said twice
