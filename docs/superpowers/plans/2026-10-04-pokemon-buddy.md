# Pokémon Buddy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Pokémon desktop pet that walks along the bottom of the screen above all windows, reacts to clicks (❤️) and drag-and-drop (falls back down, ❓), and turns stressed (💢 + Matrix CPU/RAM panel) when the laptop is overloaded.

**Architecture:** A Python package whose logic modules (config, monitor, brain, sprites, matrix) are pure and unit-tested; a thin GTK3 window, forced onto XWayland, renders and forwards mouse events to the brain; a CLI plus `install.sh` handle Pokémon choice, autostart and lifecycle.

**Tech Stack:** Python ≥3.11 (machine has 3.14), system PyGObject/GTK3 + pycairo, psutil, Pillow, pytest, PokéAPI.

**Spec:** `docs/superpowers/specs/2026-10-04-pokemon-buddy-design.md`

## Global Constraints

- Target: Ubuntu 26.04, GNOME 50, **Wayland** session. The window must run under XWayland: `os.environ["GDK_BACKEND"] = "x11"` is set **before** `gi.repository.Gtk` is imported.
- `requires-python = ">=3.11"`; PyGObject comes from the system, so the venv is created with `--system-site-packages`.
- `config.py`, `monitor.py`, `brain.py`, `sprites.py`, `matrix.py` must never import Gtk/Gdk.
- `buddy run` never touches the network; only `buddy choose` does.
- Config defaults verbatim: `pokemon = "pikachu"`, `scale = 2`, `walk_speed = 20`, `cpu_enter = 85`, `ram_enter = 90`, `cpu_exit = 70`, `ram_exit = 85`, `window_seconds = 5`.
- Timings verbatim: ❤️ 2 s, ❓ 1.5 s, idle 2–6 s, click slop 5 px, gravity 1500 px/s², edge-❓ chance 30%.
- Paths honour XDG vars: config `$XDG_CONFIG_HOME/buddy/config.toml`, cache `$XDG_CACHE_HOME/buddy/sprites/<name>/`, PID `$XDG_RUNTIME_DIR/buddy.pid`, autostart `$XDG_CONFIG_HOME/autostart/buddy.desktop`.
- Bubble art is the user's three images, unmodified apart from crop + downscale.
- Personal use only (sprites are Nintendo IP) — no packaging/distribution work.
- Every commit message ends with the trailer line `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Run all commands from the repo root `/home/bytive/Documents/myStuff/buddy`.

## Review Focus

1. **Suspend/resume or a stalled main loop yields a huge tick `dt`** → the pet must not teleport off-screen or through the floor. Pinned by `test_huge_time_step_does_not_escape_screen` (Task 4).
2. **User hand-edits config into nonsense** (exit ≥ enter, strings for numbers, broken TOML) → `load` raises a clear `ConfigError` naming the key; `buddy config` reports it; `buddy run` warns and uses defaults; `buddy choose` refuses to overwrite it. Pinned by `test_invalid_config_raises_clear_error` (Task 2) and `test_choose_refuses_to_overwrite_broken_config` (Task 7).
3. **Stale PID file pointing at a reused PID** → `buddy stop`/`choose` must never signal an unrelated process and `run` must not refuse to start. Pinned by `test_stale_pid_is_ignored_and_not_killed` (Task 7).
4. **`buddy choose` fails midway** (typo, network drop during GIF download) → current Pokémon and cache untouched. Pinned by `test_failed_download_keeps_previous_cache` (Task 5) and `test_choose_failure_leaves_config_unchanged` (Task 7).
5. **Dragging past screen edges / resolution or monitor change** → pet stays inside the work area. Pinned by `test_drag_is_clamped_to_screen` and `test_screen_shrink_pulls_pet_back_into_view` (Task 4).

## File Structure

```
pyproject.toml                 # package metadata, deps, console script, pytest config
install.sh                     # terminal installer (Task 9)
README.md                      # commands + uninstall (Task 9)
buddy/__init__.py
buddy/config.py                # Config dataclasses, load/save/validate
buddy/monitor.py               # Sample, StressMonitor (hysteresis)
buddy/brain.py                 # Bounds, State, Bubble, Brain state machine
buddy/sprites.py               # PokéAPI lookup, download, frame cache
buddy/matrix.py                # MatrixRain panel (cairo)
buddy/window.py                # GTK overlay window (manual-tested)
buddy/cli.py                   # argparse entry point
buddy/assets/bubbles/{love,angry,confused}.png
tests/test_assets.py tests/test_config.py tests/test_monitor.py tests/test_brain.py
tests/test_sprites.py tests/test_matrix.py tests/test_cli.py
spike/spike_window.py          # Task 1 only — throwaway, never committed
```

---

### Task 1: Spike — can an XWayland window float above everything? (manual gate)

**Files:**
- Create (throwaway, do NOT commit): `spike/spike_window.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a decision `WINDOW_MODE` ∈ `"normal" | "dock" | "popup"` used verbatim in Task 8's `buddy/window.py`.

- [ ] **Step 1: Write the spike**

```python
"""Throwaway spike: can an XWayland window float above everything on this GNOME?

Usage: python3 spike/spike_window.py [normal|dock|popup]
"""
import os
import sys

os.environ["GDK_BACKEND"] = "x11"

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"
SIZE = 120

if Gdk.Display.get_default() is None:
    sys.exit("No X11 display: XWayland not available")

win = Gtk.Window(type=Gtk.WindowType.POPUP if MODE == "popup" else Gtk.WindowType.TOPLEVEL)
visual = win.get_screen().get_rgba_visual()
if visual is None:
    sys.exit("No RGBA visual: compositing unavailable")
win.set_visual(visual)
win.set_app_paintable(True)
win.set_decorated(False)
win.set_skip_taskbar_hint(True)
win.set_skip_pager_hint(True)
win.set_accept_focus(False)
win.set_focus_on_map(False)
if MODE == "dock":
    win.set_type_hint(Gdk.WindowTypeHint.DOCK)
elif MODE == "normal":
    win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
if MODE != "popup":
    win.set_keep_above(True)
    win.stick()
win.set_default_size(SIZE, SIZE)
win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)


def draw(_widget, cr):
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.set_source_rgba(0.9, 0.1, 0.1, 1)
    cr.arc(SIZE / 2, SIZE / 2, 30, 0, 6.2832)
    cr.fill()
    return False


win.connect("draw", draw)
win.connect("button-press-event", lambda *_: print("clicked the dot", flush=True))
win.connect("destroy", Gtk.main_quit)

display = Gdk.Display.get_default()
wa = (display.get_primary_monitor() or display.get_monitor(0)).get_workarea()
print(f"mode={MODE} workarea={wa.x},{wa.y} {wa.width}x{wa.height}", flush=True)
state = {"x": wa.x, "n": 0}


def step():
    state["x"] = wa.x if state["x"] > wa.x + wa.width - SIZE else state["x"] + 2
    win.move(state["x"], wa.y + wa.height - SIZE)
    state["n"] += 1
    if state["n"] % 60 == 0:
        print("asked", state["x"], "got", win.get_position(), flush=True)
    return True


win.show_all()
win.input_shape_combine_region(cairo.Region(cairo.RectangleInt(SIZE // 2 - 30, SIZE // 2 - 30, 60, 60)))
GLib.timeout_add(33, step)
GLib.timeout_add_seconds(60, Gtk.main_quit)
Gtk.main()
```

- [ ] **Step 2: Run mode `normal` and have the user check it**

Run: `python3 spike/spike_window.py normal` (it closes itself after 60 s)

Expected terminal output: a `mode=normal workarea=…` line, then `asked X got (X', Y)` lines where X' tracks X.

Ask the user to verify each item and report pass/fail:
1. The red dot slides along the bottom of the usable screen area (above the dock if the dock is at the bottom).
2. It stays visible on top of a **focused, maximised** VS Code and a focused terminal.
3. Clicking the empty corners around the dot (inside its 120×120 square) clicks through to the window underneath.
4. Clicking the dot prints `clicked the dot` **and** keyboard focus stays in the terminal (typing still goes there).
5. It stays visible after switching workspace (Super+PgDn).
6. Pressing Super (Activities): note whether it appears as a window thumbnail (cosmetic, not a blocker).

