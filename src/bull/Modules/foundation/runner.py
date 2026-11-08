"""The process runner: argument lists only, never a shell."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from bull.Modules.foundation.Contracts import RunResult, Runner, Spawned, ToolMissing

# Exit code reported for a run that hit its timeout (the `timeout(1)` convention).
_TIMEOUT_RETURNCODE = 124
# How often `stop` checks whether the process group has emptied.
_POLL_SECONDS = 0.02


def _merged_env(env: Mapping[str, str] | None) -> dict[str, str] | None:
    """`env` laid over the current environment, or None to inherit it unchanged."""
    if env is None:
        return None
    return {**os.environ, **env}


def _tool_missing(
    argv: Sequence[str], cwd: Path, error: FileNotFoundError
) -> BaseException:
    """`ToolMissing` when the executable is missing; the original error when `cwd` is."""
    if error.filename is not None and Path(error.filename) == cwd:
        return error
    tool = argv[0]
    return ToolMissing(
        f"{tool} was not found on PATH",
        fix=f"Install {tool} or add it to PATH.",
    )


# macOS answers EPERM (not ESRCH) for a group whose only members are zombies; the
# group holds only processes we started, so both mean "nothing left to signal".
_GROUP_GONE = (ProcessLookupError, PermissionError)


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except _GROUP_GONE:
        return False
    return True


def _signal_group(pgid: int, signum: int) -> None:
    """Send `signum` to the group; an already-empty group is not an error."""
    try:
        os.killpg(pgid, signum)
    except _GROUP_GONE:
        pass


class LiveSpawned(Spawned):
    """A background process leading its own process group (pgid == pid)."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self._process = process
        self.pid = process.pid

    def alive(self) -> bool:
        return self._process.poll() is None

    def stop(self, grace: float = 5.0) -> None:
        """SIGTERM the whole group, wait up to `grace` seconds for it to empty, then SIGKILL.

        Safe to call on a process that has already exited, and more than once.
        """
        pgid = self.pid
        deadline = time.monotonic() + grace
        _signal_group(pgid, signal.SIGTERM)
        try:
            self._process.wait(timeout=max(grace, 0.0))
        except subprocess.TimeoutExpired:
            pass
        while _group_exists(pgid) and time.monotonic() < deadline:
            time.sleep(_POLL_SECONDS)
        if _group_exists(pgid):
            _signal_group(pgid, signal.SIGKILL)
        self._process.wait()


class LiveRunner(Runner):
    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        """Run `argv` to completion, capturing output as text.

        Raises `ToolMissing` when the executable can't be found. A timeout kills the
        process and returns code 124 with "timed out after <n>s" appended to stderr.
        """
        args = list(argv)
        start = time.monotonic()
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=_merged_env(env),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as error:
            raise _tool_missing(args, cwd, error) from error
        with process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                if stderr and not stderr.endswith("\n"):
                    stderr += "\n"
                stderr += f"timed out after {timeout:g}s"
                returncode = _TIMEOUT_RETURNCODE
        return RunResult(
            argv=tuple(args),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            seconds=time.monotonic() - start,
        )

    def spawn(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        log: Path | None = None,
    ) -> Spawned:
        """Start `argv` in the background, in its own process group.

        stdout and stderr go to `log` (appended; parent folders created) or are discarded.
        Raises `ToolMissing` when the executable can't be found.
        """
        args = list(argv)
        try:
            if log is None:
                process = self._popen(args, cwd, env, subprocess.DEVNULL)
            else:
                log.parent.mkdir(parents=True, exist_ok=True)
                # The child keeps its own copy of the descriptor; ours closes here.
                with log.open("ab") as handle:
                    process = self._popen(args, cwd, env, handle.fileno())
        except FileNotFoundError as error:
            raise _tool_missing(args, cwd, error) from error
        return LiveSpawned(process)

    @staticmethod
    def _popen(
        args: list[str], cwd: Path, env: Mapping[str, str] | None, output: int
    ) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            args,
            cwd=cwd,
            env=_merged_env(env),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def which(self, tool: str) -> Path | None:
        found = shutil.which(tool)
        return Path(found) if found is not None else None
