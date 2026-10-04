import os
import plistlib
import sys
import threading
import time

import pytest

from buddy import cli, config, ipc, sprites

FAKE_EDITOR = f'"{sys.executable}" -c pass'  # an "editor" that exits at once, on every OS


@pytest.fixture(autouse=True)
def xdg(tmp_path, monkeypatch):
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "APPDATA", "LOCALAPPDATA"):
        folder = tmp_path / var.lower()
        folder.mkdir()
        monkeypatch.setenv(var, str(folder))
    for var in ("HOME", "USERPROFILE"):  # Path.home() on POSIX / Windows
        monkeypatch.setenv(var, str(tmp_path / "home"))
    monkeypatch.setattr(cli, "_platform", lambda: "linux")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")  # restored after each test
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    return tmp_path


@pytest.fixture
def sent(monkeypatch):
    """Pretend a buddy is running and record what the CLI sends it."""
    commands = []
    monkeypatch.setattr(cli.ipc, "send", lambda command, **kw: commands.append(command) or True)
    return commands


@pytest.fixture
def live_buddy():
    """A real IPC server answering in a background thread, like a running buddy."""
    server = ipc.Server()
    server.write_contact()
    received, stop = [], threading.Event()

    def serve():
        while not stop.is_set():
            for command in server.poll():
                received.append(command)
                if command == "quit":
                    server.remove_contact()
                    stop.set()
            time.sleep(0.01)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield received
    stop.set()
    thread.join(2)
    server.close()


def test_autostart_on_writes_desktop_entry_on_linux(monkeypatch):
    monkeypatch.setattr(cli, "buddy_executable", lambda: "/opt/buddy/bin/buddy")
    assert cli.main(["autostart", "on"]) == 0
    text = cli.autostart_path().read_text()
    assert 'Exec="/opt/buddy/bin/buddy" run --foreground' in text
    assert "Type=Application" in text


def test_autostart_off_removes_entry_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(cli, "buddy_executable", lambda: "/opt/buddy/bin/buddy")
    cli.main(["autostart", "on"])
    assert cli.main(["autostart", "off"]) == 0
    assert not cli.autostart_path().exists()
    assert cli.main(["autostart", "off"]) == 0


def test_autostart_on_macos_writes_a_launch_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_platform", lambda: "darwin")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "buddy_executable", lambda: "/Users/me/buddy/.venv/bin/buddy")
    assert cli.main(["autostart", "on"]) == 0
    path = tmp_path / "home" / "Library" / "LaunchAgents" / "com.buddy.pet.plist"
    agent = plistlib.loads(path.read_bytes())
    assert agent["ProgramArguments"] == ["/Users/me/buddy/.venv/bin/buddy", "run", "--foreground"]
    assert agent["RunAtLoad"] is True
    assert cli.main(["autostart", "off"]) == 0
    assert not path.exists()


def test_autostart_on_windows_uses_the_run_key_without_a_console(monkeypatch):
    monkeypatch.setattr(cli, "_platform", lambda: "win32")
    monkeypatch.setattr(cli, "gui_executable", lambda: "C:/Users/me/buddy/.venv/Scripts/buddyw.exe")
    calls = []
    monkeypatch.setattr(cli, "_set_windows_autostart", calls.append)
    assert cli.main(["autostart", "on"]) == 0
    assert cli.main(["autostart", "off"]) == 0
    assert calls == ['"C:/Users/me/buddy/.venv/Scripts/buddyw.exe" run --foreground', None]


def test_choose_saves_canonical_name_and_reloads_running_buddy(monkeypatch, capsys, sent):
    monkeypatch.setattr(sprites, "download", lambda name, **kw: "mr-mime")
    assert cli.main(["choose", "Mr Mime"]) == 0
    assert config.load().pokemon == "mr-mime"
    assert sent == ["reload"]
    assert "Switched to mr-mime" in capsys.readouterr().out


