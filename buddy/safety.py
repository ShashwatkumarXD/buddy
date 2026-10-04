"""Keep GLib callbacks alive: an error in one must never take the long-running buddy down.

GLib drops a timeout/signal source whose Python callback raises, and a dropped Unix signal source
falls back to the signal's default action, so the next SIGHUP or SIGUSR1 would kill buddy.
"""
import functools
import sys
import traceback


def keep_alive(callback):
    @functools.wraps(callback)
    def wrapper(*args, **kwargs):
        try:
            return callback(*args, **kwargs)
        except Exception:
            print(f"buddy: error in {callback.__name__} (still running):", file=sys.stderr)
            traceback.print_exc()
            return True

    return wrapper
