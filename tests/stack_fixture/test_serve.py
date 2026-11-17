"""Tests for `bull.Modules.stack_fixture.fixture_service.serve`, written from the spec.

Choices where the spec is open (the code-writer must follow these):
- `main(argv) -> int` takes `[step, port, ...]` with step `start`, `ready` or `stop`; the port is
  the second element as a decimal string. An unknown step or an empty argv returns non-zero.
- The results folder comes from the `BULL_RESULTS` environment variable; `start` writes exactly
  one `*.pid` file there holding the server's pid, and `stop` removes it.
- `start` returns 0 once the server process is launched in the background (it does not wait for
  readiness; `ready` does). `ready` accepts an optional `--timeout <seconds>` after the port and
  returns 0 as soon as `GET /health` answers 200, non-zero when the timeout passes first.
- `stop` with no pid file is not an error (returns 0): stopping is idempotent.
- Any path other than `/health` answers 404.

Each test drives `main` in a subprocess so the background server is reparented and reaped.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

_DRIVER = (
    "import sys;"
    "from bull.Modules.stack_fixture.fixture_service.serve import main;"
    "sys.exit(main(sys.argv[1:]))"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


class Service:
    def __init__(self, results: Path) -> None:
        self.results = results
        self.port = _free_port()

    def main(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, BULL_RESULTS=str(self.results))
        return subprocess.run(
            [sys.executable, "-c", _DRIVER, *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def pid_files(self) -> list[Path]:
        return sorted(self.results.glob("*.pid"))

    def get(self, path: str) -> tuple[int, str]:
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return int(resp.status), resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, ""

    def cleanup(self) -> None:
        for pid_file in self.pid_files():
            try:
                os.kill(int(pid_file.read_text().strip()), 9)
            except (ValueError, ProcessLookupError, OSError):
                pass


@pytest.fixture
def service(tmp_path: Path) -> Iterator[Service]:
    results = tmp_path / "results"
    results.mkdir()
    svc = Service(results)
    yield svc
    svc.cleanup()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_dead(pid: int) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


def _start_ready(svc: Service) -> None:
    assert svc.main("start", str(svc.port)).returncode == 0
    assert svc.main("ready", str(svc.port), "--timeout", "20").returncode == 0


def test_start_launches_background_server_and_writes_pid_file(
    service: Service,
) -> None:
    result = service.main("start", str(service.port))
    assert result.returncode == 0
    pids = service.pid_files()
    assert len(pids) == 1
    pid = int(pids[0].read_text().strip())
    assert _alive(pid)


def test_health_answers_200_on_loopback_after_start(service: Service) -> None:
    _start_ready(service)
    status, _ = service.get("/health")
    assert status == 200


def test_unknown_path_answers_404(service: Service) -> None:
    _start_ready(service)
    status, _ = service.get("/nope")
    assert status == 404


def test_ready_succeeds_when_server_is_up(service: Service) -> None:
    assert service.main("start", str(service.port)).returncode == 0
    assert service.main("ready", str(service.port), "--timeout", "20").returncode == 0


def test_ready_fails_when_nothing_listens_before_timeout(service: Service) -> None:
    started = time.monotonic()
    result = service.main("ready", str(service.port), "--timeout", "1")
    assert result.returncode != 0
    assert time.monotonic() - started < 15


def test_stop_terminates_server_and_removes_pid_file(service: Service) -> None:
    _start_ready(service)
    pid = int(service.pid_files()[0].read_text().strip())
    assert service.main("stop", str(service.port)).returncode == 0
    assert _wait_dead(pid)
    assert service.pid_files() == []
    with pytest.raises((urllib.error.URLError, ConnectionError)):
        urllib.request.urlopen(f"http://127.0.0.1:{service.port}/health", timeout=2)


def test_stop_without_pid_file_is_not_an_error(service: Service) -> None:
    assert service.main("stop", str(service.port)).returncode == 0


def test_stop_twice_is_not_an_error(service: Service) -> None:
    _start_ready(service)
    assert service.main("stop", str(service.port)).returncode == 0
    assert service.main("stop", str(service.port)).returncode == 0


@pytest.mark.parametrize("argv", [[], ["bogus"], ["bogus", "1234"]])
def test_unknown_step_or_empty_argv_returns_non_zero(
    service: Service, argv: list[str]
) -> None:
    assert service.main(*argv).returncode != 0