- [ ] **Step 3: If any of items 1–5 fail, retry with `dock`, then `popup`**

Run: `python3 spike/spike_window.py dock`, then if needed `python3 spike/spike_window.py popup`, with the same checklist.

- [ ] **Step 4: Record the decision**

The first mode that passes items 1–5 is `WINDOW_MODE` for Task 8. If **none** pass, STOP: report to the user that approach 1 is not viable on this machine, and that the design must switch to a GNOME Shell extension (back to brainstorming). Delete the spike afterwards: `rm -r spike`. Nothing is committed in this task.

---

### Task 2: Project scaffold, bubble assets, and config

**Files:**
- Create: `pyproject.toml`, `buddy/__init__.py`, `buddy/config.py`, `buddy/assets/bubbles/{confused,angry,love}.png`
- Test: `tests/test_assets.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `config.StressConfig(cpu_enter: float=85.0, ram_enter: float=90.0, cpu_exit: float=70.0, ram_exit: float=85.0, window_seconds: int=5)` (dataclass)
  - `config.Config(pokemon: str="pikachu", scale: int=2, walk_speed: float=20.0, stress: StressConfig)` (dataclass, mutable)
  - `config.ConfigError(ValueError)`
  - `config.config_path() -> Path`
  - `config.load(path: Path | None = None) -> Config` (missing file → defaults; invalid → `ConfigError` whose message starts with the path and names the key)
  - `config.save(cfg: Config, path: Path | None = None) -> None` (creates parent dir, validates first)
  - `config.validate(cfg: Config) -> None`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "buddy"
version = "0.1.0"
description = "A Pokémon desktop buddy that shows when your laptop is stressed"
requires-python = ">=3.11"
dependencies = ["psutil", "Pillow"]

[project.optional-dependencies]
dev = ["pytest"]

[project.scripts]
buddy = "buddy.cli:main"

[tool.setuptools]
packages = ["buddy"]

[tool.setuptools.package-data]
buddy = ["assets/bubbles/*.png"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `buddy/__init__.py` containing only:

```python
"""Pokémon desktop buddy."""
```

- [ ] **Step 2: Create the venv and install**

Run:
```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q -e ".[dev]"
.venv/bin/python -c "import gi, psutil, PIL, cairo; print('deps ok')"
```
Expected: `deps ok`. (The console script `buddy` will fail until Task 7 creates `buddy/cli.py` — that is fine.)

- [ ] **Step 3: Write the failing asset test**

`tests/test_assets.py`:
```python
from pathlib import Path

from PIL import Image

BUBBLES = Path(__file__).resolve().parent.parent / "buddy" / "assets" / "bubbles"


def test_each_bubble_exists_as_small_transparent_png():
    for name in ("love", "angry", "confused"):
        im = Image.open(BUBBLES / f"{name}.png")
        assert im.mode == "RGBA"
        assert max(im.size) == 96
        assert im.getchannel("A").getextrema()[0] == 0  # has transparent pixels
```

Run: `.venv/bin/pytest tests/test_assets.py -v`
Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 4: Import the user's bubble art (crop to content, downscale to 96 px)**

The user's images live in the session temp dir (they disappear on reboot, so do this now). Mapping: `1.png` = ❓ confused, `2.png` = 💢 angry, `3.png` = ❤️ love.

Run:
```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
from PIL import Image
src = Path("/tmp/claude-1000/-home-bytive-Documents-myStuff-buddy/7bb4372f-8c6b-44ab-81f0-878ff5c0b21e/images")
dst = Path("buddy/assets/bubbles"); dst.mkdir(parents=True, exist_ok=True)
for file, name in (("1.png", "confused"), ("2.png", "angry"), ("3.png", "love")):
    im = Image.open(src / file).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox())
    im.thumbnail((96, 96), Image.LANCZOS)
    im.save(dst / f"{name}.png")
    print(name, im.size)
EOF
```
Expected: three lines, each with a size whose larger side is 96. If the source folder is gone, ask the user to re-send the three images.

Run: `.venv/bin/pytest tests/test_assets.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing config tests**

`tests/test_config.py`:
```python
import pytest

from buddy import config
from buddy.config import Config, StressConfig


def test_missing_file_gives_defaults(tmp_path):
    cfg = config.load(tmp_path / "nope.toml")
    assert cfg == Config()
    assert (cfg.pokemon, cfg.scale, cfg.walk_speed) == ("pikachu", 2, 20)
    assert cfg.stress == StressConfig(85, 90, 70, 85, 5)


def test_round_trip(tmp_path):
    cfg = Config(
        pokemon="eevee",
        scale=3,
        walk_speed=35.5,
        stress=StressConfig(cpu_enter=80, ram_enter=92, cpu_exit=60, ram_exit=80, window_seconds=8),
    )
    path = tmp_path / "sub" / "config.toml"
    config.save(cfg, path)
    assert config.load(path) == cfg


def test_partial_file_fills_in_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('pokemon = " Bulbasaur "\n[stress]\ncpu_enter = 95\n')
    cfg = config.load(path)
    assert cfg.pokemon == "bulbasaur"
    assert cfg.stress.cpu_enter == 95
    assert cfg.stress.ram_enter == 90
    assert cfg.scale == 2


def test_default_path_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.config_path() == tmp_path / "buddy" / "config.toml"


@pytest.mark.parametrize(
    "text, message",
    [
        ("pokemon = \n", "line"),
        ('scale = "big"\n', "scale"),
        ("scale = 0\n", "scale"),
        ("walk_speed = true\n", "walk_speed"),
        ('pokemon = ""\n', "pokemon"),
        ("[stress]\ncpu_exit = 90\n", "cpu_exit"),
        ("[stress]\nram_enter = 150\n", "ram_enter"),
        ("[stress]\nwindow_seconds = 0\n", "window_seconds"),
        ("stress = 3\n", "stress"),
    ],
)
def test_invalid_config_raises_clear_error(tmp_path, text, message):
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(config.ConfigError, match=message) as err:
        config.load(path)
    assert str(err.value).startswith(str(path))


def test_save_refuses_invalid_config(tmp_path):
    with pytest.raises(config.ConfigError):
        config.save(Config(scale=99), tmp_path / "c.toml")
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'config'`.

- [ ] **Step 7: Implement `buddy/config.py`**

