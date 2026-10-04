from pathlib import Path

from buddy import paths


def test_linux_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    assert paths.config_dir("linux") == tmp_path / "cfg" / "buddy"
    assert paths.cache_dir("linux") == tmp_path / "cache" / "buddy"
    assert paths.runtime_dir("linux") == tmp_path / "run"


def test_linux_defaults_without_xdg(monkeypatch, tmp_path):
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.config_dir("linux") == tmp_path / ".config" / "buddy"
    assert paths.cache_dir("linux") == tmp_path / ".cache" / "buddy"
    assert paths.runtime_dir("linux") == tmp_path / ".cache" / "buddy"


def test_windows_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.config_dir("win32") == tmp_path / "Roaming" / "buddy"
    assert paths.cache_dir("win32") == tmp_path / "Local" / "buddy" / "Cache"
    assert paths.runtime_dir("win32") == tmp_path / "Local" / "buddy"


def test_macos_uses_library(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.config_dir("darwin") == tmp_path / "Library" / "Application Support" / "buddy"
    assert paths.cache_dir("darwin") == tmp_path / "Library" / "Caches" / "buddy"
    assert paths.runtime_dir("darwin") == tmp_path / "Library" / "Caches" / "buddy"


def test_defaults_to_the_current_platform():
    assert isinstance(paths.config_dir(), Path)
