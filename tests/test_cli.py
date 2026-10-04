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
