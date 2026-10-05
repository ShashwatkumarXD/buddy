"""Buddy on screen (Qt): works on Linux (through XWayland on Wayland), macOS and Windows.

Two frameless, always-on-top tool windows that never take focus:
- the *pet* window is exactly the sprite's size and receives the mouse;
- the *decor* window draws the reaction bubble and stress panel and lets clicks through.
(Qt can't make only part of one window click-through, hence two windows moving together.)
"""
import ctypes
import ctypes.util
import os
import signal
import sys
import time
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from buddy import config as config_mod
from buddy import ipc, sprites
from buddy.brain import Bounds, Brain, Bubble
from buddy.config import Config
from buddy.matrix import PANEL_H, PANEL_W, MatrixRain
from buddy.monitor import StressMonitor
from buddy.safety import keep_alive
from buddy.timing import bubble_durations, frame_at, spin_durations

FPS = 30
MARGIN = 4
WINDOW_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
    | Qt.WindowType.WindowDoesNotAcceptFocus
    | Qt.WindowType.NoDropShadowWindowHint
)
# Qt's X11 platform plugin needs these system libraries: file name -> Debian/Ubuntu package.
X11_LIBRARIES = {
    "libxcb-cursor.so.0": "libxcb-cursor0",
    "libxkbcommon-x11.so.0": "libxkbcommon-x11-0",
    "libxcb-icccm.so.4": "libxcb-icccm4",
    "libxcb-image.so.0": "libxcb-image0",
    "libxcb-keysyms.so.1": "libxcb-keysyms1",
    "libxcb-render-util.so.0": "libxcb-render-util0",
    "libxcb-xkb.so.1": "libxcb-xkb1",
}


def _loadable(soname: str) -> bool:
    """Can this shared library actually be loaded (same search rules Qt uses)?"""
    try:
        ctypes.CDLL(soname)
        return True
    except OSError:
        return False


def missing_x11_libraries() -> list[str]:
    """Debian/Ubuntu packages Qt needs on X11/XWayland that can't be loaded."""
    return [package for soname, package in X11_LIBRARIES.items() if not _loadable(soname)]


def bubble_scale(sprite_scale: float) -> float:
    """Enlargement for the 40x32 pixel-art bubbles: half the Pokémon's scale, never below native size."""
    return max(1.0, sprite_scale / 2)


def device_pixels(pixels: int, scale: float, dpr: float) -> int:
    """Size in real screen pixels. Images are scaled once, straight to this, and tagged with the screen's
    device-pixel ratio, so Qt never resamples the pixel art again (which shimmers at 125%/150% scaling)."""
    return max(1, round(pixels * scale * dpr))


def _dpr() -> float:
    screen = QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


def _pixmap(path: Path, scale: float, mirror: bool = False) -> QPixmap:
    image = QImage(str(path))
    if image.isNull():
        raise sprites.SpriteError(f"Unreadable image {path}")
    dpr = _dpr()
    image = image.scaled(
        device_pixels(image.width(), scale, dpr),
        device_pixels(image.height(), scale, dpr),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,  # nearest neighbour keeps pixel art crisp
    )
    if mirror:
        image = image.transformed(QTransform().scale(-1, 1))
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def logical_size(pixmap: QPixmap) -> tuple[int, int]:
    size = pixmap.deviceIndependentSize()
    return round(size.width()), round(size.height())


