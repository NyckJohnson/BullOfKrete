"""Journeys of a part, with service parts started and stopped."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from bull.Modules.foundation.Contracts import Clock, Runner
from bull.Modules.gates.Contracts import StepResult
from bull.Modules.gates.steps import LiveSteps
from bull.Modules.parts.Contracts import Part
from bull.Modules.stacks.Contracts import Stack


@dataclass(frozen=True)
class Provider:
    """A service part to start before a part's journeys, with its step env and values."""

    part: Part
    stack: Stack
    env: Mapping[str, str]
    values: Mapping[str, str]
    results: Path


def _free_port() -> int:
    """A port on 127.0.0.1 that was free a moment ago."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


class JourneyRunner:
    """Runs a part's journey tests with its provider parts running."""

    def __init__(
        self,
        runner: Runner,
        steps: LiveSteps,
        clock: Clock,
        sleep: Callable[[float], None] = time.sleep,
        free_port: Callable[[], int] = _free_port,
    ) -> None:
        self._runner = runner
        self._steps = steps
        self._clock = clock
        self._sleep = sleep
        self._free_port = free_port

    def run(
        self,
        part: Part,
        stack: Stack,
        env: Mapping[str, str],
        values: Mapping[str, str],
        results: Path,
        providers: Sequence[Provider],
        adopt: bool,
    ) -> StepResult:
        raise NotImplementedError(f"{type(self).__name__}.run")