```python
"""Settings stored in ~/.config/buddy/config.toml."""
import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """The config file is unreadable or holds invalid values."""


@dataclass
class StressConfig:
    cpu_enter: float = 85.0
    ram_enter: float = 90.0
    cpu_exit: float = 70.0
    ram_exit: float = 85.0
    window_seconds: int = 5


@dataclass
class Config:
    pokemon: str = "pikachu"
    scale: int = 2
    walk_speed: float = 20.0
    stress: StressConfig = field(default_factory=StressConfig)


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "buddy" / "config.toml"


def load(path: Path | None = None) -> Config:
    path = Path(path) if path else config_path()
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        stress = data.get("stress", {})
        if not isinstance(stress, dict):
            raise ConfigError("[stress] must be a table")
        d = StressConfig()
        cfg = Config(
            pokemon=_string(data, "pokemon", Config.pokemon),
            scale=_int(data, "scale", Config.scale),
            walk_speed=_float(data, "walk_speed", Config.walk_speed),
            stress=StressConfig(
                cpu_enter=_float(stress, "cpu_enter", d.cpu_enter),
                ram_enter=_float(stress, "ram_enter", d.ram_enter),
                cpu_exit=_float(stress, "cpu_exit", d.cpu_exit),
                ram_exit=_float(stress, "ram_exit", d.ram_exit),
                window_seconds=_int(stress, "window_seconds", d.window_seconds),
            ),
        )
        validate(cfg)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, ConfigError) as e:
        raise ConfigError(f"{path}: {e}") from None
    return cfg


def save(cfg: Config, path: Path | None = None) -> None:
    validate(cfg)
    path = Path(path) if path else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    s = cfg.stress
    path.write_text(
        f"pokemon = {json.dumps(cfg.pokemon)}\n"
        f"scale = {cfg.scale}\n"
        f"walk_speed = {cfg.walk_speed!r}\n"
        "\n[stress]\n"
        f"cpu_enter = {s.cpu_enter!r}\n"
        f"ram_enter = {s.ram_enter!r}\n"
        f"cpu_exit = {s.cpu_exit!r}\n"
        f"ram_exit = {s.ram_exit!r}\n"
        f"window_seconds = {s.window_seconds}\n",
        encoding="utf-8",
    )


def validate(cfg: Config) -> None:
    if not cfg.pokemon:
        raise ConfigError("pokemon must not be empty")
    if not 1 <= cfg.scale <= 6:
        raise ConfigError("scale must be between 1 and 6")
    if not 1 <= cfg.walk_speed <= 500:
        raise ConfigError("walk_speed must be between 1 and 500")
    s = cfg.stress
    for name, enter, exit_ in (("cpu", s.cpu_enter, s.cpu_exit), ("ram", s.ram_enter, s.ram_exit)):
        if not 0 < enter <= 100:
            raise ConfigError(f"{name}_enter must be between 1 and 100")
        if not 0 <= exit_ < enter:
            raise ConfigError(f"{name}_exit must be lower than {name}_enter")
    if not 1 <= s.window_seconds <= 60:
        raise ConfigError("window_seconds must be between 1 and 60")


def _string(table: dict, key: str, default: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be text, got {value!r}")
    return value.strip().lower()


def _int(table: dict, key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be a whole number, got {value!r}")
    return value


def _float(table: dict, key: str, default: float) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number, got {value!r}")
    return float(value)
```

- [ ] **Step 8: Run tests**

Run: `.venv/bin/pytest tests/test_config.py tests/test_assets.py -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml buddy/__init__.py buddy/config.py buddy/assets tests/test_assets.py tests/test_config.py
git commit -m "Add project scaffold, bubble art, and config loading" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Stress monitor

**Files:**
- Create: `buddy/monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `config.StressConfig` (Task 2).
- Produces:
  - `monitor.Sample(cpu: float, ram: float)` (frozen dataclass)
  - `monitor.psutil_sampler() -> Sample`
  - `monitor.StressMonitor(cfg: StressConfig, sampler: Callable[[], Sample] = psutil_sampler)` with `.tick() -> bool` (call once per second), `.stressed: bool`, `.latest: Sample`

- [ ] **Step 1: Write the failing tests**

`tests/test_monitor.py`:
```python
from buddy.config import StressConfig
from buddy.monitor import Sample, StressMonitor


class FakeSampler:
    def __init__(self, samples):
        self.samples = list(samples)

    def __call__(self):
        sample = self.samples.pop(0)
        if isinstance(sample, Exception):
            raise sample
        return sample


def run(samples):
    monitor = StressMonitor(StressConfig(), FakeSampler(samples))
    states = [monitor.tick() for _ in samples]
    return monitor, states


def cpu(*values, ram=50.0):
    return [Sample(v, ram) for v in values]


def test_needs_a_full_window_before_stressing():
    _, states = run(cpu(100, 100, 100, 100))
    assert states == [False] * 4


def test_sustained_high_cpu_enters_stress():
    _, states = run(cpu(90, 90, 90, 90, 90))
    assert states[-1] is True


def test_single_spike_is_ignored():
    _, states = run(cpu(10, 10, 10, 10, 100))
    assert not any(states)


def test_high_ram_enters_stress():
    _, states = run([Sample(10, 95)] * 5)
    assert states[-1] is True


def test_stays_stressed_between_exit_and_enter_thresholds():
    _, states = run(cpu(90, 90, 90, 90, 90, 75, 75, 75, 75, 75, 75))
    assert all(states[4:])


def test_calms_only_after_a_full_calm_window():
    _, states = run(cpu(90, 90, 90, 90, 90, 50, 50, 50, 50, 50))
    assert states[8] is True  # four calm samples: not yet
    assert states[9] is False  # five calm samples: calm


def test_ram_above_exit_threshold_keeps_stress():
    _, states = run([Sample(90, 50)] * 5 + [Sample(10, 87)] * 6)
    assert all(states[4:])


def test_sampler_failure_means_not_stressed():
    _, states = run(cpu(90, 90, 90, 90, 90) + [OSError("boom")])
    assert states[4] is True
    assert states[5] is False


def test_latest_sample_is_exposed():
    monitor, _ = run([Sample(42, 63)])
    assert monitor.latest == Sample(42, 63)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_monitor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'buddy.monitor'`.

- [ ] **Step 3: Implement `buddy/monitor.py`**

```python
"""CPU/RAM sampling and the 'is the laptop stressed?' decision."""
from collections import deque
from dataclasses import dataclass
from typing import Callable

from buddy.config import StressConfig


@dataclass(frozen=True)
class Sample:
    cpu: float
    ram: float


def psutil_sampler() -> Sample:
    import psutil

    return Sample(cpu=psutil.cpu_percent(interval=None), ram=psutil.virtual_memory().percent)


class StressMonitor:
    """Hysteresis: enter on a high window average, leave only after a fully calm window."""

    def __init__(self, cfg: StressConfig, sampler: Callable[[], Sample] = psutil_sampler):
        self.cfg = cfg
        self._sampler = sampler
        self._window: deque[Sample] = deque(maxlen=cfg.window_seconds)
        self.stressed = False
        self.latest = Sample(0.0, 0.0)

    def tick(self) -> bool:
        try:
            sample = self._sampler()
        except Exception:
            self._window.clear()
            self.stressed = False
            return False
        self.latest = sample
        self._window.append(sample)
        if len(self._window) < self._window.maxlen:
            return self.stressed
        c = self.cfg
        if self.stressed:
            if all(s.cpu < c.cpu_exit and s.ram < c.ram_exit for s in self._window):
                self.stressed = False
        else:
            n = len(self._window)
            cpu = sum(s.cpu for s in self._window) / n
            ram = sum(s.ram for s in self._window) / n
            self.stressed = cpu >= c.cpu_enter or ram >= c.ram_enter
        return self.stressed
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_monitor.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add buddy/monitor.py tests/test_monitor.py
git commit -m "Add CPU/RAM stress monitor with hysteresis" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Brain (pet state machine)

**Files:**
- Create: `buddy/brain.py`
- Test: `tests/test_brain.py`

**Interfaces:**
- Consumes: nothing (plain numbers).
- Produces:
  - `brain.Bounds(left: int, top: int, right: int, floor: int)` (frozen dataclass; `floor` = bottom of the work area)
  - `brain.State` enum: `IDLE, WALK, DRAGGED, FALLING, STRESSED`
  - `brain.Bubble` enum: `LOVE="love", CONFUSED="confused", ANGRY="angry"` (values match asset filenames)
  - `brain.Brain(bounds: Bounds, width: int, height: int, walk_speed: float, rng=None)` with:
    - attributes `x: float`, `y: float` (sprite top-left, screen px), `facing: int` (1 right, -1 left), `state: State`, `stressed: bool`, `bounds: Bounds`, `width`, `height`, `walk_speed`
    - property `bubble -> Bubble | None`, property `ground_y -> float`
    - `tick(dt: float)`, `press(px, py)`, `motion(px, py)`, `release(px, py)` (screen coords), `set_stressed(bool)`, `set_bounds(Bounds)`, `resize(width, height)`
  - module constants `CLICK_SLOP, LOVE_SECONDS, CONFUSED_SECONDS, IDLE_SECONDS, FIDGET_RANGE`

- [ ] **Step 1: Write the failing tests**

`tests/test_brain.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_brain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'buddy.brain'`.

- [ ] **Step 3: Implement `buddy/brain.py`**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_brain.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add buddy/brain.py tests/test_brain.py
git commit -m "Add pet behaviour state machine" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Sprites (PokéAPI lookup, download, cache)

**Files:**
- Create: `buddy/sprites.py`
- Test: `tests/test_sprites.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `sprites.SpriteError(Exception)`
  - `sprites.SpriteInfo(name: str, id: int, animated_url: str | None, static_url: str | None)` (dataclass)
  - `sprites.normalize_name(name: str) -> str`
  - `sprites.cache_dir() -> Path`
  - `sprites.lookup(name, fetch_json=fetch_json) -> SpriteInfo`
  - `sprites.download(name, fetch_json=fetch_json, fetch_bytes=fetch_bytes, root: Path | None = None) -> str` (returns canonical name; atomic cache replace)
  - `sprites.load_cached(name, root: Path | None = None) -> list[tuple[Path, int]]` (frame PNG path, duration ms; frames all the same size, source faces **left**)

