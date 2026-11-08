"""Tests for `bull.Modules.foundation.runner`."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import RunResult, ToolMissing
from bull.Modules.foundation.runner import LiveRunner


def _py(code: str, *args: str) -> list[str]:
    return [sys.executable, "-c", code, *args]


def _wait_for(predicate: object, seconds: float = 5.0) -> bool:
    assert callable(predicate)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_run_captures_stdout_as_text(tmp_path: Path) -> None:
    result = LiveRunner().run(_py("print('héllo')"), tmp_path)
    assert isinstance(result, RunResult)
    assert result.stdout == "héllo\n"
    assert result.returncode == 0


def test_run_captures_stderr_separately(tmp_path: Path) -> None:
    code = "import sys; sys.stderr.write('bad'); sys.stdout.write('good')"
    result = LiveRunner().run(_py(code), tmp_path)
    assert result.stdout == "good"
    assert result.stderr == "bad"


def test_run_returns_nonzero_exit_code(tmp_path: Path) -> None:
    result = LiveRunner().run(_py("raise SystemExit(7)"), tmp_path)
    assert result.returncode == 7


def test_run_records_argv_and_elapsed_seconds(tmp_path: Path) -> None:
    argv = _py("pass")
    result = LiveRunner().run(argv, tmp_path)
    assert result.argv == tuple(argv)
    assert result.seconds >= 0


def test_run_uses_cwd(tmp_path: Path) -> None:
    result = LiveRunner().run(_py("import os; print(os.getcwd())"), tmp_path)
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


def test_run_merges_env_over_current_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BULL_TEST_KEPT", "kept")
    monkeypatch.setenv("BULL_TEST_OVERRIDDEN", "old")
    code = (
        "import os; print(os.environ.get('BULL_TEST_KEPT'), "
        "os.environ.get('BULL_TEST_OVERRIDDEN'), os.environ.get('BULL_TEST_NEW'))"
    )
    result = LiveRunner().run(
        _py(code),
        tmp_path,
        env={"BULL_TEST_OVERRIDDEN": "new", "BULL_TEST_NEW": "added"},
    )
    assert result.stdout.strip() == "kept new added"


def test_run_without_env_inherits_current_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BULL_TEST_INHERITED", "yes")
    result = LiveRunner().run(
        _py("import os; print(os.environ['BULL_TEST_INHERITED'])"), tmp_path
    )
    assert result.stdout.strip() == "yes"


def test_run_does_not_use_a_shell(tmp_path: Path) -> None:
    result = LiveRunner().run(
        _py("import sys; print(sys.argv[1])", "a; echo $HOME *"), tmp_path
    )
    assert result.stdout.strip() == "a; echo $HOME *"


def test_run_missing_executable_raises_tool_missing_naming_it(tmp_path: Path) -> None:
    with pytest.raises(ToolMissing) as info:
        LiveRunner().run(["bull-no-such-tool-xyz", "--version"], tmp_path)
    assert "bull-no-such-tool-xyz" in info.value.message


def test_run_timeout_returns_124_with_timed_out_message(tmp_path: Path) -> None:
    result = LiveRunner().run(_py("import time; time.sleep(30)"), tmp_path, timeout=0.5)
    assert result.returncode == 124
    stderr = result.stderr.rstrip()
    assert "timed out after" in stderr
    assert stderr.endswith("s")
    assert "0.5" in stderr.rsplit("timed out after", 1)[1]


def test_run_timeout_keeps_output_written_before_the_timeout(tmp_path: Path) -> None:
    code = "import sys, time; sys.stderr.write('early\\n'); sys.stderr.flush(); time.sleep(30)"
    result = LiveRunner().run(_py(code), tmp_path, timeout=1.0)
    assert result.returncode == 124
    assert "early" in result.stderr
    assert result.stderr.rstrip().endswith("s")


def test_run_timeout_returns_promptly_even_if_a_grandchild_holds_the_output_pipes(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, sys, time, pathlib\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "time.sleep(30)\n"
    )
    start = time.monotonic()
    try:
        result = LiveRunner().run(_py(code), tmp_path, timeout=0.5)
        elapsed = time.monotonic() - start
        assert result.returncode == 124
        assert elapsed < 5
    finally:
        if pid_file.exists() and pid_file.read_text():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_run_without_timeout_waits_for_completion(tmp_path: Path) -> None:
    result = LiveRunner().run(
        _py("import time; time.sleep(0.2); print('done')"), tmp_path
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "done"


def test_spawn_starts_process_that_is_alive(tmp_path: Path) -> None:
    runner = LiveRunner()
    spawned = runner.spawn(_py("import time; time.sleep(30)"), tmp_path)
    try:
        assert spawned.pid > 0
        assert spawned.alive()
    finally:
        spawned.stop(grace=1.0)


def test_spawn_runs_in_its_own_process_group(tmp_path: Path) -> None:
    spawned = LiveRunner().spawn(_py("import time; time.sleep(30)"), tmp_path)
    try:
        assert os.getpgid(spawned.pid) == spawned.pid
        assert os.getpgid(spawned.pid) != os.getpgrp()
    finally:
        spawned.stop(grace=1.0)


def test_spawn_writes_output_to_log_file(tmp_path: Path) -> None:
    log = tmp_path / "out.log"
    code = "import sys; print('to-stdout'); sys.stderr.write('to-stderr\\n')"
    spawned = LiveRunner().spawn(_py(code), tmp_path, log=log)
    assert _wait_for(lambda: log.exists() and "to-stderr" in log.read_text())
    text = log.read_text()
    assert "to-stdout" in text
    spawned.stop(grace=1.0)


def test_spawn_creates_missing_log_parent_folders(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "deep" / "out.log"
    spawned = LiveRunner().spawn(_py("print('hi')"), tmp_path, log=log)
    assert _wait_for(lambda: log.exists() and "hi" in log.read_text())
    spawned.stop(grace=1.0)


def test_spawn_without_log_discards_output(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    spawned = LiveRunner().spawn(_py("print('quiet')"), tmp_path)
    assert _wait_for(lambda: not spawned.alive())
    captured = capfd.readouterr()
    assert "quiet" not in captured.out
    assert list(tmp_path.iterdir()) == []


def test_spawn_merges_env_over_current_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BULL_TEST_KEPT", "kept")
    log = tmp_path / "env.log"
    code = "import os; print(os.environ['BULL_TEST_KEPT'], os.environ['BULL_TEST_NEW'])"
    spawned = LiveRunner().spawn(
        _py(code), tmp_path, env={"BULL_TEST_NEW": "added"}, log=log
    )
    assert _wait_for(lambda: log.exists() and "added" in log.read_text())
    assert log.read_text().strip() == "kept added"
    spawned.stop(grace=1.0)


def test_spawn_uses_cwd(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    log = tmp_path / "cwd.log"
    spawned = LiveRunner().spawn(_py("import os; print(os.getcwd())"), work, log=log)
    assert _wait_for(lambda: log.exists() and log.read_text().strip() != "")
    assert Path(log.read_text().strip()).resolve() == work.resolve()
    spawned.stop(grace=1.0)


def test_alive_is_false_after_process_exits_on_its_own(tmp_path: Path) -> None:
    spawned = LiveRunner().spawn(_py("pass"), tmp_path)
    assert _wait_for(lambda: not spawned.alive())


def test_stop_terminates_running_process_and_alive_is_false(tmp_path: Path) -> None:
    spawned = LiveRunner().spawn(_py("import time; time.sleep(30)"), tmp_path)
    assert spawned.alive()
    spawned.stop(grace=2.0)
    assert not spawned.alive()


def test_stop_sends_sigterm_first_so_handlers_can_run(tmp_path: Path) -> None:
    marker = tmp_path / "terminated"
    ready = tmp_path / "ready"
    code = (
        "import signal, sys, time, pathlib\n"
        f"marker = pathlib.Path({str(marker)!r})\n"
        "def handler(signum, frame):\n"
        "    marker.write_text('term')\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, handler)\n"
        f"pathlib.Path({str(ready)!r}).write_text('1')\n"
        "time.sleep(30)\n"
    )
    spawned = LiveRunner().spawn(_py(code), tmp_path)
    assert _wait_for(ready.exists)
    spawned.stop(grace=3.0)
    assert marker.read_text() == "term"
    assert not spawned.alive()


def test_stop_escalates_to_sigkill_after_grace(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    code = (
        "import signal, time, pathlib\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"pathlib.Path({str(ready)!r}).write_text('1')\n"
        "time.sleep(30)\n"
    )
    spawned = LiveRunner().spawn(_py(code), tmp_path)
    assert _wait_for(ready.exists)
    start = time.monotonic()
    spawned.stop(grace=0.3)
    elapsed = time.monotonic() - start
    assert not spawned.alive()
    assert elapsed >= 0.25
    assert elapsed < 10


def test_stop_kills_child_processes_in_the_group(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    code = (
        "import subprocess, sys, time, pathlib\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(child.pid))\n"
        "time.sleep(30)\n"
    )
    spawned = LiveRunner().spawn(_py(code), tmp_path)
    assert _wait_for(child_pid_file.exists)
    assert _wait_for(lambda: child_pid_file.read_text() != "")
    child_pid = int(child_pid_file.read_text())
    spawned.stop(grace=2.0)

    def child_gone() -> bool:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            return True
        # A zombie child still answers signal 0; treat that as gone only if reaped by init.
        return False

    assert _wait_for(child_gone, 5.0)


def test_which_finds_an_existing_executable() -> None:
    found = LiveRunner().which(Path(sys.executable).name)
    if found is None:
        pytest.skip("interpreter name is not on PATH")
    assert isinstance(found, Path)
    assert found.exists()


def test_which_returns_path_for_a_common_tool() -> None:
    found = LiveRunner().which("sh")
    assert isinstance(found, Path)
    assert found.name == "sh"


def test_which_returns_none_for_unknown_tool() -> None:
    assert LiveRunner().which("bull-no-such-tool-xyz") is None
