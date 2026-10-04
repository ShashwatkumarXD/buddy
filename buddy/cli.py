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
