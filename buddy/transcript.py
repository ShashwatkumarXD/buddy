"""Notice when the user stops Claude Code mid-turn.

Claude Code runs no hook on an interrupt (its Stop hook skips them), but it does append a user entry
whose only content is `[Request interrupted by user]` (or `... for tool use]`) to the session
transcript. The thinking hook tells buddy where that transcript is; buddy reads what gets added.
"""
import json
from pathlib import Path

MARKER = "[Request interrupted by user"
MAX_LINE = 64 * 1024  # an interrupt entry is tiny; longer lines are skipped, not buffered
MAX_READ = 1024 * 1024  # per check


def is_interrupt(line: bytes) -> bool:
    if MARKER.encode() not in line:
        return False
    try:
        entry = json.loads(line)
        content = entry["message"]["content"]
        return entry["type"] == "user" and any(
            part.get("type") == "text" and part.get("text", "").startswith(MARKER) for part in content
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


class TranscriptWatch:
    """Reads only what is appended after the prompt, so an earlier turn's interrupt doesn't count."""

    def __init__(self, path: Path):
        self.path = path
        self._offset = self._size()
        self._partial = b""

    def _size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def interrupted(self) -> bool:
        size = self._size()
        if size < self._offset:  # rewritten: start over from its end
            self._offset, self._partial = size, b""
        if size == self._offset:
            return False
        try:
            with self.path.open("rb") as f:
                f.seek(self._offset)
                data = f.read(MAX_READ)
        except OSError:
            return False
        self._offset += len(data)
        *lines, self._partial = (self._partial + data).split(b"\n")
        if len(self._partial) > MAX_LINE:
            self._partial = b""  # its tail arrives as a line that isn't valid JSON, and is ignored
        return any(is_interrupt(line) for line in lines)


def watch(path: str) -> TranscriptWatch | None:
    """A watch on the transcript at `path`, or None if it doesn't look like one."""
    p = Path(path)
    if not path or not p.is_absolute() or p.suffix != ".jsonl":
        return None
    return TranscriptWatch(p)