- [ ] **Step 1: Write the failing tests**

`tests/test_sprites.py`:
```python
import io
import urllib.error

import pytest
from PIL import Image

from buddy import sprites

ANIMATED = "https://example.test/25.gif"
STATIC = "https://example.test/25.png"


def gif_bytes():
    """Two 20x20 frames with an opaque 4x4 square in different places."""
    frames = []
    for x, y in [(4, 10), (8, 12)]:
        im = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        im.paste((255, 0, 0, 255), (x, y, x + 4, y + 4))
        frames.append(im)
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=[80, 120], loop=0, disposal=2)
    return buf.getvalue()


def png_bytes():
    im = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    im.paste((0, 0, 255, 255), (30, 40, 60, 90))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def api_json(animated=ANIMATED, static=STATIC, name="pikachu"):
    return {
        "id": 25,
        "name": name,
        "sprites": {
            "front_default": static,
            "versions": {"generation-v": {"black-white": {"animated": {"front_default": animated}}}},
        },
    }


def fetch_json_returning(payload):
    return lambda url: payload


def fetch_bytes_from(mapping):
    def fetch(url):
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value

    return fetch


def http_404(url):
    raise urllib.error.HTTPError(url, 404, "Not Found", None, None)


def offline(url):
    raise urllib.error.URLError("no network")


def test_normalize_name():
    assert sprites.normalize_name("  Mr Mime ") == "mr-mime"


def test_cache_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert sprites.cache_dir() == tmp_path / "buddy" / "sprites"


def test_lookup_reads_animated_and_static_urls():
    info = sprites.lookup("pikachu", fetch_json=fetch_json_returning(api_json()))
    assert info == sprites.SpriteInfo("pikachu", 25, ANIMATED, STATIC)


def test_lookup_unknown_name():
    with pytest.raises(sprites.SpriteError, match="No Pokémon called 'pikachuu'"):
        sprites.lookup("pikachuu", fetch_json=http_404)


def test_lookup_offline():
    with pytest.raises(sprites.SpriteError, match="Could not reach PokéAPI"):
        sprites.lookup("pikachu", fetch_json=offline)


def test_download_splits_animated_gif_and_crops(tmp_path):
    name = sprites.download(
        "Pikachu",
        fetch_json=fetch_json_returning(api_json()),
        fetch_bytes=fetch_bytes_from({ANIMATED: gif_bytes()}),
        root=tmp_path,
    )
    assert name == "pikachu"
    frames = sprites.load_cached("pikachu", root=tmp_path)
    assert [ms for _, ms in frames] == [80, 120]
    assert all(Image.open(path).size == (8, 6) for path, _ in frames)


def test_download_falls_back_to_static_png(tmp_path):
    sprites.download(
        "kyurem",
        fetch_json=fetch_json_returning(api_json(animated=None, name="kyurem")),
        fetch_bytes=fetch_bytes_from({STATIC: png_bytes()}),
        root=tmp_path,
    )
    frames = sprites.load_cached("kyurem", root=tmp_path)
    assert len(frames) == 1
    assert Image.open(frames[0][0]).size == (30, 50)


def test_broken_gif_falls_back_to_static_png(tmp_path):
    sprites.download(
        "pikachu",
        fetch_json=fetch_json_returning(api_json()),
        fetch_bytes=fetch_bytes_from({ANIMATED: b"not a gif", STATIC: png_bytes()}),
        root=tmp_path,
    )
    assert len(sprites.load_cached("pikachu", root=tmp_path)) == 1


def test_failed_download_keeps_previous_cache(tmp_path):
    good = fetch_bytes_from({ANIMATED: gif_bytes()})
    sprites.download("pikachu", fetch_json=fetch_json_returning(api_json()), fetch_bytes=good, root=tmp_path)
    dropped = urllib.error.URLError("connection dropped")
    broken = fetch_bytes_from({ANIMATED: dropped, STATIC: dropped})
    with pytest.raises(sprites.SpriteError):
        sprites.download("pikachu", fetch_json=fetch_json_returning(api_json()), fetch_bytes=broken, root=tmp_path)
    assert len(sprites.load_cached("pikachu", root=tmp_path)) == 2


def test_empty_name_is_rejected(tmp_path):
    with pytest.raises(sprites.SpriteError, match="name"):
        sprites.download("   ", fetch_json=offline, fetch_bytes=offline, root=tmp_path)


def test_load_cached_missing_gives_hint(tmp_path):
    with pytest.raises(sprites.SpriteError, match="buddy choose eevee"):
        sprites.load_cached("eevee", root=tmp_path)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_sprites.py -v`
Expected: FAIL with `ImportError: cannot import name 'sprites'`.

- [ ] **Step 3: Implement `buddy/sprites.py`**

```python
"""Find a Pokémon on PokéAPI, download its sprite frames, and cache them on disk."""
import io
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence

API = "https://pokeapi.co/api/v2/pokemon/{name}"
DEFAULT_FRAME_MS = 100
MIN_FRAME_MS = 20


class SpriteError(Exception):
    """A sprite could not be found, downloaded, or loaded."""


@dataclass
class SpriteInfo:
    name: str
    id: int
    animated_url: str | None
    static_url: str | None


def normalize_name(name: str) -> str:
    return "-".join(name.strip().lower().split())


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "buddy" / "sprites"


def fetch_json(url: str, timeout: float = 10) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "buddy-desktop-pet"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_bytes(url: str, timeout: float = 10) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "buddy-desktop-pet"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def lookup(name: str, fetch_json=fetch_json) -> SpriteInfo:
    try:
        data = fetch_json(API.format(name=urllib.parse.quote(name)))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SpriteError(f"No Pokémon called '{name}'.") from None
        raise SpriteError(f"PokéAPI returned an error ({e.code}).") from None
    except OSError as e:
        raise SpriteError(f"Could not reach PokéAPI ({e}). Check your internet connection.") from None
    sprites = data.get("sprites") or {}
    animated = (
        sprites.get("versions", {})
        .get("generation-v", {})
        .get("black-white", {})
        .get("animated", {})
        .get("front_default")
    )
    static = sprites.get("front_default")
    if not animated and not static:
        raise SpriteError(f"'{name}' has no sprites on PokéAPI.")
    return SpriteInfo(name=data["name"], id=data["id"], animated_url=animated, static_url=static)


def decode_frames(data: bytes) -> list[tuple[Image.Image, int]]:
    """Decode a GIF (many frames) or PNG (one frame) into RGBA frames with durations."""
    try:
        image = Image.open(io.BytesIO(data))
        return [
            (frame.convert("RGBA"), max(MIN_FRAME_MS, int(frame.info.get("duration") or DEFAULT_FRAME_MS)))
            for frame in ImageSequence.Iterator(image)
        ]
    except (OSError, ValueError, SyntaxError) as e:
        raise SpriteError(f"Unreadable sprite image ({e}).") from None


def crop_to_content(frames: list[tuple[Image.Image, int]]) -> list[tuple[Image.Image, int]]:
    """Crop every frame to the union of their opaque areas so the pet stands on the ground."""
    boxes = [box for box in (img.getchannel("A").getbbox() for img, _ in frames) if box]
    if not boxes:
        return frames
    union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    return [(img.crop(union), ms) for img, ms in frames]


def download(name: str, fetch_json=fetch_json, fetch_bytes=fetch_bytes, root: Path | None = None) -> str:
    name = normalize_name(name)
    if not name:
        raise SpriteError("Please give a Pokémon name.")
    info = lookup(name, fetch_json=fetch_json)
    frames = []
    if info.animated_url:
        try:
            frames = decode_frames(fetch_bytes(info.animated_url))
        except (SpriteError, OSError):
            frames = []
    if not frames:
        if not info.static_url:
            raise SpriteError(f"Could not download a sprite for '{info.name}'.")
        try:
            frames = decode_frames(fetch_bytes(info.static_url))
        except OSError as e:
            raise SpriteError(f"Could not download the sprite for '{info.name}' ({e}).") from None
    _write_atomically(root or cache_dir(), info.name, crop_to_content(frames))
    return info.name


def load_cached(name: str, root: Path | None = None) -> list[tuple[Path, int]]:
    folder = (root or cache_dir()) / normalize_name(name)
    hint = f"No sprites cached for '{name}'. Run: buddy choose {name}"
    try:
        meta = json.loads((folder / "meta.json").read_text())
        durations = [int(ms) for ms in meta["durations_ms"]]
    except (OSError, ValueError, KeyError, TypeError):
        raise SpriteError(hint) from None
    frames = [(folder / f"frame_{i:03d}.png", ms) for i, ms in enumerate(durations)]
    if not frames or not all(path.is_file() for path, _ in frames):
        raise SpriteError(hint)
    return frames


def _write_atomically(root: Path, name: str, frames: list[tuple[Image.Image, int]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{name}-new-", dir=root))
    old = root / f".{name}-old"
    final = root / name
    try:
        for i, (img, _) in enumerate(frames):
            img.save(tmp / f"frame_{i:03d}.png")
        (tmp / "meta.json").write_text(json.dumps({"name": name, "durations_ms": [ms for _, ms in frames]}))
        shutil.rmtree(old, ignore_errors=True)
        if final.exists():
            final.rename(old)
        tmp.rename(final)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_sprites.py -v`
