"""How long since the user last touched the mouse or keyboard (anywhere, not just on buddy).

Each platform has its own way to ask; the first one that answers is kept. When none does, the answer
is None and buddy just never falls asleep because of an idle computer.
"""
import ctypes
import ctypes.util
import sys
from typing import Callable

DBUS_TIMEOUT_MS = 200  # never let a stuck session bus freeze the animation

Backend = Callable[[], float]  # seconds idle; raises when it can't tell


class IdleClock:
    def __init__(self, backends: list[Backend] | None = None):
        self._candidates = list(default_backends() if backends is None else backends)
        self._backend: Backend | None = None

    def seconds(self) -> float | None:
        if self._backend is None:
            while self._candidates:
                candidate = self._candidates.pop(0)
                idle = _ask(candidate)
                if idle is not None:
                    self._backend = candidate
                    return idle
            return None
        return _ask(self._backend)


def _ask(backend: Backend) -> float | None:
    try:
        idle = float(backend())
    except Exception:
        return None
    return idle if idle >= 0 else None


def default_backends(platform: str = sys.platform) -> list[Backend]:
    if platform == "win32":
        return [windows_idle]
    if platform == "darwin":
        return [mac_idle]
    return [gnome_idle, freedesktop_idle, x11_idle]


# --- Linux ---------------------------------------------------------------


def _dbus_ms(service: str, path: str, interface: str, method: str) -> float:
    from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise OSError("no session bus")
    proxy = QDBusInterface(service, path, interface, bus)
    proxy.setTimeout(DBUS_TIMEOUT_MS)
    reply = proxy.call(method)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
        raise OSError(reply.errorMessage() or "no reply")
    return float(reply.arguments()[0])


def gnome_idle() -> float:
    """GNOME (Wayland and X11): the compositor sees every key and pointer event."""
    ms = _dbus_ms(
        "org.gnome.Mutter.IdleMonitor",
        "/org/gnome/Mutter/IdleMonitor/Core",
        "org.gnome.Mutter.IdleMonitor",
        "GetIdletime",
    )
    return ms / 1000


def freedesktop_idle() -> float:
    """KDE and others that implement the screensaver's idle-time call."""
    ms = _dbus_ms(
        "org.freedesktop.ScreenSaver",
        "/org/freedesktop/ScreenSaver",
        "org.freedesktop.ScreenSaver",
        "GetSessionIdleTime",
    )
    return ms / 1000


class _XScreenSaverInfo(ctypes.Structure):
    _fields_ = [
        ("window", ctypes.c_ulong),
        ("state", ctypes.c_int),
        ("kind", ctypes.c_int),
        ("til_or_since", ctypes.c_ulong),
        ("idle", ctypes.c_ulong),
        ("event_mask", ctypes.c_ulong),
    ]


def x11_idle() -> float:
    """Plain X11 sessions (on Wayland this would only see input sent to X apps, so it goes last)."""
    x11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
    xss = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xss") or "libXss.so.1")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(_XScreenSaverInfo)
    xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XScreenSaverInfo)]
    x11.XFree.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise OSError("no X display")
    info = xss.XScreenSaverAllocInfo()
    try:
        if not xss.XScreenSaverQueryInfo(display, x11.XDefaultRootWindow(display), info):
            raise OSError("no screensaver extension")
        return info.contents.idle / 1000
    finally:
        x11.XFree(info)
        x11.XCloseDisplay(display)


# --- Windows and macOS ---------------------------------------------------


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def windows_idle() -> float:
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    info = _LastInputInfo(cbSize=ctypes.sizeof(_LastInputInfo))
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise OSError("GetLastInputInfo failed")
    kernel32.GetTickCount.restype = ctypes.c_uint
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000  # both wrap every 49.7 days


def mac_idle() -> float:
    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
    cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_int32, ctypes.c_uint32]
    combined_session, any_input = 0, 0xFFFFFFFF
    return cg.CGEventSourceSecondsSinceLastEventType(combined_session, any_input)
