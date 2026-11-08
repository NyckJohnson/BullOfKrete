"""The process runner: argument lists only, never a shell."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from bull.Modules.foundation.Contracts import RunResult, Runner, Spawned


class LiveSpawned(Spawned):
    def alive(self) -> bool:
        raise NotImplementedError(f"{type(self).__name__}.alive")

    def stop(self, grace: float = 5.0) -> None:
        raise NotImplementedError(f"{type(self).__name__}.stop")


class LiveRunner(Runner):
    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        raise NotImplementedError(f"{type(self).__name__}.run")

    def spawn(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        log: Path | None = None,
    ) -> Spawned:
        raise NotImplementedError(f"{type(self).__name__}.spawn")

    def which(self, tool: str) -> Path | None:
        raise NotImplementedError(f"{type(self).__name__}.which")
