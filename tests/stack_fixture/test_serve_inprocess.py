"""In-process tests for `bull.Modules.stack_fixture.fixture_service.serve`."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path

import pytest

from bull.Modules.stack_fixture.fixture_service import serve

MODULE = "bull.Modules.stack_fixture.fixture_service.serve"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture(autouse=True)
def results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "results"
    monkeypatch.setenv("BULL_RESULTS", str(folder))
    return folder


@pytest.fixture
def health_server() -> Iterator[int]:
    server = HTTPServer(("127.0.0.1", 0), serve._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- argv validation ---------------------------------------------------------------------


@pytest.mark.parametrize("argv", [[], ["bogus"], ["bogus", "80"]])
def test_empty_or_unknown_step_is_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert serve.main(argv) == 64
    assert "usage" in capsys.readouterr().err


@pytest.mark.parametrize("step", ["start", "ready", "stop"])
@pytest.mark.parametrize("port", ["abc", "0", "65536", "-5", ""])
def test_bad_port_is_usage_error(step: str, port: str) -> None:
    assert serve.main([step, port]) == 64


@pytest.mark.parametrize("step", ["start", "ready", "stop"])
def test_missing_port_is_usage_error(
    step: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert serve.main([step]) == 64
    assert "missing port" in capsys.readouterr().err


# --- results folder ----------------------------------------------------------------------


def test_results_folder_falls_back_to_part_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BULL_RESULTS")
    monkeypatch.setenv("BULL_PART_ROOT", str(tmp_path))
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "serve-5001.pid").write_text("garbage")
    assert serve.main(["stop", "5001"]) == 0
    assert not (tmp_path / "results" / "serve-5001.pid").exists()


def test_results_folder_falls_back_to_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BULL_RESULTS")
    monkeypatch.delenv("BULL_PART_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "serve-5002.pid").write_text("")
    assert serve.main(["stop", "5002"]) == 0
    assert not (tmp_path / "results" / "serve-5002.pid").exists()


# --- pid file parsing --------------------------------------------------------------------


@pytest.mark.parametrize("text", ["garbage", "", "0", "1", "-1", "-999"])
def test_unusable_pid_values_are_no_pid(tmp_path: Path, text: str) -> None:
    f = tmp_path / "p.pid"
    f.write_text(text)
    assert serve._read_pid(f) is None


def test_usable_pid_is_returned(tmp_path: Path) -> None:
    f = tmp_path / "p.pid"
    f.write_text(" 4242\n")
    assert serve._read_pid(f) == 4242


# --- stop --------------------------------------------------------------------------------


def test_stop_without_pid_file_is_ok() -> None:
    assert serve.main(["stop", "5003"]) == 0


@pytest.mark.parametrize("text", ["garbage", "0", "1", "-1"])
def test_stop_corrupt_pid_file_is_removed_without_signalling(
    results: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    results.mkdir()
    pid_file = results / "serve-5004.pid"
    pid_file.write_text(text)
    monkeypatch.setattr(
        os, "kill", lambda *a: pytest.fail("must not signal"), raising=True
    )
    assert serve.main(["stop", "5004"]) == 0
    assert not pid_file.exists()


def test_stop_stale_pid_not_our_server_is_removed_without_signalling(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results.mkdir()
    pid_file = results / "serve-5005.pid"
    pid_file.write_text(f"{os.getpid()}\n")  # a live process, but not our server
    monkeypatch.setattr(
        os, "kill", lambda *a: pytest.fail("must not signal"), raising=True
    )
    assert serve.main(["stop", "5005"]) == 0
    assert not pid_file.exists()


def _ours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serve, "_is_our_server", lambda pid, port: True)


def test_stop_sends_sigterm_and_removes_pid_file(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results.mkdir()
    pid_file = results / "serve-5006.pid"
    pid_file.write_text("4242\n")
    _ours(monkeypatch)
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append((pid, sig)))
    monkeypatch.setattr(serve, "_alive", lambda pid: False)
    assert serve.main(["stop", "5006"]) == 0
    assert sent == [(4242, signal.SIGTERM)]
    assert not pid_file.exists()


def test_stop_process_already_gone_removes_pid_file(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results.mkdir()
    pid_file = results / "serve-5007.pid"
    pid_file.write_text("4242\n")
    _ours(monkeypatch)

    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", gone)
    assert serve.main(["stop", "5007"]) == 0
    assert not pid_file.exists()


def test_stop_permission_denied_fails(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results.mkdir()
    pid_file = results / "serve-5008.pid"
    pid_file.write_text("4242\n")
    _ours(monkeypatch)

    def denied(pid: int, sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(os, "kill", denied)
    assert serve.main(["stop", "5008"]) == 1
    assert "not permitted" in capsys.readouterr().err
    assert pid_file.exists()


def test_stop_escalates_to_sigkill_when_process_survives(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results.mkdir()
    pid_file = results / "serve-5009.pid"
    pid_file.write_text("4242\n")
    _ours(monkeypatch)
    sent: list[int] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append(sig))
    monkeypatch.setattr(serve, "_alive", lambda pid: True)
    monkeypatch.setattr(serve, "_STOP_GRACE", 0.0)
    assert serve.main(["stop", "5009"]) == 0
    assert sent == [signal.SIGTERM, signal.SIGKILL]
    assert not pid_file.exists()


def test_stop_sigkill_race_with_exit_is_ok(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results.mkdir()
    pid_file = results / "serve-5010.pid"
    pid_file.write_text("4242\n")
    _ours(monkeypatch)

    def kill(pid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            raise ProcessLookupError

    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(serve, "_alive", lambda pid: True)
    monkeypatch.setattr(serve, "_STOP_GRACE", 0.0)
    assert serve.main(["stop", "5010"]) == 0
    assert not pid_file.exists()


def test_stop_sigkill_permission_denied_fails(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results.mkdir()
    pid_file = results / "serve-5011.pid"
    pid_file.write_text("4242\n")
    _ours(monkeypatch)

    def kill(pid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            raise PermissionError

    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(serve, "_alive", lambda pid: True)
    monkeypatch.setattr(serve, "_STOP_GRACE", 0.0)
    assert serve.main(["stop", "5011"]) == 1
    assert "not permitted to kill" in capsys.readouterr().err


# --- process probes ----------------------------------------------------------------------


def test_alive_true_for_own_process() -> None:
    assert serve._alive(os.getpid())


def test_alive_false_when_no_such_process(monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", gone)
    assert not serve._alive(4242)


def test_alive_true_when_owned_by_someone_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def denied(pid: int, sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(os, "kill", denied)
    assert serve._alive(4242)


def _fake_ps(
    monkeypatch: pytest.MonkeyPatch, code: int, out: str = "", error: bool = False
) -> None:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if error:
            raise OSError("no ps")
        return subprocess.CompletedProcess(["ps"], code, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", run)


def test_is_our_server_matches_module_step_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_ps(monkeypatch, 0, f"/usr/bin/python -m {MODULE} _serve 7777\n")
    assert serve._is_our_server(1234, 7777)


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/python other.py",
        f"python -m {MODULE} _serve 8888",
        f"python -m {MODULE} start 7777",
    ],
)
def test_is_our_server_rejects_other_commands(
    monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    _fake_ps(monkeypatch, 0, command)
    assert not serve._is_our_server(1234, 7777)


def test_is_our_server_false_when_process_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_ps(monkeypatch, 1)
    assert not serve._is_our_server(1234, 7777)


def test_is_our_server_false_when_ps_cannot_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_ps(monkeypatch, 0, error=True)
    assert not serve._is_our_server(1234, 7777)
    assert "cannot inspect process" in capsys.readouterr().err


def test_is_our_server_false_when_ps_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("ps", 10)

    monkeypatch.setattr(subprocess, "run", run)
    assert not serve._is_our_server(1234, 7777)


# --- start -------------------------------------------------------------------------------


class FakeProc:
    pid = 31337

    def __init__(self, exit_code: int | None) -> None:
        self.exit_code = exit_code

    def wait(self, timeout: float) -> int:
        if self.exit_code is None:
            raise subprocess.TimeoutExpired("serve", timeout)
        return self.exit_code


def _popen(monkeypatch: pytest.MonkeyPatch, proc: FakeProc) -> list[list[str]]:
    launched: list[list[str]] = []

    def popen(cmd: list[str], **kwargs: object) -> FakeProc:
        launched.append(cmd)
        assert kwargs["start_new_session"] is True
        return proc

    monkeypatch.setattr(subprocess, "Popen", popen)
    return launched


def test_start_launches_background_server_and_writes_pid_file(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launched = _popen(monkeypatch, FakeProc(None))
    assert serve.main(["start", "5012"]) == 0
    assert (results / "serve-5012.pid").read_text().strip() == "31337"
    assert (results / "serve-5012.log").is_file()
    assert launched[0][1:] == ["-m", MODULE, "_serve", "5012"]


def test_start_server_exiting_at_once_fails_and_leaves_no_pid_file(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _popen(monkeypatch, FakeProc(3))
    assert serve.main(["start", "5013"]) == 1
    assert not (results / "serve-5013.pid").exists()
    assert "exited at once" in capsys.readouterr().err


def test_start_refused_while_our_server_owns_pid_file(
    results: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results.mkdir()
    (results / "serve-5014.pid").write_text("4242\n")
    _ours(monkeypatch)
    launched = _popen(monkeypatch, FakeProc(None))
    assert serve.main(["start", "5014"]) == 1
    assert "already running" in capsys.readouterr().err
    assert launched == []
    assert (results / "serve-5014.pid").read_text().strip() == "4242"


@pytest.mark.parametrize("text", ["garbage", "0", "1", "-1"])
def test_start_replaces_corrupt_pid_file(
    results: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    results.mkdir()
    (results / "serve-5015.pid").write_text(text)
    _popen(monkeypatch, FakeProc(None))
    assert serve.main(["start", "5015"]) == 0
    assert (results / "serve-5015.pid").read_text().strip() == "31337"


def test_start_replaces_stale_pid_file(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results.mkdir()
    (results / "serve-5016.pid").write_text("4242\n")
    monkeypatch.setattr(serve, "_is_our_server", lambda pid, port: False)
    _popen(monkeypatch, FakeProc(None))
    assert serve.main(["start", "5016"]) == 0
    assert (results / "serve-5016.pid").read_text().strip() == "31337"


def test_start_real_server_then_ready_then_stop(
    results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_popen = subprocess.Popen

    def reaping_popen(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        # the test process is the server's parent: reap it so `stop` sees it exit
        proc: subprocess.Popen[bytes] = real_popen(*args, **kwargs)  # type: ignore[call-overload]
        threading.Thread(target=proc.wait, daemon=True).start()
        return proc

    monkeypatch.setattr(subprocess, "Popen", reaping_popen)
    port = _free_port()
    try:
        assert serve.main(["start", str(port)]) == 0
        assert serve.main(["ready", str(port), "--timeout", "15"]) == 0
        # a second start is refused while ours owns the pid file
        assert serve.main(["start", str(port)]) == 1
    finally:
        assert serve.main(["stop", str(port)]) == 0
    assert not (results / f"serve-{port}.pid").exists()
    assert serve.main(["ready", str(port), "--timeout", "0.3"]) == 1


# --- ready -------------------------------------------------------------------------------


def test_ready_succeeds_against_running_server(health_server: int) -> None:
    assert serve.main(["ready", str(health_server)]) == 0


def test_ready_with_timeout_option_succeeds(health_server: int) -> None:
    assert serve.main(["ready", str(health_server), "--timeout", "5"]) == 0


def test_ready_times_out_when_nothing_listens(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert serve.main(["ready", str(_free_port()), "--timeout", "0.3"]) == 1
    assert "did not answer 200" in capsys.readouterr().err


def test_ready_zero_timeout_fails_at_once() -> None:
    assert serve.main(["ready", str(_free_port()), "--timeout", "0"]) == 1


@pytest.mark.parametrize(
    "extra",
    [["--timeout"], ["--wait", "5"], ["--timeout", "1", "extra"], ["5"]],
)
def test_ready_malformed_options_are_usage_errors(extra: list[str]) -> None:
    assert serve.main(["ready", "5017", *extra]) == 64


def test_ready_non_numeric_timeout_is_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert serve.main(["ready", "5017", "--timeout", "soon"]) == 64
    assert "timeout is not a number" in capsys.readouterr().err


def test_ready_polls_until_server_comes_up() -> None:
    port = _free_port()
    started: list[HTTPServer] = []

    def later() -> None:
        import time

        time.sleep(0.4)
        server = HTTPServer(("127.0.0.1", port), serve._Handler)
        started.append(server)
        server.serve_forever()

    thread = threading.Thread(target=later, daemon=True)
    thread.start()
    try:
        assert serve.main(["ready", str(port), "--timeout", "10"]) == 0
    finally:
        for server in started:
            server.shutdown()
            server.server_close()
        thread.join(timeout=5)


# --- handler -----------------------------------------------------------------------------


def test_health_answers_200_ok(health_server: int) -> None:
    with urllib.request.urlopen(f"http://127.0.0.1:{health_server}/health") as resp:
        assert resp.status == 200
        assert resp.read() == b"ok\n"


@pytest.mark.parametrize("path", ["/", "/healthz", "/health/x", "/other"])
def test_other_paths_answer_404(health_server: int, path: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(f"http://127.0.0.1:{health_server}{path}")
    assert info.value.code == 404


def test_handler_access_log_is_silent(capsys: pytest.CaptureFixture[str]) -> None:
    handler = serve._Handler.__new__(serve._Handler)
    handler.log_message("%s", "x")
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


# --- serve loop --------------------------------------------------------------------------


def test_serve_step_runs_loop_until_shut_down(monkeypatch: pytest.MonkeyPatch) -> None:
    port = _free_port()
    servers: list[HTTPServer] = []
    real = HTTPServer

    def make(addr: tuple[str, int], handler: type) -> HTTPServer:
        server = real(addr, handler)
        servers.append(server)
        return server

    monkeypatch.setattr(serve, "HTTPServer", make)
    result: list[int] = []
    thread = threading.Thread(
        target=lambda: result.append(serve.main(["_serve", str(port)])), daemon=True
    )
    thread.start()
    try:
        assert serve.main(["ready", str(port), "--timeout", "10"]) == 0
    finally:
        for server in servers:
            server.shutdown()
        thread.join(timeout=5)
    assert result == [0]


def test_serve_step_bad_port_is_usage_error() -> None:
    assert serve.main(["_serve", "nope"]) == 64