class Sprite:
    """Scaled walk/idle animations, plus mirrored copies for the other direction."""

    def __init__(self, cached: sprites.CachedSprite, scale: float):
        self.faces = cached.faces
        self.anims = {}
        for key, frames in cached.anims.items():
            native, mirrored, durations = [], [], []
            for path, ms in frames:
                native.append(_pixmap(path, scale))
                mirrored.append(_pixmap(path, scale, mirror=True))
                durations.append(max(20, ms))
            self.anims[key] = (native, mirrored, durations)
        self.width, self.height = logical_size(self.anims["walk"][0][0])
        self.current = "idle"
        self.index = 0
        self._elapsed = 0.0

    def play(self, key: str) -> None:
        if key != self.current:
            self.current = key
            self.index = 0
            self._elapsed = 0.0

    def advance(self, dt_ms: float) -> None:
        durations = self.anims[self.current][2]
        self._elapsed += dt_ms
        while self._elapsed >= durations[self.index]:
            self._elapsed -= durations[self.index]
            self.index = (self.index + 1) % len(durations)

    def frame(self, facing: int) -> QPixmap:
        native, mirrored, _ = self.anims[self.current]
        return (native if facing == self.faces else mirrored)[self.index]


def _load_bubbles(factor: float) -> dict[Bubble, list[QPixmap]]:
    """Each bubble's frames: `<name>.png`, then any `<name>_1.png`, `<name>_2.png`… (an animation)."""
    folder = resources.files("buddy") / "assets" / "bubbles"
    bubbles = {}
    for bubble in Bubble:
        frames = []
        for name in [f"{bubble.value}.png"] + [f"{bubble.value}_{i}.png" for i in range(1, 10)]:
            ref = folder / name
            if not ref.is_file():
                break
            with resources.as_file(ref) as path:
                frames.append(_pixmap(path, factor))
        bubbles[bubble] = frames
    return bubbles


class _Overlay(QWidget):
    def __init__(self, click_through: bool):
        flags = WINDOW_FLAGS | (Qt.WindowType.WindowTransparentForInput if click_through else Qt.WindowType.Widget)
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setWindowTitle("Buddy")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.paint(painter)
        painter.end()

    def paint(self, painter: QPainter) -> None:
        raise NotImplementedError


class PetWindow(_Overlay):
    def __init__(self, buddy: "Buddy"):
        super().__init__(click_through=False)
        self.buddy = buddy

    def paint(self, painter: QPainter) -> None:
        painter.drawPixmap(0, 0, self.buddy.sprite.frame(self.buddy.brain.facing))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.globalPosition()
            self.buddy.brain.press(point.x(), point.y())

    def mouseMoveEvent(self, event) -> None:
        point = event.globalPosition()
        self.buddy.brain.motion(point.x(), point.y())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.globalPosition()
            self.buddy.brain.release(point.x(), point.y())


class DecorWindow(_Overlay):
    def __init__(self, buddy: "Buddy"):
        super().__init__(click_through=True)
        self.buddy = buddy

    def paint(self, painter: QPainter) -> None:
        self.buddy.paint_decor(painter)