Expected: all PASS. If `test_download_splits_animated_gif_and_crops` reports size `(20, 20)`, Pillow lost GIF transparency when *writing the test fixture*. Fix the fixture: convert each frame with `im.convert("P", palette=Image.ADAPTIVE)` after reserving index 0 for transparency and pass `transparency=0`. Do not change production code to fit.

- [ ] **Step 5: Live check against the real API (network)**

Run:
```bash
.venv/bin/python -c "
from pathlib import Path; import tempfile
from buddy import sprites
root = Path(tempfile.mkdtemp())
print(sprites.download('pikachu', root=root))
print(len(sprites.load_cached('pikachu', root=root)), 'frames')
"
```
Expected: `pikachu` then a frame count > 1.

- [ ] **Step 6: Commit**

```bash
git add buddy/sprites.py tests/test_sprites.py
git commit -m "Add PokéAPI sprite download and cache" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Matrix stress panel

**Files:**
- Create: `buddy/matrix.py`
- Test: `tests/test_matrix.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pycairo only).
- Produces:
  - constants `matrix.PANEL_W = 120`, `matrix.PANEL_H = 70`
  - `matrix.format_stats(cpu: float, ram: float) -> tuple[str, str]`
  - `matrix.MatrixRain(width=PANEL_W, height=PANEL_H, rng=None)` with `.tick(dt: float)` and `.draw(cr: cairo.Context, x: float, y: float, cpu: float, ram: float)`

- [ ] **Step 1: Write the failing tests**

`tests/test_matrix.py`:
```python
import random

import cairo

from buddy.matrix import PANEL_H, PANEL_W, TAIL, MatrixRain, format_stats


def test_format_stats():
    assert format_stats(92.4, 88.0) == ("CPU  92%", "RAM  88%")
    assert format_stats(100, 5) == ("CPU 100%", "RAM   5%")


def test_rain_stays_bounded_over_time():
    rain = MatrixRain(rng=random.Random(1))
    for _ in range(2000):
        rain.tick(1 / 30)
    assert all(-TAIL <= head <= rain.rows + TAIL for head in rain.heads)


def test_draw_paints_green_panel():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, PANEL_W, PANEL_H)
    cr = cairo.Context(surface)
    rain = MatrixRain(rng=random.Random(1))
    for _ in range(30):
        rain.tick(1 / 30)
    rain.draw(cr, 0, 0, 91, 77)
    surface.flush()
    data = surface.get_data()
    greenish = 0
    for i in range(0, len(data), 4):
        b, g, r, a = data[i], data[i + 1], data[i + 2], data[i + 3]
        if a > 0 and g > r + 40 and g > b + 40:
            greenish += 1
    assert greenish > 50
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_matrix.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'buddy.matrix'`.

- [ ] **Step 3: Implement `buddy/matrix.py`**

```python
"""Matrix-style rain panel that shows CPU/RAM while the buddy is stressed."""
import math
import random

import cairo

PANEL_W = 120
PANEL_H = 70
CELL = 10
TAIL = 6
GLYPHS = "0123456789ABCDEF<>*+=#$%&"
GREEN = (0.0, 1.0, 0.25)


def format_stats(cpu: float, ram: float) -> tuple[str, str]:
    return f"CPU {cpu:3.0f}%", f"RAM {ram:3.0f}%"


class MatrixRain:
    def __init__(self, width: int = PANEL_W, height: int = PANEL_H, rng=None):
        self.width = width
        self.height = height
        self.rng = rng or random.Random()
        self.cols = max(1, width // CELL)
        self.rows = max(1, height // CELL)
        self.heads = [self.rng.uniform(-TAIL, self.rows) for _ in range(self.cols)]
        self.speeds = [self.rng.uniform(4, 12) for _ in range(self.cols)]  # rows per second
        self.grid = [[self.rng.choice(GLYPHS) for _ in range(self.rows)] for _ in range(self.cols)]

    def tick(self, dt: float) -> None:
        dt = min(max(dt, 0.0), 0.1)
        for c in range(self.cols):
            self.heads[c] += self.speeds[c] * dt
            if self.heads[c] - TAIL > self.rows:
                self.heads[c] = self.rng.uniform(-TAIL, 0)
            if self.rng.random() < 0.3:
                self.grid[c][self.rng.randrange(self.rows)] = self.rng.choice(GLYPHS)

    def draw(self, cr: cairo.Context, x: float, y: float, cpu: float, ram: float) -> None:
        cr.save()
        cr.translate(x, y)
        _rounded_rect(cr, 0.5, 0.5, self.width - 1, self.height - 1, 6)
        cr.set_source_rgba(0.0, 0.05, 0.0, 0.85)
        cr.fill_preserve()
        cr.set_source_rgba(*GREEN, 0.9)
        cr.set_line_width(1)
        cr.stroke()
        _rounded_rect(cr, 0.5, 0.5, self.width - 1, self.height - 1, 6)
        cr.clip()

        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(CELL)
        for c in range(self.cols):
            head = int(self.heads[c])
            for k in range(TAIL):
                r = head - k
                if not 0 <= r < self.rows:
                    continue
                if k == 0:
                    cr.set_source_rgba(0.7, 1.0, 0.7, 1.0)
                else:
                    cr.set_source_rgba(*GREEN, 0.6 * (1 - k / TAIL))
                cr.move_to(c * CELL + 1, (r + 1) * CELL - 1)
                cr.show_text(self.grid[c][r])

        cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(15)
        for i, line in enumerate(format_stats(cpu, ram)):
            ext = cr.text_extents(line)
            tx = (self.width - ext.x_advance) / 2
            ty = self.height / 2 + (i - 0.5) * 20 + 6
            cr.set_source_rgba(0, 0, 0, 0.75)
            cr.rectangle(tx - 3, ty - 14, ext.x_advance + 6, 18)
            cr.fill()
            cr.set_source_rgba(0.75, 1.0, 0.75, 1.0)
            cr.move_to(tx, ty)
            cr.show_text(line)
        cr.restore()


def _rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_matrix.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add buddy/matrix.py tests/test_matrix.py
git commit -m "Add Matrix-style CPU/RAM stress panel" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: CLI (choose, autostart, config, stop, run guards)

**Files:**
- Create: `buddy/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `config.load/save/config_path/Config/ConfigError` (Task 2), `sprites.download/load_cached/SpriteError` (Task 5). Lazily imports `buddy.window.run(cfg: Config, frames: list[tuple[Path, int]]) -> int` (Task 8) only inside `cmd_run`.
- Produces:
  - `cli.main(argv: list[str] | None = None) -> int` (console script `buddy`)
  - `cli.read_pid() -> int | None` (only returns a PID whose `/proc/<pid>/cmdline` has an argument named `buddy` and an argument `run`)
  - `cli.pid_path() -> Path`, `cli.autostart_path() -> Path`, `cli.buddy_executable() -> str`
  - `cli.cmd_run/cmd_choose/cmd_autostart/cmd_config/cmd_stop(args) -> int`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import signal
