# Pokémon Buddy — Design

Date: 2026-10-04
Status: Approved in conversation, pending written-spec review

## Goal

A small Pokémon desktop pet that floats above every window (desktop, VS Code, terminal),
wanders along the bottom of the screen in small steps, reacts to clicks and drags, and acts
as the "soul" of the laptop: when CPU/RAM load reaches levels where the laptop starts to lag,
it becomes stressed and reveals a Matrix-style CPU/RAM readout. The readout is hidden unless
the Pokémon is stressed. Installed and configured from the terminal; runs at login.

## Target environment

- Ubuntu 26.04, GNOME Shell 50, **Wayland** session, single 1920×1080 monitor.
- Python 3.14, GTK3 via PyGObject (system `python3-gi`), psutil.
- Native Wayland clients cannot keep-above or self-position on GNOME, so the window runs
  under **XWayland** (`GDK_BACKEND=x11`).

Personal use only: sprites are Nintendo IP fetched from PokéAPI's public sprite repo.

## Approach

Python + GTK3 window under XWayland: undecorated, transparent (RGBA visual), keep-above,
sticky (all workspaces), skip-taskbar/skip-pager. The window is moved programmatically each
frame. An input-shape region limited to the sprite's opaque pixels makes everything else
click-through. Exact window kind (normal keep-above utility window, DOCK type hint, or
override-redirect popup) is decided by the spike below.

**De-risk first:** the first implementation task is a ~20-line throwaway spike window that
verifies on this machine: (1) stays above VS Code and a terminal, (2) clicks pass through the
transparent area, (3) self-positioning works. If the spike fails, stop and switch to a GNOME
Shell extension design before building anything else.

## Components

All in package `buddy/`. Logic modules have no GTK imports so they are unit-testable.

| Module | Responsibility | Depends on |
|---|---|---|
| `config.py` | Load/save `~/.config/buddy/config.toml`; defaults; validation | stdlib `tomllib` |
| `monitor.py` | Sample CPU/RAM; rolling average; stressed decision with hysteresis | psutil (injectable sampler) |
| `brain.py` | Pet state machine: position, velocity, facing, state, active bubble | config values only |
| `sprites.py` | Resolve name→id via PokéAPI, download + cache frames, mirrored frames | urllib, GdkPixbuf (loading only) |
| `matrix.py` | Draw Matrix rain panel with CPU/RAM text onto a cairo context | cairo |
| `window.py` | GTK window, ~30 fps tick, input events → brain, render sprite/bubble/panel, input shape | GTK3, all above |
| `cli.py` | `buddy run/choose/autostart/config/stop` | all above |
| `assets/bubbles/` | `love.png`, `angry.png`, `confused.png` (user-supplied art), drawn at ~48px | — |

### config.toml (defaults)

```toml
pokemon = "pikachu"
style = "gba"        # gba = Mystery Dungeon sprites, ds = Black/White sprites
scale = 2            # sprite pixel scale (0.5–6)
walk_speed = 20      # px/s
[stress]
cpu_enter = 85       # % averaged over window
ram_enter = 90       # %
cpu_exit = 70
ram_exit = 85
window_seconds = 5
```

## Behaviour

### Brain states

