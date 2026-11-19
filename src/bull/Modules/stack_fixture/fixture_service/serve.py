"""The fixture service: an HTTP server on 127.0.0.1 answering `GET /health`.

`main([step, port, ...]) -> int` implements the service stack's `[run]` steps (reached through
`tool.py start|ready|stop <port>`):

- `start <port>`: launches the server as a detached background process and returns 0 without
  waiting for readiness. It does check briefly that the process did not exit at once (e.g. on a
  taken port: exit 1); a server ended by `stop` within that check is a normal stop (exit 0). Its
  pid goes to `<results>/serve-<port>.pid` and its output to `<results>/serve-<port>.log`.
  Refuses (exit 1) while our server for that port owns the pid file.
- `ready <port> [--timeout <seconds>]`: polls `GET /health` until it answers 200 (exit 0) or the
  timeout (default 30 s) passes (exit 1).
- `stop <port>`: terminates the server named by the pid file and removes the file; a missing pid
  file is not an error.

A pid file counts only when it holds a pid above 1 that belongs, by its command line, to this
module's server for the same port; otherwise (corrupt, or stale after pid reuse) it means "no
server": `stop` removes it without signalling anything and `start` replaces it.

The results folder is `BULL_RESULTS` (else `<BULL_PART_ROOT or cwd>/results`). Usage errors exit 64.
"""

from __future__ import annotations

import os
import signal
import subprocess
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
_START_CHECK = 0.3  # seconds start waits to catch a server that dies at once
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


def _read_pid(path: Path) -> int | None:
    """The server pid stored in `path`, or None when the file holds no usable pid.

    Only pids above 1 are accepted: 0, -1 and 1 would make `kill` signal the caller's process
    group, every process, or init. A non-numeric file is treated the same way (no server).
    """
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        return None
    return pid if pid > 1 else None


def _alive(pid: int) -> bool:
    """Whether a process with this pid exists (signal 0 probe; delivers nothing)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def _is_our_server(pid: int, port: int) -> bool:
    """Whether `pid` is a live fixture server for `port`, judged by its command line.

    Guards against a stale pid file whose pid the system has since given to an unrelated
    process: such a process is never signalled nor taken as a running server.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"cannot inspect process {pid}: {exc}", file=sys.stderr)
        return False  # unverifiable: never signal a process we cannot identify
    if result.returncode != 0:
        return False  # no such process
    words = result.stdout.split()
    return _MODULE in words and _SERVE_STEP in words and str(port) in words


def _ended_by_stop(code: int) -> bool:
    """Whether a server that ended during start's check window was ended by `stop`.

    `stop` ends the server with SIGTERM, then SIGKILL, so the process dies by one of those
    signals. A server that dies on its own (e.g. a taken port) exits with a non-negative code.
    An external SIGTERM/SIGKILL in the check window also reads as a stop; that is harmless,
    because `ready` then fails.
    """
    return code in (-signal.SIGTERM, -signal.SIGKILL)


def _start(args: list[str]) -> int:
    port = _port(args)
    pid_file = _pid_file(port)
    if pid_file.is_file():
        pid = _read_pid(pid_file)
        if pid is not None and _is_our_server(pid, port):
            print(
                f"start: a server for port {port} is already running", file=sys.stderr
            )
            return 1
        # a corrupt or stale pid file is replaced below
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    log = pid_file.with_suffix(".log")
    with log.open("wb") as log_out:
        # Own session and stdio away from the caller's pipes: the server outlives this call.
        proc = subprocess.Popen(
            [sys.executable, "-m", _MODULE, _SERVE_STEP, str(port)],
            stdin=subprocess.DEVNULL,
            stdout=log_out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    # Write the pid file before the start check: `ready` can succeed and `stop` run within the
    # check's window, and a `stop` that found no pid file would leave the server running.
    pid_file.write_text(f"{proc.pid}\n")
    try:
        code = proc.wait(timeout=_START_CHECK)
    except subprocess.TimeoutExpired:
        return 0  # still running: launched
    if _ended_by_stop(code):
        return 0  # launched, then ended by our own `stop` within the check window
    print(
        f"start: the server for port {port} exited at once (code {code}); see {log}",
        file=sys.stderr,
    )
    pid_file.unlink(missing_ok=True)
    return 1


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
    if pid is None or not _is_our_server(pid, port):
        pid_file.unlink(missing_ok=True)  # corrupt or stale: no server of ours to stop
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return 0
    except PermissionError:
        print(f"stop: not permitted to signal process {pid}", file=sys.stderr)
        return 1
    deadline = time.monotonic() + _STOP_GRACE
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
    if _alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # exited between the check and the kill
        except PermissionError:
            print(f"stop: not permitted to kill process {pid}", file=sys.stderr)
            return 1
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


# coverage-exempt-begin: script entry guard, runs only as `python -m`
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# coverage-exempt-end