import subprocess
import sys

import pytest

from buddy import cli, config, sprites


@pytest.fixture(autouse=True)
def xdg(tmp_path, monkeypatch):
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        folder = tmp_path / var.lower()
        folder.mkdir()
        monkeypatch.setenv(var, str(folder))
    return tmp_path


@pytest.fixture
def fake_buddy_process():
    """A process whose command line looks like `... buddy run`."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "buddy", "run"])
    yield proc
    proc.kill()
    proc.wait()


def test_autostart_on_writes_desktop_entry(monkeypatch):
    monkeypatch.setattr(cli, "buddy_executable", lambda: "/opt/buddy/bin/buddy")
    assert cli.main(["autostart", "on"]) == 0
    text = cli.autostart_path().read_text()
    assert 'Exec=env GDK_BACKEND=x11 "/opt/buddy/bin/buddy" run' in text
    assert "Type=Application" in text


def test_autostart_off_removes_entry_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(cli, "buddy_executable", lambda: "/opt/buddy/bin/buddy")
    cli.main(["autostart", "on"])
    assert cli.main(["autostart", "off"]) == 0
    assert not cli.autostart_path().exists()
    assert cli.main(["autostart", "off"]) == 0


def test_choose_saves_canonical_name_and_reloads_running_buddy(monkeypatch, capsys):
    monkeypatch.setattr(sprites, "download", lambda name: "mr-mime")
    monkeypatch.setattr(cli, "read_pid", lambda: 4242)
    sent = []
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    assert cli.main(["choose", "Mr Mime"]) == 0
    assert config.load().pokemon == "mr-mime"
    assert sent == [(4242, signal.SIGHUP)]
    assert "Switched to mr-mime" in capsys.readouterr().out


def test_choose_failure_leaves_config_unchanged(monkeypatch, capsys):
    config.save(config.Config(pokemon="eevee"))

    def fail(name):
        raise sprites.SpriteError("No Pokémon called 'pikachuu'.")

    monkeypatch.setattr(sprites, "download", fail)
    assert cli.main(["choose", "pikachuu"]) == 1
    assert config.load().pokemon == "eevee"
    assert "No Pokémon called" in capsys.readouterr().err


def test_choose_refuses_to_overwrite_broken_config(monkeypatch, capsys):
    path = config.config_path()
    path.parent.mkdir(parents=True)
    path.write_text("scale = 0\n")
    monkeypatch.setattr(sprites, "download", lambda name: "eevee")
    assert cli.main(["choose", "eevee"]) == 1
    assert path.read_text() == "scale = 0\n"
    assert "scale" in capsys.readouterr().err


def test_read_pid_recognises_running_buddy(fake_buddy_process):
    cli.pid_path().write_text(str(fake_buddy_process.pid))
    assert cli.read_pid() == fake_buddy_process.pid


def test_stale_pid_is_ignored_and_not_killed():
    other = subprocess.Popen(["sleep", "30"])
    try:
        cli.pid_path().write_text(str(other.pid))
        assert cli.read_pid() is None
        assert cli.main(["stop"]) == 1
        assert other.poll() is None  # still alive
    finally:
        other.kill()
        other.wait()


def test_stop_terminates_running_buddy(fake_buddy_process):
    cli.pid_path().write_text(str(fake_buddy_process.pid))
    assert cli.main(["stop"]) == 0
    assert fake_buddy_process.wait(timeout=5) == -signal.SIGTERM


def test_run_refuses_second_instance(monkeypatch, capsys):
    monkeypatch.setattr(cli, "read_pid", lambda: 123)
    assert cli.main(["run"]) == 1
    assert "already running" in capsys.readouterr().out


def test_run_without_sprites_explains_how_to_fix(capsys):
    assert cli.main(["run"]) == 1
    assert "buddy choose pikachu" in capsys.readouterr().err


def test_config_command_validates_after_editing(monkeypatch, capsys):
    monkeypatch.setenv("EDITOR", "true")
    monkeypatch.delenv("VISUAL", raising=False)
    assert cli.main(["config"]) == 0  # creates defaults
    assert config.config_path().exists()
    assert "Config OK" in capsys.readouterr().out
    config.config_path().write_text("[stress]\ncpu_exit = 99\n")
    assert cli.main(["config"]) == 1
    assert "cpu_exit" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'cli'`.

- [ ] **Step 3: Implement `buddy/cli.py`**

```python
"""Command line: buddy run | choose | autostart | config | stop."""
import argparse
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from buddy import config, sprites

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Buddy
Comment=Pokémon desktop buddy
Exec=env GDK_BACKEND=x11 "{exe}" run
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
NoDisplay=true
"""


def pid_path() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()) / "buddy.pid"


def autostart_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "buddy.desktop"


def buddy_executable() -> str:
    return str(Path(sys.argv[0]).resolve())


def _is_buddy_process(pid: int) -> bool:
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    names = [Path(os.fsdecode(arg)).name for arg in args if arg]
    return "buddy" in names and "run" in names


def read_pid() -> int | None:
    try:
        pid = int(pid_path().read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if _is_buddy_process(pid) else None


def _signal_running(sig: int) -> bool:
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return False
    return True


def _remove_own_pid() -> None:
    try:
        if pid_path().read_text().strip() == str(os.getpid()):
            pid_path().unlink()
    except OSError:
        pass


def cmd_run(args) -> int:
    pid = read_pid()
    if pid is not None:
        print(f"Buddy is already running (pid {pid}).")
        return 1
    try:
        cfg = config.load()
    except config.ConfigError as e:
        print(f"buddy: {e}\nbuddy: using default settings for now (fix with: buddy config)", file=sys.stderr)
        cfg = config.Config()
    try:
        frames = sprites.load_cached(cfg.pokemon)
    except sprites.SpriteError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    os.environ["GDK_BACKEND"] = "x11"  # must happen before GTK is imported
    from buddy import window

    pid_path().write_text(str(os.getpid()))
    try:
        return window.run(cfg, frames)
    finally:
        _remove_own_pid()


def cmd_choose(args) -> int:
    try:
        cfg = config.load()
    except config.ConfigError as e:
        print(f"buddy: {e}\nbuddy: fix it first with: buddy config", file=sys.stderr)
        return 1
    name = args.name
    if not name:
        try:
            name = input(f"Which Pokémon? [{cfg.pokemon}] ").strip()
        except EOFError:
            name = ""
        name = name or cfg.pokemon
    print(f"Fetching {name}…")
    try:
        canonical = sprites.download(name)
    except sprites.SpriteError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    cfg.pokemon = canonical
    config.save(cfg)
    if _signal_running(signal.SIGHUP):
        print(f"Switched to {canonical}!")
    else:
        print(f"Saved {canonical}. Start it with: buddy run")
    return 0


def cmd_autostart(args) -> int:
    path = autostart_path()
    if args.state == "on":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DESKTOP_ENTRY.format(exe=buddy_executable()))
        print(f"Buddy will start at login ({path}).")
    else:
        path.unlink(missing_ok=True)
        print("Buddy will no longer start at login.")
    return 0


