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
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable

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


EVENT_SIGNALS = {"thinking": signal.SIGUSR1, "done": signal.SIGUSR2}


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
    args = [os.fsdecode(arg) for arg in args if arg]
    # The console script runs as: <python> <path>/buddy run
    return len(args) >= 3 and Path(args[1]).name == "buddy" and args[2] == "run"


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
        cfg = config.salvage()
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
    command = f'"{buddy_executable()}" event {event}' + (" --json" if agent.json_output else "")
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
        _signal_running(EVENT_SIGNALS[args.name])
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
    p = sub.add_parser("agents", help="react to AI agents: Claude Code, Gemini CLI, Codex")
    p.add_argument("state", choices=["on", "off"])
    p.add_argument("names", nargs="*", choices=sorted(AGENTS), metavar="agent", help="default: all installed")
    p.set_defaults(func=cmd_agents)
    p = sub.add_parser("event", help="used by AI agent hooks")
    p.add_argument("name", choices=sorted(EVENT_SIGNALS))
    p.add_argument("--json", action="store_true", help="print {} (for Gemini CLI)")
    p.set_defaults(func=cmd_event)
    sub.add_parser("guide", help="show the full guide").set_defaults(func=cmd_guide)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
