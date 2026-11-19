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

import ast
import importlib.util
import json
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
                pid = int(pid_file.read_text().strip())
                if pid > 1:  # never 0/-1/1: those would signal groups or everything
                    os.kill(pid, 9)
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


# --- process safety, usage errors, log file, portability (unit 4 review) ---

_USAGE = 64


# Runs `main` with os.kill/os.killpg replaced by recorders that never deliver a real signal
# (only the harmless signal 0 probe goes through), so a buggy `stop` cannot hurt the machine
# running the tests. Prints the exit code and every recorded call as JSON.
def _recording_driver_source() -> str:
    return (
        "import json, os, sys\n"
        "calls = []\n"
        "real = os.kill\n"
        "def fake_kill(pid, sig):\n"
        "    calls.append(['kill', pid, int(sig)])\n"
        "    if int(sig) == 0:\n"
        "        return real(pid, 0)\n"
        "os.kill = fake_kill\n"
        "os.killpg = lambda pg, sig: calls.append(['killpg', pg, int(sig)])\n"
        "from bull.Modules.stack_fixture.fixture_service.serve import main\n"
        "rc = main(sys.argv[1:])\n"
        "print(json.dumps({'rc': rc, 'calls': calls}))\n"
    )


@pytest.fixture
def canary() -> Iterator[subprocess.Popen[bytes]]:
    proc = subprocess.Popen(["sleep", "120"], start_new_session=True)
    yield proc
    proc.kill()
    proc.wait()


@pytest.mark.parametrize("content", ["0", "-1", "1", "abc"])
def test_stop_with_corrupt_pid_file_signals_nothing_and_removes_it(
    service: Service, canary: subprocess.Popen[bytes], content: str
) -> None:
    pid_file = service.results / f"serve-{service.port}.pid"
    pid_file.write_text(content + "\n")
    env = dict(os.environ, BULL_RESULTS=str(service.results))
    result = subprocess.run(
        [sys.executable, "-c", _recording_driver_source(), "stop", str(service.port)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["rc"] == 0
    delivered = [c for c in report["calls"] if c[2] != 0]
    assert delivered == []
    assert not pid_file.exists()
    assert canary.poll() is None


@pytest.mark.parametrize("content", ["0", "-1", "1", "abc"])
def test_start_with_corrupt_pid_file_treats_it_as_no_server(
    service: Service, content: str
) -> None:
    pid_file = service.results / f"serve-{service.port}.pid"
    pid_file.write_text(content + "\n")
    assert service.main("start", str(service.port)).returncode == 0
    assert service.main("ready", str(service.port), "--timeout", "20").returncode == 0
    assert int(pid_file.read_text().strip()) > 1


def test_stop_with_stale_pid_file_naming_unrelated_process_leaves_it_running(
    service: Service, canary: subprocess.Popen[bytes]
) -> None:
    pid_file = service.results / f"serve-{service.port}.pid"
    pid_file.write_text(f"{canary.pid}\n")
    assert service.main("stop", str(service.port)).returncode == 0
    time.sleep(0.3)
    assert canary.poll() is None
    assert _alive(canary.pid)


def test_start_with_stale_pid_file_naming_unrelated_process_replaces_it(
    service: Service, canary: subprocess.Popen[bytes]
) -> None:
    pid_file = service.results / f"serve-{service.port}.pid"
    pid_file.write_text(f"{canary.pid}\n")
    assert service.main("start", str(service.port)).returncode == 0
    assert service.main("ready", str(service.port), "--timeout", "20").returncode == 0
    assert int(pid_file.read_text().strip()) != canary.pid
    assert canary.poll() is None


def test_start_twice_while_server_is_live_returns_1(service: Service) -> None:
    _start_ready(service)
    first_pid = service.pid_files()[0].read_text()
    assert service.main("start", str(service.port)).returncode == 1
    assert service.pid_files()[0].read_text() == first_pid
    assert service.get("/health")[0] == 200


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["bogus"],
        ["bogus", "1234"],
        ["start"],
        ["stop"],
        ["ready"],
        ["start", "abc"],
        ["stop", "abc"],
        ["ready", "abc"],
        ["start", "0"],
        ["start", "70000"],
        ["start", "-5"],
        ["ready", "1", "--timeout", "abc"],
        ["ready", "1", "--timeout"],
        ["ready", "1", "--bogus", "5"],
    ],
)
def test_usage_errors_exit_exactly_64(service: Service, argv: list[str]) -> None:
    assert service.main(*argv).returncode == _USAGE


def test_start_writes_server_output_log_in_results_folder(service: Service) -> None:
    _start_ready(service)
    assert (service.results / f"serve-{service.port}.log").is_file()


def test_background_launch_does_not_use_python_313_only_setsid_keyword() -> None:
    # pyproject requires Python >=3.11; `os.posix_spawn(..., setsid=True)` exists only in 3.13+.
    spec = importlib.util.find_spec("bull.Modules.stack_fixture.fixture_service.serve")
    assert spec is not None and spec.origin is not None
    tree = ast.parse(Path(spec.origin).read_text())
    keywords = {
        kw.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
    }
    assert "setsid" not in keywords


def _start_in_background(svc: Service) -> subprocess.Popen[str]:
    env = dict(os.environ, BULL_RESULTS=str(svc.results))
    return subprocess.Popen(
        [sys.executable, "-c", _DRIVER, "start", str(svc.port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_stop_during_the_start_check_window_is_not_a_start_failure(
    service: Service,
) -> None:
    starter = _start_in_background(service)
    deadline = time.monotonic() + 20
    while not service.pid_files() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert service.pid_files()
    assert service.main("stop", str(service.port)).returncode == 0
    out, err = starter.communicate(timeout=60)
    assert starter.returncode == 0, err
    assert "exited at once" not in out + err
    logs = list(service.results.glob("*.log"))
    assert all("exited at once" not in log.read_text() for log in logs)
    assert service.pid_files() == []


def test_start_with_port_already_taken_is_a_start_failure(service: Service) -> None:
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", service.port))
        blocker.listen()
        result = service.main("start", str(service.port))
    assert result.returncode == 1
    assert "exited at once" in result.stderr
    assert service.pid_files() == []
