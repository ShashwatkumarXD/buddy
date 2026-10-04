# Cross-platform Implementation Plan

> Executed inline (superpowers:executing-plans) on `feature/cross-platform`, stacked on PR #1; TDD per task.

**Spec:** `docs/superpowers/specs/2026-10-04-cross-platform-design.md`

## Global Constraints
- No GTK/gi/cairo imports anywhere; GUI code only in `window.py`; `paths.py`, `ipc.py`, `cli.py` stdlib-light.
- `buddy event` must never fail, print only `{}` with `--json`, and stay fast (no PySide6/PIL import).
- Linux behaviour must stay as it is today.

## Review Focus
1. Stale port file / port reused by another program → never treated as buddy (`test_stale_port_file_is_not_running`).
2. Wrong token → command ignored (`test_server_ignores_wrong_token`).
3. `buddy event` with no buddy running → silent and fast (`test_event_without_running_buddy_is_silent`).
4. Windows autostart value / macOS plist content correct without running on those OSes (mocked tests).
5. Window survives a full tick loop off-screen on every OS (`test_window_smoke`, CI matrix).

## Tasks
1. `paths.py` — config/cache/runtime dirs per OS. Tests: each OS via monkeypatched platform/env.
2. `ipc.py` — `Server(token).poll() -> list[str]`, `send(command) -> bool`, port-file handling. Tests: round trip, wrong token, stale file.
3. `cli.py` — use paths + ipc (drop PID file, `/proc`, signals); lazy `sprites` import; per-OS autostart. Tests updated.
4. `matrix.py` on QPainter. Tests on offscreen QImage.
5. `window.py` on Qt (pet + decor windows, IPC poll, macOS tweaks). Offscreen smoke test.
6. Packaging + installers (`pyproject`, `install.sh`, `install.ps1`) + CI workflow + README/guide.