def test_choose_failure_leaves_config_unchanged(monkeypatch, capsys):
    config.save(config.Config(pokemon="eevee"))

    def fail(name, **kw):
        raise sprites.SpriteError("No Pokémon called 'pikachuu'.")

    monkeypatch.setattr(sprites, "download", fail)
    assert cli.main(["choose", "pikachuu"]) == 1
    assert config.load().pokemon == "eevee"
    assert "No Pokémon called" in capsys.readouterr().err


def test_choose_refuses_to_overwrite_broken_config(monkeypatch, capsys):
    path = config.config_path()
    path.parent.mkdir(parents=True)
    path.write_text("scale = 0\n")
    monkeypatch.setattr(sprites, "download", lambda name, **kw: "eevee")
    assert cli.main(["choose", "eevee"]) == 1
    assert path.read_text() == "scale = 0\n"
    assert "scale" in capsys.readouterr().err


def test_stop_asks_the_running_buddy_to_quit(live_buddy, capsys):
    assert cli.main(["stop"]) == 0
    assert live_buddy == ["quit"]
    assert "stopped" in capsys.readouterr().out


def test_stop_when_nothing_is_running(capsys):
    assert cli.main(["stop"]) == 1
    assert "not running" in capsys.readouterr().out


def test_run_refuses_second_instance(live_buddy, capsys):
    assert cli.main(["run"]) == 1
    assert "already running" in capsys.readouterr().out


def test_run_without_sprites_explains_how_to_fix(capsys):
    assert cli.main(["run"]) == 1
    assert "buddy choose pikachu" in capsys.readouterr().err


def test_config_command_validates_after_editing(monkeypatch, capsys):
    monkeypatch.setenv("EDITOR", FAKE_EDITOR)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    assert cli.main(["config"]) == 0  # creates defaults
    assert config.config_path().exists()
    assert "Config OK" in capsys.readouterr().out
    config.config_path().write_text("[stress]\ncpu_exit = 99\n")
    assert cli.main(["config"]) == 1
    assert "cpu_exit" in capsys.readouterr().err


def test_run_reports_missing_gui_library(monkeypatch, capsys):
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    monkeypatch.setitem(sys.modules, "buddy.window", None)  # makes `from buddy import window` raise ImportError
    assert cli.main(["run", "--foreground"]) == 1
    assert "buddy:" in capsys.readouterr().err
    assert not ipc.port_file().exists()


def test_choose_uses_configured_style_and_prints_fallback_notes(monkeypatch, capsys):
    config.save(config.Config(style="ds"))
    seen = {}

    def download(name, style, notes):
        seen["style"] = style
        notes.append("No Mystery Dungeon sprite for zorua; using its Emerald sprite instead.")
        return "zorua"

    monkeypatch.setattr(sprites, "download", download)
    assert cli.main(["choose", "zorua"]) == 0
    assert seen["style"] == "ds"
    assert "using its Emerald sprite" in capsys.readouterr().out


def test_guide_covers_every_command_and_setting(capsys):
    assert cli.main(["guide"]) == 0
    out = capsys.readouterr().out
    for command in ("run", "stop", "choose", "config", "autostart on", "autostart off", "agents on", "agents off", "claude on", "claude off", "guide"):
        assert f"buddy {command}" in out
    for setting in ("pokemon", "style", "scale", "walk_speed", "cpu_enter", "ram_enter", "cpu_exit", "ram_exit", "window_seconds"):
        assert setting in out
    assert "UNINSTALL" in out.upper()


# --- Claude Code integration -------------------------------------------------

import json  # noqa: E402


@pytest.fixture
def claude_dir(tmp_path, monkeypatch):
    folder = tmp_path / "claude"
    folder.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(folder))
    monkeypatch.setattr(cli, "buddy_executable", lambda: "/opt/buddy/bin/buddy")
    return folder


def buddy_commands(settings):
    return [
        hook["command"]
        for groups in settings.get("hooks", {}).values()
        for group in groups
        for hook in group.get("hooks", [])
        if "buddy" in hook.get("command", "")
    ]


