"""The fixture service: an HTTP server on 127.0.0.1 answering `GET /health`.

`main([step, port, ...]) -> int` implements the service stack's `[run]` steps (reached through
`tool.py start|ready|stop <port>`):

- `start <port>`: launches the server as a detached background process and returns 0 without
  waiting for it; its pid goes to `<results>/serve-<port>.pid` and its output to
  `<results>/serve-<port>.log`. Refuses (exit 1) while a live server already owns that pid file.
- `ready <port> [--timeout <seconds>]`: polls `GET /health` until it answers 200 (exit 0) or the
  timeout (default 30 s) passes (exit 1).
- `stop <port>`: terminates the server named by the pid file and removes the file; a missing pid
  file is not an error.

The results folder is `BULL_RESULTS` (else `<BULL_PART_ROOT or cwd>/results`). Usage errors exit 64.
"""

from __future__ import annotations

import os
import signal
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_HOST = "127.0.0.1"
_MODULE = "bull.Modules.stack_fixture.fixture_service.serve"
_SERVE_STEP = (
    "_serve"  # internal: run the server in the foreground (the background process)
)
_DEFAULT_READY_TIMEOUT = 30.0
_POLL_INTERVAL = 0.1
_STOP_GRACE = 10.0
_USAGE = 64


class _UsageError(Exception):
    """The step was called with missing or malformed arguments."""


class _Handler(BaseHTTPRequestHandler):
    """`GET /health` → 200 `ok`; every other path → 404."""

    def do_GET(self) -> None:  # name fixed by http.server
        if self.path == "/health":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        """Silence the per-request access log."""


def _results() -> Path:
    raw = os.environ.get("BULL_RESULTS")
    if raw:
        return Path(raw)
    return Path(os.environ.get("BULL_PART_ROOT") or Path.cwd()) / "results"


def _port(args: list[str]) -> int:
    if not args:
        raise _UsageError("missing port")
    try:
        port = int(args[0])
    except ValueError as exc:
        raise _UsageError(f"port is not a number: {args[0]!r}") from exc
    if not 0 < port < 65536:
        raise _UsageError(f"port out of range: {port}")
    return port


def _pid_file(port: int) -> Path:
    return _results() / f"serve-{port}.pid"


def _read_pid(path: Path) -> int:
    """The pid stored in `path`; raises _UsageError when the file does not hold one."""
    text = path.read_text().strip()
    try:
        return int(text)
    except ValueError as exc:
        raise _UsageError(f"{path.name} does not hold a pid: {text!r}") from exc


def _alive(pid: int) -> bool:
    """Whether `pid` runs; reaps it first when it is our own exited child (a zombie)."""
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass  # not our child: whoever started it reaps it
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def _start(args: list[str]) -> int:
    port = _port(args)
    pid_file = _pid_file(port)
    if pid_file.is_file():
        try:
            running = _alive(_read_pid(pid_file))
        except _UsageError:
            running = False  # a corrupt pid file is replaced below
        if running:
            print(
                f"start: a server for port {port} is already running", file=sys.stderr
            )
            return 1
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log = pid_file.with_suffix(".log")
    # posix_spawn gives a detached child (own session, stdio away from the caller's pipes)
    # without a Popen object that would expect to be waited on.
    pid = os.posix_spawn(
        sys.executable,
        [sys.executable, "-m", _MODULE, _SERVE_STEP, str(port)],
        dict(os.environ),
        file_actions=[
            (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
            (
                os.POSIX_SPAWN_OPEN,
                1,
                str(log),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o644,
            ),
            (os.POSIX_SPAWN_DUP2, 1, 2),
        ],
        setsid=True,
    )
    pid_file.write_text(f"{pid}\n")
    return 0


def _ready(args: list[str]) -> int:
    port = _port(args)
    rest = args[1:]
    timeout = _DEFAULT_READY_TIMEOUT
    if rest:
        if len(rest) != 2 or rest[0] != "--timeout":
            raise _UsageError("ready takes <port> [--timeout <seconds>]")
        try:
            timeout = float(rest[1])
        except ValueError as exc:
            raise _UsageError(f"timeout is not a number: {rest[1]!r}") from exc
    url = f"http://{_HOST}:{port}/health"
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                f"ready: {url} did not answer 200 within {timeout:g}s", file=sys.stderr
            )
            return 1
        try:
            with urllib.request.urlopen(url, timeout=min(1.0, remaining)) as resp:
                if resp.status == 200:
                    return 0
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass  # not up yet: keep polling until the deadline
        time.sleep(min(_POLL_INTERVAL, max(0.0, deadline - time.monotonic())))


def _stop(args: list[str]) -> int:
    port = _port(args)
    pid_file = _pid_file(port)
    if not pid_file.is_file():
        return 0
    pid = _read_pid(pid_file)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return 0
    deadline = time.monotonic() + _STOP_GRACE
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # exited between the check and the kill
    pid_file.unlink(missing_ok=True)
    return 0


def _serve(args: list[str]) -> int:
    """Run the server in the foreground until killed (the background process's body)."""
    port = _port(args)
    with HTTPServer((_HOST, port), _Handler) as server:
        server.serve_forever()
    return 0


_STEPS = {"start": _start, "ready": _ready, "stop": _stop, _SERVE_STEP: _serve}


def main(argv: list[str]) -> int:
    """Run one service step (`start`, `ready` or `stop`); 64 for a usage error."""
    if not argv or argv[0] not in _STEPS:
        print("usage: serve <start|ready|stop> <port> …", file=sys.stderr)
        return _USAGE
    try:
        return _STEPS[argv[0]](argv[1:])
    except _UsageError as exc:
        print(f"{argv[0]}: {exc}", file=sys.stderr)
        return _USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
