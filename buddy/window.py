"""Transparent always-on-top GTK3 window that draws the buddy. Runs under XWayland."""
import signal
import sys
import time
from importlib import resources
from pathlib import Path

import cairo
import gi

try:
    gi.require_foreign("cairo")
except ImportError:
    raise ImportError("GTK's cairo bindings are missing. Install them with: sudo apt install python3-gi-cairo") from None
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from buddy import config as config_mod  # noqa: E402
from buddy import sprites  # noqa: E402
from buddy.brain import Bounds, Brain, Bubble  # noqa: E402
from buddy.config import Config  # noqa: E402
from buddy.matrix import PANEL_H, PANEL_W, MatrixRain  # noqa: E402
from buddy.monitor import StressMonitor  # noqa: E402

WINDOW_MODE = "normal"  # "normal" | "dock" | "popup" — chosen by the Task 1 spike
FPS = 30
BUBBLE_SIZE = 48
MARGIN = 4


class Sprite:
    """Scaled animation frames; source art faces left, mirrored copies face right."""

    def __init__(self, frames: list[tuple[Path, int]], scale: float):
        self.left, self.right, self.durations = [], [], []
        for path, ms in frames:
            pb = GdkPixbuf.Pixbuf.new_from_file(str(path))
            pb = pb.scale_simple(round(pb.get_width() * scale), round(pb.get_height() * scale), GdkPixbuf.InterpType.NEAREST)
            self.left.append(pb)
            self.right.append(pb.flip(True))
            self.durations.append(ms)
        self.width = self.left[0].get_width()
        self.height = self.left[0].get_height()
        self.index = 0
        self._elapsed = 0.0

    def advance(self, dt_ms: float) -> None:
        self._elapsed += dt_ms
        while self._elapsed >= self.durations[self.index]:
            self._elapsed -= self.durations[self.index]
            self.index = (self.index + 1) % len(self.durations)

    def frame(self, facing: int) -> GdkPixbuf.Pixbuf:
        return (self.right if facing > 0 else self.left)[self.index]


def _load_bubbles() -> dict[Bubble, GdkPixbuf.Pixbuf]:
    bubbles = {}
    for bubble in Bubble:
        ref = resources.files("buddy") / "assets" / "bubbles" / f"{bubble.value}.png"
        with resources.as_file(ref) as path:
            bubbles[bubble] = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), BUBBLE_SIZE, BUBBLE_SIZE, True)
    return bubbles