def cmd_config(args) -> int:
    path = config.config_path()
    if not path.exists():
        config.save(config.Config(), path)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or ("nano" if shutil.which("nano") else None)
    if editor:
        subprocess.call([*shlex.split(editor), str(path)])
    else:
        print(f"Settings file: {path}")
    try:
        config.load(path)
    except config.ConfigError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    print("Config OK.")
    if _signal_running(signal.SIGHUP):
        print("Buddy reloaded.")
    return 0


def cmd_stop(args) -> int:
    pid = read_pid()
    if pid is None:
        print("Buddy is not running.")
        return 1
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if read_pid() != pid:
            break
        time.sleep(0.1)
    print("Buddy stopped.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="buddy", description="A Pokémon that lives on your desktop.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="start buddy").set_defaults(func=cmd_run)
    p = sub.add_parser("choose", help="pick your Pokémon")
    p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_choose)
    p = sub.add_parser("autostart", help="start buddy when you log in")
    p.add_argument("state", choices=["on", "off"])
    p.set_defaults(func=cmd_autostart)
    sub.add_parser("config", help="edit settings").set_defaults(func=cmd_config)
    sub.add_parser("stop", help="stop buddy").set_defaults(func=cmd_stop)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add buddy/cli.py tests/test_cli.py
git commit -m "Add buddy command line" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: GTK overlay window (manual verification)

**Files:**
- Create: `buddy/window.py`

**Interfaces:**
- Consumes: `config.load/Config/ConfigError` (Task 2), `monitor.StressMonitor` (Task 3), `brain.Bounds/Brain/Bubble` (Task 4), `sprites.load_cached/SpriteError` (Task 5), `matrix.MatrixRain/PANEL_W/PANEL_H` (Task 6), `WINDOW_MODE` decided in Task 1.
- Produces: `window.run(cfg: Config, frames: list[tuple[Path, int]]) -> int` (called by `cli.cmd_run`; blocks in `Gtk.main()`; returns 0 on normal quit, 1 on display failure). Handles SIGHUP (reload config + sprites), SIGTERM/SIGINT (quit).

- [ ] **Step 1: Implement `buddy/window.py`**

Set `WINDOW_MODE` to the value recorded in Task 1, Step 4.

```python
"""Transparent always-on-top GTK3 window that draws the buddy. Runs under XWayland."""
import signal
import sys
import time
from importlib import resources
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from buddy import config as config_mod  # noqa: E402
from buddy import sprites  # noqa: E402
from buddy.brain import Bounds, Brain, Bubble  # noqa: E402
from buddy.config import Config  # noqa: E402
from buddy.matrix import PANEL_H, PANEL_W, MatrixRain  # noqa: E402
from buddy.monitor import StressMonitor  # noqa: E402

WINDOW_MODE = "normal"  # "normal" | "dock" | "popup" — chosen by the Task 1 spike
FPS = 30
BUBBLE_SIZE = 48
MARGIN = 4


class Sprite:
    """Scaled animation frames; source art faces left, mirrored copies face right."""

    def __init__(self, frames: list[tuple[Path, int]], scale: int):
        self.left, self.right, self.durations = [], [], []
        for path, ms in frames:
            pb = GdkPixbuf.Pixbuf.new_from_file(str(path))
            pb = pb.scale_simple(pb.get_width() * scale, pb.get_height() * scale, GdkPixbuf.InterpType.NEAREST)
            self.left.append(pb)
            self.right.append(pb.flip(True))
            self.durations.append(ms)
        self.width = self.left[0].get_width()
        self.height = self.left[0].get_height()
        self.index = 0
        self._elapsed = 0.0

    def advance(self, dt_ms: float) -> None:
        self._elapsed += dt_ms
        while self._elapsed >= self.durations[self.index]:
            self._elapsed -= self.durations[self.index]
            self.index = (self.index + 1) % len(self.durations)

    def frame(self, facing: int) -> GdkPixbuf.Pixbuf:
        return (self.right if facing > 0 else self.left)[self.index]


def _load_bubbles() -> dict[Bubble, GdkPixbuf.Pixbuf]:
    bubbles = {}
    for bubble in Bubble:
        ref = resources.files("buddy") / "assets" / "bubbles" / f"{bubble.value}.png"
        with resources.as_file(ref) as path:
            bubbles[bubble] = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), BUBBLE_SIZE, BUBBLE_SIZE, True)
    return bubbles


class BuddyWindow(Gtk.Window):
    def __init__(self, cfg: Config, frames: list[tuple[Path, int]]):
        super().__init__(type=Gtk.WindowType.POPUP if WINDOW_MODE == "popup" else Gtk.WindowType.TOPLEVEL)
        visual = self.get_screen().get_rgba_visual()
        if visual is None:
            raise RuntimeError("no transparent (RGBA) visual — is the compositor running?")
        self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        if WINDOW_MODE == "dock":
            self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        elif WINDOW_MODE == "normal":
            self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        if WINDOW_MODE != "popup":
            self.set_keep_above(True)
            self.stick()
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("destroy", Gtk.main_quit)

        self.bubbles = _load_bubbles()
        self.matrix = MatrixRain(PANEL_W, PANEL_H)
        self.cfg = cfg
        self.sprite = Sprite(frames, cfg.scale)
        self.monitor = StressMonitor(cfg.stress)
        self.brain = Brain(self._bounds(), self.sprite.width, self.sprite.height, cfg.walk_speed)
        self._moved_to = None
        self._layout()

        screen = self.get_screen()
        screen.connect("size-changed", self._on_screen_changed)
        screen.connect("monitors-changed", self._on_screen_changed)
        self._last = time.monotonic()
        GLib.timeout_add(1000 // FPS, self._on_tick)
        GLib.timeout_add_seconds(1, self._on_monitor)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGHUP, self.reload)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._quit)

    # --- geometry --------------------------------------------------------

    def _bounds(self) -> Bounds:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        wa = monitor.get_workarea()
        return Bounds(left=wa.x, top=wa.y, right=wa.x + wa.width, floor=wa.y + wa.height)

    def _layout(self) -> None:
        """Window = [panel | sprite | panel] wide; bubble row above the sprite; bottoms aligned."""
        s = self.sprite
        self.sprite_off_x = PANEL_W + MARGIN
        self.win_w = s.width + 2 * (PANEL_W + MARGIN)
        self.win_h = max(BUBBLE_SIZE + MARGIN + s.height, PANEL_H)
        self.sprite_off_y = self.win_h - s.height
        self.panel_y = self.win_h - PANEL_H
        self.set_size_request(self.win_w, self.win_h)
        self.resize(self.win_w, self.win_h)
        if self.get_realized():
            self.update_input_shape()

    def update_input_shape(self) -> None:
        rect = cairo.RectangleInt(self.sprite_off_x, self.sprite_off_y, self.sprite.width, self.sprite.height)
        self.input_shape_combine_region(cairo.Region(rect))

    def _on_screen_changed(self, *_):
        self.brain.set_bounds(self._bounds())

    # --- loop ------------------------------------------------------------

    def _on_tick(self) -> bool:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        self.brain.tick(dt)
        self.sprite.advance(min(dt, 0.1) * 1000)
        if self.brain.stressed:
            self.matrix.tick(dt)
        target = (int(self.brain.x) - self.sprite_off_x, int(self.brain.y) - self.sprite_off_y)
        if target != self._moved_to:
            self.move(*target)
            self._moved_to = target
        self.queue_draw()
        return True

    def _on_monitor(self) -> bool:
        self.brain.set_stressed(self.monitor.tick())
        return True

    def _on_draw(self, _widget, cr) -> bool:
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        b = self.brain
        Gdk.cairo_set_source_pixbuf(cr, self.sprite.frame(b.facing), self.sprite_off_x, self.sprite_off_y)
        cr.paint()
        bubble = b.bubble
        if bubble is not None:
            bx = self.sprite_off_x + (self.sprite.width - BUBBLE_SIZE) // 2
            by = self.sprite_off_y - BUBBLE_SIZE - MARGIN
            Gdk.cairo_set_source_pixbuf(cr, self.bubbles[bubble], bx, by)
            cr.paint()
        if b.stressed:
            room_right = b.bounds.right - (b.x + self.sprite.width)
            px = self.sprite_off_x + self.sprite.width + MARGIN if room_right >= PANEL_W + MARGIN else 0
            latest = self.monitor.latest
            self.matrix.draw(cr, px, self.panel_y, latest.cpu, latest.ram)
        return False

    # --- input -----------------------------------------------------------

    def _on_press(self, _widget, event) -> bool:
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.brain.press(event.x_root, event.y_root)
        return True

    def _on_motion(self, _widget, event) -> bool:
        self.brain.motion(event.x_root, event.y_root)
        return True

    def _on_release(self, _widget, event) -> bool:
        if event.button == 1:
            self.brain.release(event.x_root, event.y_root)
        return True

    # --- signals ---------------------------------------------------------

    def reload(self) -> bool:
        try:
            cfg = config_mod.load()
            frames = sprites.load_cached(cfg.pokemon)
        except (config_mod.ConfigError, sprites.SpriteError) as e:
            print(f"buddy: reload skipped: {e}", file=sys.stderr)
            return True
        self.cfg = cfg
        self.sprite = Sprite(frames, cfg.scale)
        self.monitor = StressMonitor(cfg.stress)
        self.brain.walk_speed = cfg.walk_speed
        self.brain.resize(self.sprite.width, self.sprite.height)
        self._layout()
        return True  # keep the SIGHUP handler installed

    def _quit(self) -> bool:
        Gtk.main_quit()
        return False


def run(cfg: Config, frames: list[tuple[Path, int]]) -> int:
    if Gdk.Display.get_default() is None:
        print(
            "buddy: could not open an X11 display. On Wayland buddy needs XWayland "
            "(sudo apt install xwayland).",
            file=sys.stderr,
        )
        return 1
    try:
        win = BuddyWindow(cfg, frames)
    except RuntimeError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    win.show_all()
    win.update_input_shape()
    Gtk.main()
    return 0
```

