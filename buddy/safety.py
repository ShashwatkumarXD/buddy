"""Keep GUI callbacks alive: an error in one timer tick or command must never take buddy down.

Every timer and IPC callback in the window is wrapped, so a bad frame, a broken reload or a
surprise from the OS is logged to stderr and buddy keeps running.
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
