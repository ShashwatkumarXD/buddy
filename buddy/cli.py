"""Command line: buddy run | stop | choose | config | autostart | agents | guide."""
import argparse
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable

from buddy import config, ipc, paths

# `buddy event` runs on every AI-agent prompt, so heavy modules (sprites → Pillow, window → Qt)
# are imported inside the commands that need them.

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Buddy
Comment=Pokémon desktop buddy
Exec="{exe}" run --foreground
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
NoDisplay=true
"""
MAC_AGENT_LABEL = "com.buddy.pet"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DETACHED_PROCESS = 0x00000008  # Windows process flags (subprocess only defines them on Windows)
CREATE_NEW_PROCESS_GROUP = 0x00000200
START_TIMEOUT = 15.0  # seconds `buddy run` waits to see the new buddy answer
EVENTS = ("thinking", "done")


@dataclass(frozen=True)
class Agent:
    """An AI coding CLI whose hooks can run `buddy event thinking|done`."""

    key: str
    title: str
    settings: Callable[[], Path]
    events: dict[str, str]  # buddy event -> the agent's hook event
    timeout: int  # in the agent's own unit
    json_output: bool = False  # hook stdout must be JSON (Gemini)
    note: str = ""


AGENTS = {
    "claude": Agent(
        "claude",
        "Claude Code",
        lambda: Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "settings.json",
        {"thinking": "UserPromptSubmit", "done": "Stop"},
        timeout=5,
    ),
    "gemini": Agent(
        "gemini",
        "Gemini CLI",
        lambda: Path.home() / ".gemini" / "settings.json",
        {"thinking": "BeforeAgent", "done": "AfterAgent"},
        timeout=5000,
        json_output=True,
    ),
    "codex": Agent(
        "codex",
        "Codex",
        lambda: Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "hooks.json",
        {"thinking": "UserPromptSubmit", "done": "Stop"},
        timeout=5,
        note="Approve the new hooks once with /hooks inside Codex.",
    ),
}


def _platform() -> str:
    return sys.platform


def buddy_executable() -> str:
    exe = Path(sys.argv[0]).resolve()
    if _platform().startswith("win") and not exe.exists() and exe.with_suffix(".exe").exists():
        exe = exe.with_suffix(".exe")
    return str(exe)


def gui_executable() -> str:
    """On Windows, `buddyw.exe` starts buddy without a console window."""
    exe = Path(buddy_executable())
    gui = exe.with_name("buddyw.exe")
    return str(gui) if gui.exists() else str(exe)


def autostart_path() -> Path | None:
    platform = _platform()
    if platform.startswith("win"):
        return None  # Windows uses the registry
    if platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{MAC_AGENT_LABEL}.plist"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart" / "buddy.desktop"


def _set_windows_autostart(command: str | None) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if command is None:
            try:
                winreg.DeleteValue(key, "Buddy")
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, "Buddy", 0, winreg.REG_SZ, command)


def background_command() -> list[str]:
    """The command `buddy run` launches; pythonw.exe on Windows so no console window pops up."""
    python = Path(sys.executable)
    if _platform().startswith("win") and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    # -P: don't put the current folder on sys.path, or a stray secrets.py there would be imported.
    return [str(python), "-P", "-m", "buddy.cli", "run", "--foreground"]


def _start_in_background() -> int:
    """Start buddy detached from this terminal, so closing the terminal doesn't stop it."""
    log = paths.cache_dir() / "buddy.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if _platform().startswith("win"):
        detach = {"creationflags": DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP}
    else:
        detach = {"start_new_session": True}  # own session: no hang-up when the terminal closes
    with open(log, "w", encoding="utf-8") as err:
        child = subprocess.Popen(
            background_command(),
            cwd=Path.home(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err,
            **detach,
        )
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if ipc.is_running():
            print("Buddy is running. It stays until you run: buddy stop")
            return 0
        if child.poll() is not None:
            reason = log.read_text(encoding="utf-8").strip()
            print(reason or f"buddy: it stopped right after starting (see {log})", file=sys.stderr)
            return 1
        time.sleep(0.1)
    print(f"Buddy is still starting. If it doesn't appear, see {log}")
    return 0


def cmd_run(args) -> int:
    from buddy import sprites

    if ipc.is_running():
        print("Buddy is already running.")
        return 1
    try:
        cfg = config.load()
    except config.ConfigError as e:
        print(f"buddy: {e}\nbuddy: using default settings for now (fix with: buddy config)", file=sys.stderr)
        cfg = config.salvage()
    try:
        cached = sprites.load_cached(cfg.pokemon, style=cfg.style)
    except sprites.SpriteError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    if not args.foreground:
        return _start_in_background()
    override = os.environ.get("BUDDY_QT_PLATFORM")
    if override:
        os.environ["QT_QPA_PLATFORM"] = override
    elif _platform().startswith("linux") and os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY"):
        # Wayland won't let apps stay on top or place themselves; XWayland does.
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    try:
        from buddy import window
    except ImportError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    return window.run(cfg, cached)


def cmd_choose(args) -> int:
    from buddy import sprites

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
    if ipc.send("reload"):
        print(f"Switched to {canonical}!")
    else:
        print(f"Saved {canonical}. Start it with: buddy run")
    return 0


def cmd_autostart(args) -> int:
    on = args.state == "on"
    platform = _platform()
    if platform.startswith("win"):
        _set_windows_autostart(f'"{Path(gui_executable()).as_posix()}" run --foreground' if on else None)
    else:
        path = autostart_path()
        if on:
            path.parent.mkdir(parents=True, exist_ok=True)
            if platform == "darwin":
                agent = {"Label": MAC_AGENT_LABEL, "ProgramArguments": [buddy_executable(), "run", "--foreground"], "RunAtLoad": True}
                path.write_bytes(plistlib.dumps(agent))
            else:
                path.write_text(DESKTOP_ENTRY.format(exe=buddy_executable()))
        else:
            path.unlink(missing_ok=True)
    print("Buddy will start at login." if on else "Buddy will no longer start at login.")
    return 0


def _editor() -> tuple[list[str] | None, bool]:
    """The editor command, and whether it blocks until editing is finished."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        return shlex.split(editor), True
    platform = _platform()
    if platform.startswith("win"):
        return ["notepad"], False  # Windows 11 Notepad may hand off to an open window and exit
    if platform == "darwin":
        return ["open", "-t"], False  # TextEdit stays running after its window closes
    return (["nano"], True) if shutil.which("nano") else (None, True)


def cmd_config(args) -> int:
    from buddy import sprites

    path = config.config_path()
    if not path.exists():
        config.save(config.Config(), path)
    editor, waits = _editor()
    if editor is None:
        print(f"Settings file: {path}")
    elif waits:
        subprocess.call([*editor, str(path)])
    else:
        subprocess.Popen([*editor, str(path)])
        try:
            input("Press Enter here once you've saved your changes… ")
        except EOFError:
            pass
    try:
        cfg = config.load(path)
    except config.ConfigError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    try:
        sprites.load_cached(cfg.pokemon, style=cfg.style)
    except sprites.SpriteError as e:
        print(f"buddy: settings are valid, but {e}", file=sys.stderr)
        return 1
    print("Config OK.")
    if ipc.send("reload"):
        print("Buddy reloaded.")
    return 0


def cmd_stop(args) -> int:
    if not ipc.send("quit"):
        print("Buddy is not running.")
        return 1
    for _ in range(30):
        if not ipc.is_running():
            break
        time.sleep(0.1)
    print("Buddy stopped.")
    return 0


def claude_settings_path() -> Path:
    return AGENTS["claude"].settings()


def _is_buddy_hook(hook) -> bool:
    command = hook.get("command", "") if isinstance(hook, dict) else ""
    return "buddy" in command and command.removesuffix(" --json").endswith((" event thinking", " event done"))


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


def _buddy_hook(agent: Agent, event: str) -> dict:
    exe = buddy_executable().replace("\\", "/")  # forward slashes work in bash, cmd and PowerShell
    if any(ch.isspace() or ch in "\"'$`&;|()<>" for ch in exe):
        exe = f'"{exe}"'  # PowerShell would read a quoted first word as a string, so quote only when needed
    command = f"{exe} event {event}" + (" --json" if agent.json_output else "")
    hook = {"type": "command", "command": command, "timeout": agent.timeout}
    return {"name": f"buddy-{event}", **hook} if agent.json_output else hook


def set_agent_hooks(agent: Agent, enable: bool) -> int:
    """Add or remove buddy's hooks in one agent's settings file, leaving everything else alone."""
    path = agent.settings()
    if not enable and not path.exists():
        print(f"{agent.title}: buddy no longer reacts.")
        return 0
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        settings = json.loads(text) if text.strip() else {}
        if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
            raise ValueError("unexpected structure")
    except (OSError, ValueError) as e:
        print(f"buddy: can't read {path} ({e}); left it unchanged.", file=sys.stderr)
        return 1
    target = path.resolve() if path.exists() else path  # write through a dotfiles symlink
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o600  # may hold API keys
    settings = _without_buddy_hooks(settings)
    if enable:
        if text:
            _write_with_mode(path.with_name(path.name + ".buddy-backup"), text, mode)
        hooks = settings.setdefault("hooks", {})
        for event, agent_event in agent.events.items():
            groups = hooks.setdefault(agent_event, [])
            if not isinstance(groups, list):
                print(f"buddy: unexpected '{agent_event}' hooks in {path}; left it unchanged.", file=sys.stderr)
                return 1
            groups.append({"hooks": [_buddy_hook(agent, event)]})
        message = f"{agent.title}: buddy will react. Restart open {agent.title} sessions to pick this up. {agent.note}"
    else:
        message = f"{agent.title}: buddy no longer reacts."
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".buddy-tmp")
    _write_with_mode(tmp, json.dumps(settings, indent=2) + "\n", mode)
    tmp.replace(target)
    print(message.strip())
    return 0


def cmd_claude(args) -> int:
    return set_agent_hooks(AGENTS["claude"], args.state == "on")


def cmd_agents(args) -> int:
    if args.names:
        agents = [AGENTS[name] for name in args.names]
    elif args.state == "on":
        agents = [agent for agent in AGENTS.values() if shutil.which(agent.key)]
        if not agents:
            print("No supported AI agent found (looked for: " + ", ".join(AGENTS) + ").")
            return 0
    else:
        agents = [agent for agent in AGENTS.values() if agent.settings().exists()]
    results = [set_agent_hooks(agent, args.state == "on") for agent in agents]
    return 1 if any(results) else 0


def _write_with_mode(path: Path, text: str, mode: int) -> None:
    """Write text to a file that never exists with looser permissions than `mode`."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def cmd_event(args) -> int:
    """Called by AI agent hooks: must never fail or print anything but `{}` (Gemini wants JSON)."""
    try:
        ipc.send(args.name)
    except Exception:
        pass
    if args.json:
        print("{}")
    return 0


def cmd_guide(args) -> int:
    print((resources.files("buddy") / "guide.txt").read_text(encoding="utf-8"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="buddy", description="A Pokémon that lives on your desktop.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="start buddy (keeps running after you close the terminal)")
    p.add_argument("--foreground", action="store_true", help="stay attached to this terminal")
    p.set_defaults(func=cmd_run)
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
    p = sub.add_parser("agents", help="react to AI agents: Claude Code, Gemini CLI, Codex")
    p.add_argument("state", choices=["on", "off"])
    p.add_argument("names", nargs="*", choices=sorted(AGENTS), metavar="agent", help="default: all installed")
    p.set_defaults(func=cmd_agents)
    p = sub.add_parser("event", help="used by AI agent hooks")
    p.add_argument("name", choices=EVENTS)
    p.add_argument("--json", action="store_true", help="print {} (for Gemini CLI)")
    p.set_defaults(func=cmd_event)
    sub.add_parser("guide", help="show the full guide").set_defaults(func=cmd_guide)
    args = parser.parse_args(argv)
    if sys.stderr is None:  # started without a console (buddyw.exe, login items): keep errors in a log
        log = paths.cache_dir() / "buddy.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        sys.stderr = open(log, "a", encoding="utf-8", buffering=1)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