class Buddy:
    """The running buddy: brain, monitor, sprite, the two windows and the IPC listener."""

    def __init__(self, app: QApplication, cfg: Config, cached: sprites.CachedSprite):
        self.app = app
        self.cfg = cfg
        self.sprite = Sprite(cached, cfg.scale)
        self.bubbles = _load_bubbles(bubble_scale(cfg.scale))
        self.matrix = MatrixRain(PANEL_W, PANEL_H)
        self.monitor = StressMonitor(cfg.stress)
        self.brain = Brain(self._bounds(), self.sprite.width, self.sprite.height, cfg.walk_speed)
        self.decor = DecorWindow(self)
        self.pet = PetWindow(self)
        self._bubble_shown = None
        self._bubble_ms = 0.0
        self._last = time.monotonic()
        self._layout()
        self.server = ipc.Server()
        self.server.write_contact()

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            screen.availableGeometryChanged.connect(self._on_screen_changed)
        app.primaryScreenChanged.connect(self._on_screen_changed)
        self._timers = []
        for interval, callback in ((1000 // FPS, self.on_tick), (1000, self.on_monitor), (50, self.on_ipc)):
            timer = QTimer()
            timer.timeout.connect(callback)
            timer.start(interval)
            self._timers.append(timer)

    # --- geometry -------------------------------------------------------------

    def _bounds(self) -> Bounds:
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)
        return Bounds(left=area.x(), top=area.y(), right=area.x() + area.width(), floor=area.y() + area.height())

    def _layout(self) -> None:
        """Decor window = [panel | sprite | panel] wide, bubble row above the sprite; bottoms aligned."""
        s = self.sprite
        bubble_h = max(logical_size(pb)[1] for frames in self.bubbles.values() for pb in frames)
        self.sprite_off_x = PANEL_W + MARGIN
        self.decor_w = s.width + 2 * (PANEL_W + MARGIN)
        self.decor_h = max(bubble_h + MARGIN + s.height, PANEL_H)
        self.sprite_off_y = self.decor_h - s.height
        self.panel_y = self.decor_h - PANEL_H
        self.pet.setFixedSize(s.width, s.height)
        self.decor.setFixedSize(self.decor_w, self.decor_h)
        self._place(force=True)

    def _place(self, force: bool = False) -> None:
        x, y = int(self.brain.x), int(self.brain.y)
        if force or (self.pet.x(), self.pet.y()) != (x, y):
            self.pet.move(x, y)
            self.decor.move(x - self.sprite_off_x, y - self.sprite_off_y)

    def show(self) -> None:
        self.decor.show()
        self.pet.show()  # shown last so it sits above the decor window

    @keep_alive
    def _on_screen_changed(self, *_):
        self.brain.set_bounds(self._bounds())

    # --- loop -----------------------------------------------------------------

    @keep_alive
    def on_tick(self) -> bool:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        self.brain.tick(dt)
        bubble = self.brain.bubble
        self._bubble_ms = self._bubble_ms + dt * 1000 if bubble is self._bubble_shown else 0.0
        self._bubble_shown = bubble
        self.sprite.play("walk" if self.brain.moving else "idle")
        self.sprite.advance(min(dt, 0.1) * 1000)
        if self.brain.stressed:
            self.matrix.tick(dt)
        self._place()
        self.pet.update()
        self.decor.update()
        return True

    @keep_alive
    def on_monitor(self) -> bool:
        self.brain.set_stressed(self.monitor.tick())
        return True

    @keep_alive
    def on_ipc(self) -> bool:
        for command in self.server.poll():
            if command == "thinking":
                self.brain.claude_thinking()
            elif command == "done":
                self.brain.claude_done()
            elif command == "reload":
                self.reload()
            elif command == "quit":
                self.app.quit()
        return True

    def paint_decor(self, painter: QPainter) -> None:
        b = self.brain
        bubble = b.bubble
        if bubble is not None:
            frames = self.bubbles[bubble]
            timing = spin_durations if bubble is Bubble.SCRIBBLE else bubble_durations
            pb = frames[frame_at(self._bubble_ms, timing(len(frames)))]
            bw, bh = logical_size(pb)
            bx = self.sprite_off_x + (self.sprite.width - bw) // 2
            by = self.sprite_off_y - bh - MARGIN
            painter.drawPixmap(bx, by, pb)
        if b.stressed:
            room_right = b.bounds.right - (b.x + self.sprite.width)
            px = self.sprite_off_x + self.sprite.width + MARGIN if room_right >= PANEL_W + MARGIN else 0
            latest = self.monitor.latest
            self.matrix.draw(painter, px, self.panel_y, latest.cpu, latest.ram)

    # --- commands ---------------------------------------------------------------

    @keep_alive
    def reload(self) -> bool:
        try:
            cfg = config_mod.load()
            cached = sprites.load_cached(cfg.pokemon, style=cfg.style)
            sprite = Sprite(cached, cfg.scale)
        except (config_mod.ConfigError, sprites.SpriteError) as e:
            print(f"buddy: reload skipped: {e}", file=sys.stderr)
            return True
        self.cfg = cfg
        self.sprite = sprite
        self.bubbles = _load_bubbles(bubble_scale(cfg.scale))
        self.monitor = StressMonitor(cfg.stress)
        self.brain.walk_speed = cfg.walk_speed
        self.brain.resize(self.sprite.width, self.sprite.height)
        self._layout()
        return True

    def shutdown(self) -> None:
        for timer in self._timers:
            timer.stop()
        self.server.remove_contact()
        self.server.close()
        self.pet.close()
        self.decor.close()


# --- X11 (Linux, incl. XWayland): show on every workspace ----------------------------------------


def _x11_all_workspaces(widgets: list[QWidget]) -> None:
    """Set _NET_WM_DESKTOP = 0xFFFFFFFF ("all desktops") before the windows are mapped."""
    try:
        x11 = ctypes.CDLL("libX11.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XInternAtom.restype = ctypes.c_ulong
        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XChangeProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
        ]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        display = x11.XOpenDisplay(None)
        if not display:
            return
        desktop = x11.XInternAtom(display, b"_NET_WM_DESKTOP", 0)
        all_desktops = ctypes.c_ulong(0xFFFFFFFF)
        xa_cardinal, prop_mode_replace = 6, 0
        for widget in widgets:
            x11.XChangeProperty(display, int(widget.winId()), desktop, xa_cardinal, 32,
                                prop_mode_replace, ctypes.byref(all_desktops), 1)
        x11.XFlush(display)
        x11.XCloseDisplay(display)
    except Exception as e:  # cosmetic only; never stop buddy from running
        print(f"buddy: couldn't show on every workspace ({e})", file=sys.stderr)


# --- macOS: no Dock icon, visible on every Space (best effort, via the Objective-C runtime) ------


def _objc():
    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    lib.objc_getClass.restype = ctypes.c_void_p
    lib.objc_getClass.argtypes = [ctypes.c_char_p]
    lib.sel_registerName.restype = ctypes.c_void_p
    lib.sel_registerName.argtypes = [ctypes.c_char_p]
    return lib


def _objc_send(lib, receiver, selector: str, *args, argtypes=()):
    send = lib.objc_msgSend
    send.restype = ctypes.c_void_p
    send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, *argtypes]
    return send(receiver, lib.sel_registerName(selector.encode()), *args)


