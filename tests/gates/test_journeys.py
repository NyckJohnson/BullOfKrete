"""Tests for `bull.Modules.gates.journeys`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bull.Modules.events.Contracts import EventKind
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.Contracts import RunResult, Spawned
from bull.Modules.foundation.files import LiveFiles
from bull.Modules.foundation.mocks import MockClock
from bull.Modules.gates.Contracts import Gate, Verdict
from bull.Modules.gates.journeys import JourneyRunner, Provider
from bull.Modules.gates.steps import LiveSteps
from bull.Modules.parts.Contracts import Part
from bull.Modules.parts.mocks import sample_part
from bull.Modules.stacks.Contracts import RunCommands, Stack

from .rig import make_stack

START = datetime(2026, 11, 11, tzinfo=UTC)


class _Proc:
    def __init__(self, name: str, log: list[str], pid: int) -> None:
        self.name = name
        self.pid = pid
        self._log = log
        self.stops: list[float] = []

    def alive(self) -> bool:
        return True

    def stop(self, grace: float = 5.0) -> None:
        self.stops.append(grace)
        self._log.append(f"proc-stop:{self.name}")


class _Runner:
    """Scripted runner: argv[0] names the part (via the `python` value), argv[1] the step."""

    def __init__(self, clock: MockClock) -> None:
        self.clock = clock
        self.log: list[str] = []
        self.calls: list[tuple[tuple[str, ...], Path, Mapping[str, str] | None]] = []
        self.spawns: list[
            tuple[tuple[str, ...], Path, Mapping[str, str] | None, Path | None]
        ] = []
        self.procs: list[_Proc] = []
        self.ready_codes: dict[str, list[int]] = {}
        self.ready_cost = 0.0
        self.journeys_code = 0
        self.journeys_stdout = ""
        self.journeys_raises = False
        self.stop_raises = False

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        self.calls.append((tuple(argv), cwd, env))
        who, step = argv[0], argv[1]
        self.log.append(f"{step}:{who}" if step != "journeys" else "journeys")
        code = 0
        stdout = ""
        if step == "ready":
            self.clock.time += timedelta(seconds=self.ready_cost)
            codes = self.ready_codes.get(who, [0])
            code = codes.pop(0) if len(codes) > 1 else codes[0]
        elif step == "stop" and self.stop_raises:
            raise OSError("stop command broke")
        elif step == "journeys":
            if self.journeys_raises:
                raise RuntimeError("journeys blew up")
            code = self.journeys_code
            stdout = self.journeys_stdout
        return RunResult(tuple(argv), code, stdout, "", 0.25)

    def spawn(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        log: Path | None = None,
    ) -> Spawned:
        self.spawns.append((tuple(argv), cwd, env, log))
        self.log.append(f"spawn:{argv[0]}")
        proc = _Proc(argv[0], self.log, 100 + len(self.procs))
        self.procs.append(proc)
        return proc

    def which(self, tool: str) -> Path | None:
        return None

    def steps_of(self, step: str) -> list[tuple[str, ...]]:
        return [argv for argv, _, _ in self.calls if argv[1] == step]


class _Harness:
    def __init__(self, tmp_path: Path, ports: Sequence[int] = (5001, 5002, 5003)):
        self.tmp = tmp_path
        self.clock = MockClock(START)
        self.runner = _Runner(self.clock)
        self.events = MockEventLog()
        self.sleeps: list[float] = []
        self._ports = list(ports)
        steps = LiveSteps(self.runner, self.events, LiveFiles())
        self.jr = JourneyRunner(
            self.runner,
            steps,
            self.clock,
            sleep=self._sleep,
            free_port=lambda: self._ports.pop(0),
        )
        self.results = tmp_path / "results" / "cli"
        self.results.mkdir(parents=True)
        self.part: Part = sample_part(tmp_path / "cli", "cli")
        self.stack: Stack = make_stack("clistack")
        self.values = {"python": "PY"}
        self.env = {"BASE": "1", "BULL_PART": "cli"}

    def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock.time += timedelta(seconds=seconds)

    def provider(self, name: str, timeout: float = 3.0) -> Provider:
        stack = make_stack(f"{name}stack", service=True)
        assert stack.manifest.run is not None
        stack = replace(
            stack,
            manifest=replace(
                stack.manifest,
                run=RunCommands(
                    ("{python}", "start", "{port}"),
                    ("{python}", "ready", "{port}"),
                    ("{python}", "stop", "{port}"),
                    timeout,
                ),
            ),
        )
        root = self.tmp / name
        root.mkdir(exist_ok=True)
        results = self.tmp / "results" / name
        results.mkdir(parents=True, exist_ok=True)
        return Provider(
            part=sample_part(root, name),
            stack=stack,
            env={"PROVIDER": name},
            values={"python": f"P-{name}"},
            results=results,
        )

    def run(self, providers: Sequence[Provider] = ()) -> object:
        return self.jr.run(
            self.part,
            self.stack,
            self.env,
            self.values,
            self.results,
            providers,
            False,
        )


def test_without_providers_only_the_journeys_step_runs(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    result = h.run()
    assert h.runner.spawns == []
    assert h.runner.log == ["journeys"]
    assert result.verdict is Verdict.PASS  # type: ignore[attr-defined]


def test_journeys_step_belongs_to_the_part_without_a_module(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    result = h.run()
    assert result.gate is Gate.JOURNEYS  # type: ignore[attr-defined]
    assert result.part == "cli"  # type: ignore[attr-defined]
    assert result.module is None  # type: ignore[attr-defined]


def test_journeys_run_with_filled_argv_in_the_part_folder(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.run()
    argv, cwd, env = h.runner.calls[0]
    assert argv == ("PY", "journeys")
    assert cwd == h.part.root
    assert env is not None and env["BASE"] == "1"


def test_failing_journeys_give_a_failed_step_with_its_labels(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.runner.journeys_code = 1
    h.runner.journeys_stdout = "bull-fail: checkout flow\n"
    result = h.run()
    assert result.verdict is Verdict.FAIL  # type: ignore[attr-defined]
    assert result.labels == ("checkout flow",)  # type: ignore[attr-defined]


def test_journeys_step_is_reported_as_a_gate_step_event(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.run()
    events = [e for e in h.events.events if e.kind is EventKind.GATE_STEP]
    assert [e.data["gate"] for e in events] == ["journeys"]
    assert events[0].data["part"] == "cli"


def test_provider_is_spawned_on_a_free_port_with_filled_start_argv(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path)
    web = h.provider("web")
    h.run([web])
    argv, cwd, env, log = h.runner.spawns[0]
    assert argv == ("P-web", "start", "5001")
    assert cwd == web.part.root
    assert env == {"PROVIDER": "web"}
    assert log is not None and log.name == "run.log"


def test_providers_start_in_order_each_on_its_own_port(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.run([h.provider("web"), h.provider("api")])
    assert [s[0] for s in h.runner.spawns] == [
        ("P-web", "start", "5001"),
        ("P-api", "start", "5002"),
    ]


def test_ready_is_polled_with_the_providers_port(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.run([h.provider("web")])
    assert h.runner.steps_of("ready") == [("P-web", "ready", "5001")]


def test_ready_is_polled_every_half_second_until_it_exits_zero(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path)
    h.runner.ready_codes["P-web"] = [1, 1, 0]
    result = h.run([h.provider("web")])
    assert len(h.runner.steps_of("ready")) == 3
    assert 2 <= len(h.sleeps) <= 3
    assert set(h.sleeps) == {0.5}
    assert result.verdict is Verdict.PASS  # type: ignore[attr-defined]


def test_a_provider_is_ready_before_the_next_one_starts(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.run([h.provider("web"), h.provider("api")])
    assert h.runner.log[:5] == [
        "spawn:P-web",
        "ready:P-web",
        "spawn:P-api",
        "ready:P-api",
        "journeys",
    ]


def test_a_provider_that_never_gets_ready_fails_the_journeys_step(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path)
    h.runner.ready_codes["P-web"] = [1]
    result = h.run([h.provider("web", timeout=2.0)])
    assert result.verdict is Verdict.FAIL  # type: ignore[attr-defined]
    assert result.gate is Gate.JOURNEYS  # type: ignore[attr-defined]
    assert result.labels == ("web not ready",)  # type: ignore[attr-defined]
    assert result.part == "cli"  # type: ignore[attr-defined]
    assert h.runner.steps_of("journeys") == []
    assert set(h.sleeps) == {0.5}
    assert len(h.sleeps) <= 6


def test_ready_timeout_is_measured_with_the_clock_not_by_counting_polls(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path)
    h.runner.ready_codes["P-web"] = [1]
    h.runner.ready_cost = 10.0
    result = h.run([h.provider("web", timeout=3.0)])
    assert result.labels == ("web not ready",)  # type: ignore[attr-defined]
    assert len(h.runner.steps_of("ready")) <= 2


def test_not_ready_provider_is_still_stopped_and_earlier_ones_too(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path)
    h.runner.ready_codes["P-api"] = [1]
    h.run([h.provider("web"), h.provider("api", timeout=1.0)])
    stops = [e for e in h.runner.log if e.startswith("stop:")]
    assert stops == ["stop:P-api", "stop:P-web"]
    assert [p.stops for p in h.runner.procs] == [[5.0], [5.0]]


def test_journeys_get_a_url_per_running_provider(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.run([h.provider("web"), h.provider("api")])
    journeys_calls = [c for c in h.runner.calls if c[0] == ("PY", "journeys")]
    assert len(journeys_calls) == 1
    env = journeys_calls[0][2]
    assert env is not None
    assert env["BULL_URL_WEB"] == "http://127.0.0.1:5001"
    assert env["BULL_URL_API"] == "http://127.0.0.1:5002"
    assert env["BASE"] == "1"


def test_the_callers_env_is_not_modified(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.run([h.provider("web")])
    assert h.env == {"BASE": "1", "BULL_PART": "cli"}


def test_providers_are_stopped_in_reverse_order_after_the_journeys(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path)
    h.run([h.provider("web"), h.provider("api")])
    assert h.runner.log[4:] == [
        "journeys",
        "stop:P-api",
        "proc-stop:P-api",
        "stop:P-web",
        "proc-stop:P-web",
    ]
    assert h.runner.steps_of("stop") == [
        ("P-api", "stop", "5002"),
        ("P-web", "stop", "5001"),
    ]
    assert all(p.stops == [5.0] for p in h.runner.procs)


def test_providers_are_stopped_when_the_journeys_fail(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.runner.journeys_code = 1
    result = h.run([h.provider("web")])
    assert result.verdict is Verdict.FAIL  # type: ignore[attr-defined]
    assert h.runner.steps_of("stop") == [("P-web", "stop", "5001")]
    assert h.runner.procs[0].stops == [5.0]


def test_providers_are_stopped_when_the_journeys_raise(tmp_path: Path) -> None:
    h = _Harness(tmp_path)
    h.runner.journeys_raises = True
    with pytest.raises(RuntimeError, match="journeys blew up"):
        h.run([h.provider("web"), h.provider("api")])
    assert h.runner.steps_of("stop") == [
        ("P-api", "stop", "5002"),
        ("P-web", "stop", "5001"),
    ]
    assert [p.stops for p in h.runner.procs] == [[5.0], [5.0]]


def test_a_failing_stop_command_is_ignored_and_the_process_is_still_stopped(
    tmp_path: Path,
) -> None:
    h = _Harness(tmp_path)
    h.runner.stop_raises = True
    result = h.run([h.provider("web"), h.provider("api")])
    assert result.verdict is Verdict.PASS  # type: ignore[attr-defined]
    assert [p.stops for p in h.runner.procs] == [[5.0], [5.0]]
