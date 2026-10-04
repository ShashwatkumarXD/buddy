# Cross-platform Buddy (Windows, macOS, Linux) — Design

Date: 2026-10-04 · Status: approved in conversation (option A) · Builds on the two earlier specs.

## Goal

Same Buddy on Windows, macOS and Linux: walking, reactions, drag & drop, stress panel, AI-agent
reactions, `buddy` commands, start at login, installers.

## Decisions

- **Qt (PySide6-Essentials) everywhere** replaces GTK/cairo. Linux keeps running through XWayland
  (`QT_QPA_PLATFORM=xcb` on Wayland sessions). Dependencies become pip-only: PySide6-Essentials,
  psutil, Pillow. Linux additionally needs Qt's X11 libraries (one `apt` line, checked by install.sh).
- **Two top-level windows** (Qt has no input-only window shape): a *pet* window exactly the sprite's
  size that takes mouse input, and a *decor* window for bubble + stress panel created with
  `WindowTransparentForInput`, moved with the pet every frame. Both frameless, always-on-top, tool
  windows that never take focus.
- **Local IPC instead of Unix signals / `/proc`:** the running buddy listens on 127.0.0.1 (random
  port); `<runtime dir>/buddy.port` (mode 0600) holds `{port, token, pid}`. Commands, one line
  `"<token> <command>\n"`, reply `"ok\n"`: `ping`, `thinking`, `done`, `reload`, `quit`. "Running" =
  answers ping with the right token. `buddy event` stays silent, exits 0, and imports nothing heavy.
- **Platform folders** (`buddy/paths.py`, stdlib only): Linux XDG as today; macOS
  `~/Library/Application Support/buddy` + `~/Library/Caches/buddy`; Windows `%APPDATA%\buddy` +
  `%LOCALAPPDATA%\buddy`.
- **Start at login:** Linux `~/.config/autostart/buddy.desktop`; Windows `HKCU\...\Run` value
  running `buddyw.exe run` (no console window); macOS `~/Library/LaunchAgents/com.buddy.pet.plist`.
- **Agent hooks** use forward-slash executable paths (work in bash, cmd and PowerShell).
- **macOS:** `WA_MacAlwaysShowToolWindow`; hide the Dock icon (activation policy *accessory*) and join
  all Spaces via small `ctypes` Objective-C calls (best effort, CI + user verified).
- **Windows:** shows on the current virtual desktop only (pinning to all needs undocumented APIs).
- **Installers:** `install.sh` for Linux and macOS, `install.ps1` for Windows.
- **CI:** GitHub Actions runs the suite on ubuntu/windows/macos with `QT_QPA_PLATFORM=offscreen`,
  including a smoke test that builds the real windows and runs them.

## Unchanged

Brain, monitor, sprites, config, timing, bubble art, agent hook logic, all behaviour and timings.
