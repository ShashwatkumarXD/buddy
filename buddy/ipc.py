"""Talk to the running buddy over 127.0.0.1 — works the same on Linux, macOS and Windows.

The running buddy writes `<runtime dir>/buddy.port` (private to the user) with its port and a random
token. A command is one line, `"<token> <command>\\n"`; buddy replies `"ok\\n"`. Anything with the wrong
token, or an unknown command, is dropped without a reply. Stdlib only, so `buddy event` stays fast.
"""
import json
import os
import secrets
import socket
import time
from pathlib import Path

from buddy import paths

COMMANDS = ("ping", "thinking", "done", "reload", "quit")
CLIENT_TIMEOUT = 0.5
STALE_CLIENT_SECONDS = 2.0


def port_file() -> Path:
    return paths.runtime_dir() / "buddy.port"


def read_contact() -> tuple[int, str] | None:
    try:
        data = json.loads(port_file().read_text(encoding="utf-8"))
        return int(data["port"]), str(data["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def send(command: str, timeout: float = CLIENT_TIMEOUT) -> bool:
    """Send one command to the running buddy. True only if a real buddy accepted it."""
    contact = read_contact()
    if contact is None:
        return False
    port, token = contact
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
            conn.sendall(f"{token} {command}\n".encode())
            return conn.recv(16).startswith(b"ok")
    except OSError:
        return False


def is_running() -> bool:
    return send("ping")


class Server:
    """Non-blocking listener; the GUI loop calls poll() a few times a second."""

    def __init__(self, token: str | None = None):
        self.token = token or secrets.token_hex(16)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self._sock.setblocking(False)
        self.port = self._sock.getsockname()[1]
        self._clients: list[list] = []  # [connection, buffer, connected_at]

    def write_contact(self, path: Path | None = None) -> None:
        path = path or port_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"port": self.port, "token": self.token, "pid": os.getpid()}, f)
        os.replace(tmp, path)

    def remove_contact(self, path: Path | None = None) -> None:
        path = path or port_file()
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("token") == self.token:
                path.unlink()
        except (OSError, ValueError, AttributeError):
            pass

    def poll(self) -> list[str]:
        """Accept waiting clients and return the commands they sent (pings are answered, not returned)."""
        while True:
            try:
                conn, _ = self._sock.accept()
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            conn.setblocking(False)
            self._clients.append([conn, b"", time.monotonic()])
        commands = []
        for client in list(self._clients):
            conn, buffer, since = client
            try:
                data = conn.recv(256)
            except (BlockingIOError, InterruptedError):
                if time.monotonic() - since > STALE_CLIENT_SECONDS:
                    self._drop(client)
                continue
            except OSError:
                self._drop(client)
                continue
            buffer += data
            client[1] = buffer
            if b"\n" in buffer or not data or len(buffer) > 512:
                command = self._parse(buffer.split(b"\n", 1)[0])
                if command is not None:
                    try:
                        conn.sendall(b"ok\n")
                    except OSError:
                        pass
                    if command != "ping":
                        commands.append(command)
                self._drop(client)
        return commands

    def _parse(self, line: bytes) -> str | None:
        token, _, command = line.decode("utf-8", errors="replace").strip().partition(" ")
        if secrets.compare_digest(token.encode(), self.token.encode()) and command in COMMANDS:
            return command
        return None

    def _drop(self, client: list) -> None:
        try:
            client[0].close()
        except OSError:
            pass
        self._clients.remove(client)

    def close(self) -> None:
        for client in list(self._clients):
            self._drop(client)
        self._sock.close()