- [ ] **Step 2: Import smoke check**

Run: `GDK_BACKEND=x11 .venv/bin/python -c "import buddy.window as w; print('import ok', w.WINDOW_MODE)"`
Expected: `import ok <mode>`.

- [ ] **Step 3: Launch with a real sprite**

Run:
```bash
.venv/bin/buddy choose pikachu
.venv/bin/buddy run &
```
Expected: `Saved pikachu. Start it with: buddy run`, then Pikachu appears at the bottom-centre of the screen.

- [ ] **Step 4: Manual checklist (ask the user to confirm each)**

1. Pikachu idles, then walks in small steps along the bottom of the usable screen area, and turns around at the screen edges (sometimes with ❓).
2. It stays on top of focused VS Code and terminal windows, and on every workspace.
3. Clicking Pikachu → ❤️ for ~2 s and a small hop; keyboard focus stays in the previous app.
4. Click-hold-drag → it follows the cursor with no bubble; release mid-screen → falls to the ground → ❓.
5. Clicking right next to (not on) Pikachu reaches the window underneath.
6. Stress test — run `for i in $(seq $(nproc)); do timeout 25 sh -c 'while :; do :; done' & done`. Within ~5 s: 💢 appears, Pikachu fidgets in place, and the green Matrix panel shows CPU/RAM next to it (on the left when near the right edge). About 5 s after the loops end, 💢 and the panel disappear and it walks again.
7. `.venv/bin/buddy choose eevee` while running → it switches to Eevee without restarting.
8. `.venv/bin/buddy stop` → it disappears; `buddy stop` again → `Buddy is not running.`

Fix any failures (re-run the full test suite after code changes) before moving on.

- [ ] **Step 5: Commit**

```bash
git add buddy/window.py
git commit -m "Add transparent always-on-top buddy window" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Installer, README, and autostart check

**Files:**
- Create: `install.sh`, `README.md`

**Interfaces:**
- Consumes: console script `buddy` with `choose`, `autostart on`, `stop`, `run` (Task 7).
- Produces: a one-command install that leaves `~/.local/bin/buddy`, `~/.config/autostart/buddy.desktop`, and a running buddy.

- [ ] **Step 1: Write `install.sh`**

```bash
#!/usr/bin/env bash
# Install buddy: ./install.sh [pokemon-name]
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
REPO="$PWD"
BUDDY="$REPO/.venv/bin/buddy"
LOG_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/buddy"

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "GTK bindings are missing. Install them with: sudo apt install python3-gi gir1.2-gtk-3.0"
    exit 1
fi
command -v Xwayland >/dev/null || echo "warning: Xwayland not found; on Wayland buddy needs it (sudo apt install xwayland)"

echo "Setting up Python environment…"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --quiet -e .

mkdir -p "$HOME/.local/bin" "$LOG_DIR"
ln -sf "$BUDDY" "$HOME/.local/bin/buddy"

if [ $# -ge 1 ]; then "$BUDDY" choose "$1"; else "$BUDDY" choose; fi
"$BUDDY" autostart on
"$BUDDY" stop >/dev/null 2>&1 || true
setsid -f "$BUDDY" run >"$LOG_DIR/buddy.log" 2>&1 </dev/null

echo
echo "Buddy is running! Commands:"
echo "  buddy choose <name>    switch Pokémon"
echo "  buddy config           edit thresholds, size, speed"
echo "  buddy autostart off    don't start at login"
echo "  buddy stop / buddy run"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "Note: add ~/.local/bin to your PATH to use the 'buddy' command." ;;
esac
```

Run: `chmod +x install.sh`

- [ ] **Step 2: Write `README.md`**

````markdown
# Buddy

A Pokémon that lives above your windows. Click it for love, drag it around, and watch it get
stressed (with a Matrix CPU/RAM readout) when your laptop is overloaded.

Built for Ubuntu GNOME on Wayland (runs through XWayland). Personal use only — sprites come
from PokéAPI and are Nintendo's property.

## Install

```bash
./install.sh            # asks which Pokémon
./install.sh charmander # or pass it directly
```

## Commands

| Command | What it does |
|---|---|
| `buddy choose <name>` | Switch Pokémon (Gen 1–5 are animated) |
| `buddy config` | Edit `~/.config/buddy/config.toml` (thresholds, `scale`, `walk_speed`) |
| `buddy autostart on\|off` | Start at login or not |
| `buddy run` / `buddy stop` | Start / stop |

Logs from the installer launch: `~/.cache/buddy/buddy.log`.

## Uninstall

```bash
buddy stop; buddy autostart off
rm ~/.local/bin/buddy
rm -r ~/.config/buddy ~/.cache/buddy
```
````

- [ ] **Step 3: Run the installer end to end**

Run: `./install.sh pikachu`
Expected: ends with `Buddy is running!`, Pikachu is visible, and:
```bash
readlink ~/.local/bin/buddy          # → <repo>/.venv/bin/buddy
cat ~/.config/autostart/buddy.desktop  # Exec=env GDK_BACKEND=x11 "<repo>/.venv/bin/buddy" run
pgrep -af "buddy run"                 # one process
```

- [ ] **Step 4: Re-run to prove it is idempotent**

Run: `./install.sh pikachu && pgrep -af "buddy run" | wc -l`
Expected: `1` (the old instance was stopped, a single new one runs).

- [ ] **Step 5: Autostart check (user)**

Ask the user to log out and back in. Expected: Pikachu appears within ~5 s of the desktop loading. If not, check `journalctl --user -b | grep -i buddy`.

- [ ] **Step 6: Full test suite and commit**

Run: `.venv/bin/pytest -v`
Expected: all PASS.

```bash
git add install.sh README.md
git commit -m "Add installer and README" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
