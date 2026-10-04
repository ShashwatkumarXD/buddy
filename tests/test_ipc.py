import json
import os
import socket
import sys
import threading
import time

import pytest

from buddy import ipc


@pytest.fixture(autouse=True)
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def server():
    srv = ipc.Server()
    srv.write_contact()
    yield srv
    srv.close()


def ask_in_background(command):
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("ok", ipc.send(command)))
    thread.start()
    return thread, result


def pump(srv, thread, seconds=3.0):
    got = []
    deadline = time.monotonic() + seconds
    while (thread.is_alive() or not got) and time.monotonic() < deadline:
        got += srv.poll()
        if not thread.is_alive() and got:
            break
        time.sleep(0.01)
    thread.join(1)
    return got


def test_command_round_trip(server):
    thread, result = ask_in_background("thinking")
    assert pump(server, thread) == ["thinking"]
    assert result["ok"] is True


def test_ping_answers_but_is_not_reported(server):
    thread, result = ask_in_background("ping")
    got = []
    deadline = time.monotonic() + 3
    while thread.is_alive() and time.monotonic() < deadline:
        got += server.poll()
        time.sleep(0.01)
    assert result["ok"] is True
    assert got == []


def test_server_ignores_wrong_token(server):
    ipc.port_file().write_text(json.dumps({"port": server.port, "token": "not-the-token", "pid": 1}))
    thread, result = ask_in_background("quit")
    deadline = time.monotonic() + 3
    got = []
    while thread.is_alive() and time.monotonic() < deadline:
        got += server.poll()
        time.sleep(0.01)
    assert result["ok"] is False
    assert got == []


def test_unknown_command_is_ignored(server):
    thread, result = ask_in_background("format-disk")
    deadline = time.monotonic() + 3
    got = []
    while thread.is_alive() and time.monotonic() < deadline:
        got += server.poll()
        time.sleep(0.01)
    assert result["ok"] is False
    assert got == []


def test_stale_port_file_is_not_running():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    ipc.port_file().parent.mkdir(parents=True, exist_ok=True)
    ipc.port_file().write_text(json.dumps({"port": free_port, "token": "x", "pid": 1}))
    start = time.monotonic()
    assert ipc.is_running() is False
    assert time.monotonic() - start < 1.0


def test_no_port_file_means_not_running():
    assert ipc.is_running() is False
    assert ipc.send("thinking") is False


def test_remove_contact_only_removes_its_own_file(server):
    other = ipc.Server()
    other.remove_contact()  # not its file
    assert ipc.port_file().exists()
    server.remove_contact()
    assert not ipc.port_file().exists()
    other.close()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")
def test_contact_file_is_private(server):
    assert os.stat(ipc.port_file()).st_mode & 0o777 == 0o600


def test_garbage_bytes_do_not_crash_the_server(server):
    with socket.create_connection(("127.0.0.1", server.port), timeout=1) as conn:
        conn.sendall("é\xff tökén quit\n".encode("utf-8", "surrogatepass") + b"\xfe\xff\n")
        deadline = time.monotonic() + 1
        got = []
        while time.monotonic() < deadline:
            got += server.poll()
            time.sleep(0.01)
    assert got == []
