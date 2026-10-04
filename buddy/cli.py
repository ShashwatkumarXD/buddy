"""Command line: buddy run | choose | autostart | config | stop."""
import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from importlib import resources
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


CLAUDE_EVENTS = {"thinking": ("UserPromptSubmit", signal.SIGUSR1), "done": ("Stop", signal.SIGUSR2)}


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
        cached = sprites.load_cached(cfg.pokemon, style=cfg.style)
    except sprites.SpriteError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    os.environ["GDK_BACKEND"] = "x11"  # must happen before GTK is imported
    try:
        from buddy import window
    except ImportError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1

    pid_path().write_text(str(os.getpid()))
    try:
        return window.run(cfg, cached)
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
    notes: list[str] = []
    try:
        canonical = sprites.download(name, style=cfg.style, notes=notes)
    except sprites.SpriteError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    for note in notes:
        print(note)
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


def claude_settings_path() -> Path:
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return base / "settings.json"


def _is_buddy_hook(hook) -> bool:
    command = hook.get("command", "") if isinstance(hook, dict) else ""
    return "buddy" in command and command.endswith((" event thinking", " event done"))


def _without_buddy_hooks(settings: dict) -> dict:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                remaining = [hook for hook in group["hooks"] if not _is_buddy_hook(hook)]
                if group["hooks"] and not remaining:
                    continue  # the group held only buddy's hook
                group = {**group, "hooks": remaining}
            kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del settings["hooks"]
    return settings


def cmd_claude(args) -> int:
    path = claude_settings_path()
    if args.state == "off" and not path.exists():
        print("Buddy no longer reacts to Claude Code.")
        return 0
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        settings = json.loads(text) if text.strip() else {}
        if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
            raise ValueError("unexpected structure")
    except (OSError, ValueError) as e:
        print(f"buddy: can't read {path} ({e}); left it unchanged.", file=sys.stderr)
        return 1
    settings = _without_buddy_hooks(settings)
    if args.state == "on":
        if text:
            path.with_name(path.name + ".buddy-backup").write_text(text, encoding="utf-8")
        hooks = settings.setdefault("hooks", {})
        exe = buddy_executable()
        for name, (claude_event, _) in CLAUDE_EVENTS.items():
            groups = hooks.setdefault(claude_event, [])
            if not isinstance(groups, list):
                print(f"buddy: unexpected '{claude_event}' hooks in {path}; left it unchanged.", file=sys.stderr)
                return 1
            groups.append({"hooks": [{"type": "command", "command": f'"{exe}" event {name}', "timeout": 5}]})
        message = "Buddy will react to Claude Code. Restart open Claude Code sessions to pick this up."
    else:
        message = "Buddy no longer reacts to Claude Code."
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".buddy-tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    print(message)
    return 0


def cmd_event(args) -> int:
    """Called by Claude Code hooks: must stay silent and always succeed."""
    try:
        _signal_running(CLAUDE_EVENTS[args.name][1])
    except Exception:
        pass
    return 0


def cmd_guide(args) -> int:
    print((resources.files("buddy") / "guide.txt").read_text(encoding="utf-8"))
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
    p = sub.add_parser("claude", help="react to Claude Code (adds/removes its hooks)")
    p.add_argument("state", choices=["on", "off"])
    p.set_defaults(func=cmd_claude)
    p = sub.add_parser("event", help="used by Claude Code hooks")
    p.add_argument("name", choices=sorted(CLAUDE_EVENTS))
    p.set_defaults(func=cmd_event)
    sub.add_parser("guide", help="show the full guide").set_defaults(func=cmd_guide)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