class BuddyWindow(Gtk.Window):
    def __init__(self, cfg: Config, frames: list[tuple[Path, int]]):
        super().__init__(type=Gtk.WindowType.POPUP if WINDOW_MODE == "popup" else Gtk.WindowType.TOPLEVEL)
        visual = self.get_screen().get_rgba_visual()
        if visual is None:
            raise RuntimeError("no transparent (RGBA) visual — is the compositor running?")
        self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        if WINDOW_MODE == "dock":
            self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        elif WINDOW_MODE == "normal":
            self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        if WINDOW_MODE != "popup":
            self.set_keep_above(True)
            self.stick()
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("destroy", Gtk.main_quit)

        self.bubbles = _load_bubbles()
        self.matrix = MatrixRain(PANEL_W, PANEL_H)
        self.cfg = cfg
        self.sprite = Sprite(frames, cfg.scale)
        self.monitor = StressMonitor(cfg.stress)
        self.brain = Brain(self._bounds(), self.sprite.width, self.sprite.height, cfg.walk_speed)
        self._moved_to = None
        self._layout()

        screen = self.get_screen()
        screen.connect("size-changed", self._on_screen_changed)
        screen.connect("monitors-changed", self._on_screen_changed)
        self._last = time.monotonic()
        GLib.timeout_add(1000 // FPS, self._on_tick)
        GLib.timeout_add_seconds(1, self._on_monitor)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGHUP, self.reload)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._quit)

    # --- geometry --------------------------------------------------------

    def _bounds(self) -> Bounds:
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        wa = monitor.get_workarea()
        return Bounds(left=wa.x, top=wa.y, right=wa.x + wa.width, floor=wa.y + wa.height)

    def _layout(self) -> None:
        """Window = [panel | sprite | panel] wide; bubble row above the sprite; bottoms aligned."""
        s = self.sprite
        self.sprite_off_x = PANEL_W + MARGIN
        self.win_w = s.width + 2 * (PANEL_W + MARGIN)
        self.win_h = max(BUBBLE_SIZE + MARGIN + s.height, PANEL_H)
        self.sprite_off_y = self.win_h - s.height
        self.panel_y = self.win_h - PANEL_H
        self.set_size_request(self.win_w, self.win_h)
        self.resize(self.win_w, self.win_h)
        if self.get_realized():
            self.update_input_shape()

    def update_input_shape(self) -> None:
        rect = cairo.RectangleInt(self.sprite_off_x, self.sprite_off_y, self.sprite.width, self.sprite.height)
        self.input_shape_combine_region(cairo.Region(rect))

    def _on_screen_changed(self, *_):
        self.brain.set_bounds(self._bounds())

    # --- loop ------------------------------------------------------------

    def _on_tick(self) -> bool:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        self.brain.tick(dt)
        self.sprite.advance(min(dt, 0.1) * 1000)
        if self.brain.stressed:
            self.matrix.tick(dt)
        target = (int(self.brain.x) - self.sprite_off_x, int(self.brain.y) - self.sprite_off_y)
        if target != self._moved_to:
            self.move(*target)
            self._moved_to = target
        self.queue_draw()
        return True

    def _on_monitor(self) -> bool:
        self.brain.set_stressed(self.monitor.tick())
        return True

    def _on_draw(self, _widget, cr) -> bool:
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        b = self.brain
        Gdk.cairo_set_source_pixbuf(cr, self.sprite.frame(b.facing), self.sprite_off_x, self.sprite_off_y)
        cr.paint()
        bubble = b.bubble
        if bubble is not None:
            bx = self.sprite_off_x + (self.sprite.width - BUBBLE_SIZE) // 2
            by = self.sprite_off_y - BUBBLE_SIZE - MARGIN
            Gdk.cairo_set_source_pixbuf(cr, self.bubbles[bubble], bx, by)
            cr.paint()
        if b.stressed:
            room_right = b.bounds.right - (b.x + self.sprite.width)
            px = self.sprite_off_x + self.sprite.width + MARGIN if room_right >= PANEL_W + MARGIN else 0
            latest = self.monitor.latest
            self.matrix.draw(cr, px, self.panel_y, latest.cpu, latest.ram)
        return False

    # --- input -----------------------------------------------------------

    def _on_press(self, _widget, event) -> bool:
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.brain.press(event.x_root, event.y_root)
        return True

    def _on_motion(self, _widget, event) -> bool:
        self.brain.motion(event.x_root, event.y_root)
        return True

    def _on_release(self, _widget, event) -> bool:
        if event.button == 1:
            self.brain.release(event.x_root, event.y_root)
        return True

    # --- signals ---------------------------------------------------------

    def reload(self) -> bool:
        try:
            cfg = config_mod.load()
            frames = sprites.load_cached(cfg.pokemon)
        except (config_mod.ConfigError, sprites.SpriteError) as e:
            print(f"buddy: reload skipped: {e}", file=sys.stderr)
            return True
        self.cfg = cfg
        self.sprite = Sprite(frames, cfg.scale)
        self.monitor = StressMonitor(cfg.stress)
        self.brain.walk_speed = cfg.walk_speed
        self.brain.resize(self.sprite.width, self.sprite.height)
        self._layout()
        return True  # keep the SIGHUP handler installed

    def _quit(self) -> bool:
        Gtk.main_quit()
        return False


def run(cfg: Config, frames: list[tuple[Path, int]]) -> int:
    if Gdk.Display.get_default() is None:
        print(
            "buddy: could not open an X11 display. On Wayland buddy needs XWayland "
            "(sudo apt install xwayland).",
            file=sys.stderr,
        )
        return 1
    try:
        win = BuddyWindow(cfg, frames)
    except RuntimeError as e:
        print(f"buddy: {e}", file=sys.stderr)
        return 1
    win.show_all()
    win.update_input_shape()
    Gtk.main()
    return 0
