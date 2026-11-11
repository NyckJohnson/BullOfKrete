"""Journeys of a part, with service parts started and stopped."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from bull.Modules.foundation.Contracts import BullError, Clock, Runner, Spawned
from bull.Modules.gates.Contracts import Gate, StepResult, Verdict
from bull.Modules.gates.steps import LiveSteps, fill
from bull.Modules.parts.Contracts import Part
from bull.Modules.stacks.Contracts import RunCommands, Stack

_POLL_SECONDS = 0.5
_STOP_GRACE = 5.0
_HOST = "127.0.0.1"


@dataclass(frozen=True)
class Provider:
    """A service part to start before a part's journeys, with its step env and values."""

    part: Part
    stack: Stack
    env: Mapping[str, str]
    values: Mapping[str, str]
    results: Path


@dataclass(frozen=True)
class _Started:
    """A provider whose `start` command was spawned, with what is needed to stop it."""

    provider: Provider
    commands: RunCommands
    values: Mapping[str, str]
    port: int
    process: Spawned


def _free_port() -> int:
    """A port on 127.0.0.1 that was free a moment ago."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_HOST, 0))
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
        """Start `providers` in order, run the part's `journeys` step, then stop them all.

        A provider that is not ready within its `ready_timeout` fails the step with
        "<provider> not ready" and the journeys are not run. Started providers are
        always stopped (reverse order), also when the journeys fail or raise.
        Raises `BullError` when the stack has no `journeys` step or a provider's
        stack has no `[run]` commands.
        """
        argv = stack.manifest.gates.journeys
        if argv is None:
            raise BullError(f"stack {stack.manifest.name} has no journeys step")
        start = self._clock.now()
        started: list[_Started] = []
        try:
            urls: dict[str, str] = {}
            for provider in providers:
                one = self._start(provider)
                started.append(one)
                if not self._wait_ready(one):
                    return self._steps.result(
                        Gate.JOURNEYS,
                        part.name,
                        None,
                        Verdict.FAIL,
                        (f"{provider.part.name} not ready",),
                        _seconds(start, self._clock.now()),
                        "",
                    )
                key = f"BULL_URL_{provider.part.name.upper()}"
                urls[key] = f"http://{_HOST}:{one.port}"
            output = self._steps.execute(
                "journeys",
                fill(argv, values),
                part.root,
                {**env, **urls},
                results,
            )
            verdict = Verdict.PASS if output.exit == 0 else Verdict.FAIL
            return self._steps.result(
                Gate.JOURNEYS,
                part.name,
                None,
                verdict,
                output.labels,
                output.seconds,
                output.tail,
            )
        finally:
            for one in reversed(started):
                self._stop(one)

    def _start(self, provider: Provider) -> _Started:
        """Spawn the provider's `start` command on a free port."""
        commands = provider.stack.manifest.run
        if commands is None:
            raise BullError(
                f"part {provider.part.name} has no [run] commands",
                f"its stack {provider.stack.manifest.name} can't be started for journeys",
            )
        port = self._free_port()
        values = {**provider.values, "port": str(port)}
        process = self._runner.spawn(
            fill(commands.start, values),
            provider.part.root,
            provider.env,
            provider.results / "run.log",
        )
        return _Started(provider, commands, values, port, process)

    def _wait_ready(self, one: _Started) -> bool:
        """Poll `ready` every 0.5 s until it exits 0 (True) or the timeout passes (False)."""
        deadline = self._clock.now() + timedelta(seconds=one.commands.ready_timeout)
        argv = fill(one.commands.ready, one.values)
        while True:
            check = self._runner.run(argv, one.provider.part.root, one.provider.env)
            if check.returncode == 0:
                return True
            if self._clock.now() > deadline:
                return False
            self._sleep(_POLL_SECONDS)

    def _stop(self, one: _Started) -> None:
        """Run the provider's `stop` command (its errors ignored), then stop the process."""
        try:
            self._runner.run(
                fill(one.commands.stop, one.values),
                one.provider.part.root,
                one.provider.env,
            )
        except (OSError, BullError):
            pass  # the spawned process is stopped below either way
        finally:
            one.process.stop(_STOP_GRACE)


def _seconds(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds()
