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
    monkeypatch.setattr(sprites, "download", lambda name, **kw: "mr-mime")
    monkeypatch.setattr(cli, "read_pid", lambda: 4242)
    sent = []
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    assert cli.main(["choose", "Mr Mime"]) == 0
    assert config.load().pokemon == "mr-mime"
    assert sent == [(4242, signal.SIGHUP)]
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


def test_run_reports_missing_gtk_bindings(monkeypatch, capsys):
    monkeypatch.setattr(sprites, "load_cached", lambda name, **kw: object())
    monkeypatch.setitem(sys.modules, "buddy.window", None)  # makes `from buddy import window` raise ImportError
    assert cli.main(["run"]) == 1
    assert "buddy:" in capsys.readouterr().err
    assert not cli.pid_path().exists()


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
    for command in ("run", "stop", "choose", "config", "autostart on", "autostart off", "claude on", "claude off", "guide"):
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
    assert prompt == {"type": "command", "command": '"/opt/buddy/bin/buddy" event thinking', "timeout": 5}
    assert stop == {"type": "command", "command": '"/opt/buddy/bin/buddy" event done', "timeout": 5}


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


def test_event_signals_running_buddy(monkeypatch):
    monkeypatch.setattr(cli, "read_pid", lambda: 4242)
    sent = []
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    assert cli.main(["event", "thinking"]) == 0
    assert cli.main(["event", "done"]) == 0
    assert sent == [(4242, signal.SIGUSR1), (4242, signal.SIGUSR2)]


def test_event_without_running_buddy_is_silent(capsys):
    assert cli.main(["event", "done"]) == 0
    assert capsys.readouterr() == ("", "")
