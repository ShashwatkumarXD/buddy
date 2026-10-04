"""Where buddy keeps its files on each operating system (stdlib only)."""
import os
import sys
from pathlib import Path

APP = "buddy"


def _is_windows(platform: str) -> bool:
    return platform.startswith("win")


def config_dir(platform: str | None = None) -> Path:
    platform = platform or sys.platform
    if _is_windows(platform):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP


def cache_dir(platform: str | None = None) -> Path:
    platform = platform or sys.platform
    if _is_windows(platform):
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP / "Cache"
    if platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP


def runtime_dir(platform: str | None = None) -> Path:
    """Folder for the running buddy's contact file (buddy.port)."""
    platform = platform or sys.platform
    if _is_windows(platform):
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP
    if platform == "darwin":
        return cache_dir(platform)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return Path(runtime) if runtime else cache_dir(platform)