def test_claude_on_adds_thinking_and_done_hooks(claude_dir):
    assert cli.main(["claude", "on"]) == 0
    settings = json.loads((claude_dir / "settings.json").read_text())
    prompt = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    stop = settings["hooks"]["Stop"][0]["hooks"][0]
    assert prompt == {"type": "command", "command": "/opt/buddy/bin/buddy event thinking", "timeout": 5}
    assert stop == {"type": "command", "command": "/opt/buddy/bin/buddy event done", "timeout": 5}


def test_claude_on_preserves_existing_settings(claude_dir):
    existing = {
        "model": "opus",
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify-send done"}]}]},
    }
    (claude_dir / "settings.json").write_text(json.dumps(existing))
    assert cli.main(["claude", "on"]) == 0
    settings = json.loads((claude_dir / "settings.json").read_text())
    assert settings["model"] == "opus"
    stop_commands = [h["command"] for g in settings["hooks"]["Stop"] for h in g["hooks"]]
    assert "notify-send done" in stop_commands
    assert json.loads((claude_dir / "settings.json.buddy-backup").read_text()) == existing


def test_claude_on_is_idempotent(claude_dir):
    cli.main(["claude", "on"])
    cli.main(["claude", "on"])
    settings = json.loads((claude_dir / "settings.json").read_text())
    assert len(buddy_commands(settings)) == 2


def test_claude_off_removes_only_buddy_hooks(claude_dir):
    (claude_dir / "settings.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify-send done"}]}]}})
    )
    cli.main(["claude", "on"])
    assert cli.main(["claude", "off"]) == 0
    settings = json.loads((claude_dir / "settings.json").read_text())
    assert buddy_commands(settings) == []
    assert "UserPromptSubmit" not in settings["hooks"]
    assert settings["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "notify-send done"}]}]


def test_claude_on_refuses_invalid_json(claude_dir, capsys):
    (claude_dir / "settings.json").write_text("{not json")
    assert cli.main(["claude", "on"]) == 1
    assert (claude_dir / "settings.json").read_text() == "{not json"
    assert "settings.json" in capsys.readouterr().err


def test_event_reaches_the_running_buddy(live_buddy):
    assert cli.main(["event", "thinking"]) == 0
    assert cli.main(["event", "done"]) == 0
    deadline = time.monotonic() + 2
    while len(live_buddy) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert live_buddy == ["thinking", "done"]


def test_event_does_not_import_heavy_libraries():
    import subprocess

    code = "import sys; from buddy import cli; cli.main(['event', 'done']); print(sorted(m for m in ('PIL', 'PySide6') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30).stdout
    assert out.strip() == "[]"


def test_event_without_running_buddy_is_silent(capsys):
    assert cli.main(["event", "done"]) == 0
    assert capsys.readouterr() == ("", "")



# --- review fixes ---------------------------------------------------------------


def test_run_with_invalid_config_keeps_the_chosen_pokemon(monkeypatch, capsys):
    path = config.config_path()
    path.parent.mkdir(parents=True)
    path.write_text('pokemon = "eevee"\nstyle = "ds"\nscale = 10\n')
    asked = []
    monkeypatch.setattr(sprites, "load_cached", lambda name, style: asked.append((name, style)) or object())
    monkeypatch.setitem(sys.modules, "buddy.window", None)
    cli.main(["run", "--foreground"])
    assert asked == [("eevee", "ds")]
    assert "scale" in capsys.readouterr().err


def test_config_command_warns_when_sprite_is_not_downloaded(monkeypatch, capsys, sent):
    monkeypatch.setenv("EDITOR", FAKE_EDITOR)
    monkeypatch.delenv("VISUAL", raising=False)
    config.save(config.Config(pokemon="eevee"))
    assert cli.main(["config"]) == 1
    out, err = capsys.readouterr()
    assert "buddy choose eevee" in err
    assert "reloaded" not in out
    assert sent == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")
def test_claude_on_keeps_file_permissions(claude_dir):
    settings = claude_dir / "settings.json"
    settings.write_text('{"env": {"API_KEY": "secret"}}')
    settings.chmod(0o600)
    assert cli.main(["claude", "on"]) == 0
    assert settings.stat().st_mode & 0o777 == 0o600
    assert (claude_dir / "settings.json.buddy-backup").stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlinks need extra rights on Windows")
def test_claude_on_writes_through_a_symlinked_settings_file(claude_dir, tmp_path):
    real = tmp_path / "dotfiles" / "settings.json"
    real.parent.mkdir()
    real.write_text('{"model": "opus"}')
    (claude_dir / "settings.json").symlink_to(real)
    assert cli.main(["claude", "on"]) == 0
    assert (claude_dir / "settings.json").is_symlink()
    assert "event thinking" in real.read_text()


# --- other AI agents (Gemini CLI, Codex) -------------------------------------------


@pytest.fixture
def agent_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(cli, "buddy_executable", lambda: "/opt/buddy/bin/buddy")
    return home


def installed(monkeypatch, *names):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}" if name in names else None)