- **WALK** — moves along the ground (bottom of the monitor's work area, i.e. above the dock)
  at `walk_speed`. Randomly transitions to IDLE.
- **IDLE** — stands still for a random 2–6 s, then WALK in a random direction.
- **Edge** — on reaching a screen edge: turn around; with 30% chance show ❓ for 1.5 s.
- **DRAGGED** — entered when the pointer is pressed on the sprite and moves > 5 px. Sprite
  follows the cursor (keeping the grab offset). No bubble.
- **FALLING** — on release while above ground: accelerate downward (gravity ~1500 px/s²)
  until reaching ground; then show ❓ for 1.5 s and go IDLE.
- **Click** — press + release with < 5 px movement: ❤️ for 2 s and a small hop
  (upward impulse, then FALLING without the ❓ on landing).
- **STRESSED** — while `monitor.stressed` is true: 💢 bubble persists, Matrix panel visible,
  no walking; small left/right fidget. Click/drag still work; after them it returns to
  STRESSED behaviour while still stressed.

### Bubble priority

DRAGGED → no bubble. Otherwise ❤️ > ❓ > 💢 (transient bubbles override the stress bubble;
💢 returns when they expire).

### Stress detection (hysteresis)

Sample once per second. Enter stressed when the window of the last `window_seconds` samples
is full and mean CPU ≥ `cpu_enter` **or** mean RAM ≥ `ram_enter`. Exit only when **every**
sample in the full window has CPU < `cpu_exit` **and** RAM < `ram_exit`. The panel shows the
latest CPU% and RAM%.

### Sprites

**Style `gba` (default, chosen by the user 2026-10-04):** Mystery Dungeon-style sheets from
PMDCollab SpriteCollab (`sprite/{id:04d}/AnimData.xml`, `Walk-Anim.png`, `Idle-Anim.png`).
The right-facing row (row 2) is used and mirrored for left. Walk plays while moving/falling/
dragged, Idle while standing/stressed. Frames are padded around their centres onto one canvas so
walk and idle stay aligned. Missing on SpriteCollab → still Emerald (Gen III) sprite + a note.
SpriteCollab art is CC BY-NC 4.0: credited in the README; personal use only.

**Style `ds` (the original design, kept but not default):**

- Lookup: `https://pokeapi.co/api/v2/pokemon/{name}` → id and sprite URLs.
- Preferred: Gen-5 animated GIF (`versions.generation-v.black-white.animated.front_default`,
  ids 1–649), split into frames. Fallback: static `front_default` PNG.
- Cached at `~/.cache/buddy/sprites/{name}/`. Horizontally flipped frames for facing direction.
- `buddy run` uses cache only — never touches the network.

## Rendering

Fixed-size transparent window big enough for sprite + bubble above + panel beside it. The
whole window is moved to follow the brain's position. Each frame: clear to transparent, draw
sprite frame (nearest-neighbour scaling), bubble above head, Matrix panel if stressed. Input
shape = sprite's opaque bounding area (updated when the frame/facing changes); panel and
bubble are click-through.

## CLI and installation

- `./install.sh`: create `.venv` with `--system-site-packages` (for system PyGObject),
  `pip install -e .`, symlink `~/.local/bin/buddy`, prompt for a Pokémon (`buddy choose`),
  enable autostart, launch.
- `buddy run` — start (sets `GDK_BACKEND=x11` in-process before GTK is imported). Writes a PID file at
  `$XDG_RUNTIME_DIR/buddy.pid`; refuses to start a second instance.
- `buddy choose <name>` — validate + download sprites, save to config, send `SIGHUP` to a
  running instance which reloads sprites/config.
- `buddy autostart on|off` — write/remove `~/.config/autostart/buddy.desktop`
  (`Exec=env GDK_BACKEND=x11 <path>/buddy run`).
- `buddy config` — open config in `$EDITOR` (fallback `xdg-open`).
- `buddy stop` — `SIGTERM` the running instance.

## Error handling

- No network / unknown Pokémon during `choose`: clear message, config unchanged.
- Missing/corrupt sprite cache at run: print an instruction to run `buddy choose <name>` and
  exit non-zero. (The animated→static fallback happens at download time; only one variant is
  cached.) A failed `choose` never replaces the existing cache.
- XWayland unavailable (GTK fails to open X display): clear message and exit.
- psutil read failure: treat as not stressed, keep running.

## Testing

- pytest unit tests: `brain` (transitions with synthetic ticks/events: click→love, drag→fall→
  confused, edge turn, stress overrides walk, bubble priority), `monitor` (hysteresis with a
  fake sampler), `config` (defaults, round-trip, invalid values), `sprites` (lookup/fallback
  with mocked HTTP).
- Manual: spike window first; then a smoke checklist for the full widget (stays on top over
  VS Code/terminal, click-through, drag/drop, stress via a CPU burn like `stress-ng` or a
  Python busy-loop, autostart after re-login).

## Out of scope (YAGNI)

Multiple Pokémon at once, multi-monitor walking, sound, GUI settings window, distribution
packaging, network/disk/temperature metrics.