def _mac_tweaks(widgets: list[QWidget]) -> None:
    try:
        lib = _objc()
        ns_app = _objc_send(lib, lib.objc_getClass(b"NSApplication"), "sharedApplication")
        _objc_send(lib, ns_app, "setActivationPolicy:", 1, argtypes=[ctypes.c_long])  # accessory: no Dock icon
        all_spaces = (1 << 0) | (1 << 4) | (1 << 8)  # CanJoinAllSpaces | Stationary | FullScreenAuxiliary
        for widget in widgets:
            ns_window = _objc_send(lib, int(widget.winId()), "window")
            _objc_send(lib, ns_window, "setCollectionBehavior:", all_spaces, argtypes=[ctypes.c_ulong])
    except Exception as e:  # cosmetic only; never stop buddy from running
        print(f"buddy: macOS window tweaks skipped ({e})", file=sys.stderr)


def run(cfg: Config, cached: sprites.CachedSprite) -> int:
    if sys.platform.startswith("linux") and os.environ.get("QT_QPA_PLATFORM", "xcb") == "xcb":
        missing = missing_x11_libraries()
        if missing:
            print(
                "buddy: Qt needs some system libraries. Install them with:\n"
                f"  sudo apt install {' '.join(missing)}",
                file=sys.stderr,
            )
            return 1
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    try:
        buddy = Buddy(app, cfg, cached)
    except sprites.SpriteError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    if app.platformName() == "xcb":
        _x11_all_workspaces([buddy.pet, buddy.decor])
    buddy.show()
    if sys.platform == "darwin" and app.platformName() == "cocoa":  # winId() is an NSView only on cocoa
        _mac_tweaks([buddy.pet, buddy.decor])
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    try:
        return app.exec()
    finally:
        buddy.shutdown()