def test_gemini_hooks_use_before_and_after_agent_with_json_output(agent_home):
    assert cli.main(["agents", "on", "gemini"]) == 0
    settings = json.loads((agent_home / ".gemini" / "settings.json").read_text())
    before = settings["hooks"]["BeforeAgent"][0]["hooks"][0]
    after = settings["hooks"]["AfterAgent"][0]["hooks"][0]
    assert before["command"] == "/opt/buddy/bin/buddy event thinking --json"
    assert after["command"] == "/opt/buddy/bin/buddy event done --json"
    assert before["type"] == "command" and before["timeout"] == 5000  # Gemini timeouts are milliseconds
    assert before["name"] == "buddy-thinking"


def test_codex_hooks_go_in_hooks_json(agent_home):
    assert cli.main(["agents", "on", "codex"]) == 0
    settings = json.loads((agent_home / ".codex" / "hooks.json").read_text())
    assert settings["hooks"]["UserPromptSubmit"][0]["hooks"][0] == {
        "type": "command",
        "command": "/opt/buddy/bin/buddy event thinking",
        "timeout": 5,
    }
    assert settings["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("event done")


def test_agents_on_sets_up_every_installed_agent(agent_home, monkeypatch, capsys):
    installed(monkeypatch, "claude", "codex")
    assert cli.main(["agents", "on"]) == 0
    assert (agent_home / ".claude" / "settings.json").exists()
    assert (agent_home / ".codex" / "hooks.json").exists()
    assert not (agent_home / ".gemini").exists()
    out = capsys.readouterr().out
    assert "Claude Code" in out and "Codex" in out


def test_agents_on_with_nothing_installed_says_so(agent_home, monkeypatch, capsys):
    installed(monkeypatch)
    assert cli.main(["agents", "on"]) == 0
    assert "No supported AI agent" in capsys.readouterr().out


def test_agents_off_removes_buddy_from_every_agent(agent_home, monkeypatch):
    installed(monkeypatch, "claude", "gemini", "codex")
    cli.main(["agents", "on"])
    assert cli.main(["agents", "off"]) == 0
    for path in (".claude/settings.json", ".gemini/settings.json", ".codex/hooks.json"):
        assert buddy_commands(json.loads((agent_home / path).read_text())) == []


def test_codex_home_is_respected(agent_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    cli.main(["agents", "on", "codex"])
    assert (tmp_path / "codex-home" / "hooks.json").exists()


def test_event_json_prints_an_empty_object_for_gemini(capsys):
    assert cli.main(["event", "thinking", "--json"]) == 0
    assert capsys.readouterr() == ("{}\n", "")



# --- cross-platform review fixes --------------------------------------------------


def test_hook_command_quotes_only_paths_that_need_it(claude_dir, monkeypatch):
    import json

    monkeypatch.setattr(cli, "buddy_executable", lambda: "C:\\Users\\Jo Smith\\buddy\\.venv\\Scripts\\buddy.exe")
    cli.main(["claude", "on"])
    command = json.loads((claude_dir / "settings.json").read_text())["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert command == '"C:/Users/Jo Smith/buddy/.venv/Scripts/buddy.exe" event done'


def test_run_on_wayland_always_uses_xwayland(monkeypatch):
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    monkeypatch.setitem(sys.modules, "buddy.window", None)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")  # e.g. exported globally on Sway/KDE
    monkeypatch.delenv("BUDDY_QT_PLATFORM", raising=False)
    cli.main(["run", "--foreground"])
    assert os.environ["QT_QPA_PLATFORM"] == "xcb"


def test_buddy_qt_platform_overrides_the_choice(monkeypatch):
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    monkeypatch.setitem(sys.modules, "buddy.window", None)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("BUDDY_QT_PLATFORM", "wayland")
    cli.main(["run", "--foreground"])
    assert os.environ["QT_QPA_PLATFORM"] == "wayland"


def test_errors_go_to_a_log_file_when_there_is_no_console(monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)  # buddyw.exe / pythonw on Windows
    assert cli.main(["run"]) == 1  # no sprites cached
    from buddy import paths

    assert "buddy choose" in (paths.cache_dir() / "buddy.log").read_text()


def test_config_on_macos_waits_for_enter_not_for_textedit_to_quit(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_platform", lambda: "darwin")
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    opened = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda args: opened.append(args))
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert cli.main(["config"]) == 0
    assert opened and opened[0][:2] == ["open", "-t"] and "-W" not in opened[0]
    assert "Config OK" in capsys.readouterr().out


# --- buddy run keeps going after the terminal closes ------------------------------


class FakeChild:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code


@pytest.fixture
def spawned(monkeypatch):
    """Record the background start instead of launching a real buddy."""
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeChild()

    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    return calls


def test_run_starts_buddy_in_its_own_session_and_returns(monkeypatch, spawned, capsys):
    answers = iter([False, False, True])  # not running yet; still starting; up
    monkeypatch.setattr(cli.ipc, "is_running", lambda: next(answers))
    assert cli.main(["run"]) == 0
    [(command, kwargs)] = spawned
    assert command == [sys.executable, "-P", "-m", "buddy.cli", "run", "--foreground"]
    assert kwargs["cwd"] == cli.Path.home()  # never imports modules from the folder you ran it in
    assert kwargs["start_new_session"] is True  # no hang-up when the terminal closes
    assert kwargs["stdin"] is cli.subprocess.DEVNULL
    assert kwargs["stdout"] is cli.subprocess.DEVNULL
    assert "buddy stop" in capsys.readouterr().out


def test_run_on_windows_starts_buddy_detached_without_a_console(monkeypatch, spawned, tmp_path):
    monkeypatch.setattr(cli, "_platform", lambda: "win32")
    python = tmp_path / "Scripts" / "python.exe"
    python.parent.mkdir()
    python.touch()
    (python.parent / "pythonw.exe").touch()
    monkeypatch.setattr(cli.sys, "executable", str(python))
    answers = iter([False, True])
    monkeypatch.setattr(cli.ipc, "is_running", lambda: next(answers))
    assert cli.main(["run"]) == 0
    [(command, kwargs)] = spawned
    assert command == [str(python.parent / "pythonw.exe"), "-P", "-m", "buddy.cli", "run", "--foreground"]
    assert kwargs["creationflags"] & cli.DETACHED_PROCESS
    assert kwargs["creationflags"] & cli.CREATE_NEW_PROCESS_GROUP
    assert "start_new_session" not in kwargs


def test_run_shows_why_buddy_failed_to_start(monkeypatch, capsys):
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    monkeypatch.setattr(cli.ipc, "is_running", lambda: False)

    def popen(command, stderr, **kwargs):
        stderr.write("buddy: Qt can't open the display\n")
        return FakeChild(exit_code=1)

    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    assert cli.main(["run"]) == 1
    assert "Qt can't open the display" in capsys.readouterr().err


def test_run_does_not_start_anything_when_checks_fail(spawned, live_buddy, capsys):
    assert cli.main(["run"]) == 1
    assert "already running" in capsys.readouterr().out
    assert spawned == []
