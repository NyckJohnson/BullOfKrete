"""A test rig for `LiveGates`: scripted runner, fake collaborators, a real temp app folder."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from bull.Modules.api.Contracts import ApiCheck
from bull.Modules.api.mocks import MockApiSnapshots
from bull.Modules.coverage.mocks import MockCoverageTriage
from bull.Modules.events.Contracts import Event, EventKind
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.Contracts import AppLayout, RunResult, Spawned
from bull.Modules.foundation.files import LiveFiles
from bull.Modules.foundation.mocks import MockClock, sample_layout
from bull.Modules.gates.Contracts import (
    GateMode,
    GateRequest,
    GateRun,
    PassRecord,
    StepResult,
)
from bull.Modules.gates.driver import LiveGates
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.interfaces.Contracts import InterfaceResult
from bull.Modules.interfaces.mocks import MockInterfaces
from bull.Modules.memo.Contracts import InterfaceEntry, Memo
from bull.Modules.memo.mocks import sample_memo
from bull.Modules.parts.Contracts import Part
from bull.Modules.parts.mocks import MockParts
from bull.Modules.settings.Contracts import Layer, Resolved, Setting, SettingValue
from bull.Modules.stacks.Contracts import (
    GateCommands,
    RunCommands,
    Stack,
    TestRun,
)
from bull.Modules.stacks.mocks import (
    MockStackReaders,
    MockStackRegistry,
    sample_stack,
)
from bull.Modules.status.Contracts import ModuleState, ModuleStatus, Track
from bull.Modules.status.mocks import MockRefs, MockStatusStore, sample_status

DEFAULT_RUN = TestRun(count=10, failed=())
HEAD_SHA = "a" * 40
BRANCH_SHA = "b" * 40


def make_stack(
    name: str,
    *,
    journeys: bool = True,
    run: TestRun | None = DEFAULT_RUN,
    comment: str = "#",
    service: bool = False,
) -> Stack:
    """A fixture-shaped stack whose steps are `{python} <step> ...`."""
    base = sample_stack(name)
    manifest = replace(
        base.manifest,
        comment=comment,
        gates=GateCommands(
            preflight=("{python}", "preflight"),
            setup=("{python}", "setup"),
            build_test=("{python}", "build-test"),
            build_test_fast=("{python}", "build-test-fast", "{module}"),
            lint=("{python}", "lint", "{module}"),
            rerun_failed=("{python}", "rerun", "{failed_ids}"),
            journeys=("{python}", "journeys") if journeys else None,
        ),
        run=RunCommands(
            ("{python}", "start"), ("{python}", "ready"), ("{python}", "stop"), 5.0
        )
        if service
        else None,
    )
    readers = MockStackReaders()
    readers.run = run
    return replace(base, manifest=manifest, readers=readers)


class FakeRunner:
    """Scripted gate steps, keyed by the step word (`argv[1]`) and optionally the part."""

    def __init__(self) -> None:
        self.script: dict[tuple[str, str | None], RunResult] = {}
        self.root_names: dict[Path, str] = {}
        self.calls: list[tuple[tuple[str, ...], Path, Mapping[str, str] | None]] = []
        self.on_run: Callable[[str], None] | None = None

    def set(
        self,
        step: str,
        *,
        part: str | None = None,
        code: int = 0,
        stdout: str = "",
        stderr: str = "",
        seconds: float = 0.5,
    ) -> None:
        self.script[(step, part)] = RunResult(
            argv=(), returncode=code, stdout=stdout, stderr=stderr, seconds=seconds
        )

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        self.calls.append((tuple(argv), cwd, env))
        step = argv[1] if len(argv) > 1 else ""
        part = self.root_names.get(cwd)
        if self.on_run is not None:
            self.on_run(step)
        found = self.script.get((step, part)) or self.script.get((step, None))
        if found is None:
            return RunResult(tuple(argv), 0, "", "", 0.5)
        return replace(found, argv=tuple(argv))

    def spawn(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        log: Path | None = None,
    ) -> Spawned:
        raise AssertionError("the driver must not spawn processes itself")

    def which(self, tool: str) -> Path | None:
        return None

    def steps(self, part: str | None = None) -> list[str]:
        """The step words run, in order (optionally only those run in `part`)."""
        return [
            argv[1]
            for argv, cwd, _ in self.calls
            if part is None or self.root_names.get(cwd) == part
        ]

    def envs(self, step: str) -> list[Mapping[str, str]]:
        return [env or {} for argv, _, env in self.calls if argv[1] == step]


class FakePasses:
    def __init__(self) -> None:
        self.records: dict[str, PassRecord] = {}
        self.recorded: list[tuple[str, str | None, str, tuple[str, ...]]] = []

    def record(
        self,
        app: AppLayout,
        sha: str,
        branch: str | None,
        command: str,
        parts: Sequence[str],
    ) -> None:
        self.recorded.append((sha, branch, command, tuple(parts)))

    def get(self, app: AppLayout, sha: str) -> PassRecord | None:
        return self.records.get(sha)


class FakeSettings:
    """Settings answering `coverage.*` and `bookkeeping_paths`; `show` names its part."""

    def __init__(self) -> None:
        self.values: dict[str, SettingValue] = {
            "coverage.exclude": ("*/mocks/*",),
            "coverage.exclude_extra": (),
            "bookkeeping_paths": (".bull/", "docs/"),
        }
        self.part_values: dict[tuple[str, str | None], SettingValue] = {}
        self.calls: list[tuple[str, str | None]] = []

    def get(self, key: str, part: str | None = None) -> SettingValue:
        self.calls.append((key, part))
        return self.part_values.get((key, part), self.values[key])

    def show(self, part: str | None = None) -> list[Resolved]:
        self.calls.append(("show", part))
        return [Resolved("marker", str(part), Layer.APP, None)]

    def schema(self) -> list[Setting]:
        return []

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        raise NotImplementedError


class ScriptedApi(MockApiSnapshots):
    """`check`/`check_interface` answers per name; default passing."""

    def __init__(self) -> None:
        super().__init__()
        self.module_checks: dict[str, ApiCheck] = {}
        self.interface_checks: dict[str, ApiCheck] = {}

    def check(self, app: AppLayout, module: str) -> ApiCheck:
        self.calls.append(("check", (app, module)))
        return self.module_checks.get(module, ApiCheck(module, True, True, ""))

    def check_interface(self, app: AppLayout, name: str) -> ApiCheck:
        self.calls.append(("check_interface", (app, name)))
        return self.interface_checks.get(name, ApiCheck(name, True, True, ""))


class ScriptedInterfaces(MockInterfaces):
    def __init__(self) -> None:
        super().__init__()
        self.module_results: dict[str, list[InterfaceResult]] = {}

    def check_module(
        self, app: AppLayout, memo: Memo, module: str
    ) -> list[InterfaceResult]:
        self.calls.append(("check_module", (app, memo, module)))
        return list(self.module_results.get(module, []))


class FakeJourneys:
    """Stands in for the journey runner; records each call, returns a scripted result."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.verdicts: dict[str, str] = {}

    def run(
        self,
        part: Part,
        stack: Stack,
        env: Mapping[str, str],
        values: Mapping[str, str],
        results: Path,
        providers: Sequence[object],
        adopt: bool,
    ) -> StepResult:
        from bull.Modules.gates.Contracts import Gate, Verdict

        self.calls.append(
            {
                "part": part,
                "stack": stack,
                "env": dict(env),
                "values": dict(values),
                "results": results,
                "providers": list(providers),
                "adopt": adopt,
            }
        )
        failed = self.verdicts.get(part.name) == "fail"
        return StepResult(
            gate=Gate.JOURNEYS,
            part=part.name,
            module=None,
            verdict=Verdict.FAIL if failed else Verdict.PASS,
            labels=("journey broke",) if failed else (),
            seconds=1.0,
            output_tail="",
        )

    def parts(self) -> list[str]:
        return [str(c["part"].name) for c in self.calls]  # type: ignore[attr-defined]


@dataclass
class Rig:
    app: AppLayout
    root: Path
    files: LiveFiles
    git: MockGit
    runner: FakeRunner
    events: MockEventLog
    clock: MockClock
    registry: MockStackRegistry
    parts: MockParts
    triage: MockCoverageTriage
    api: ScriptedApi
    passes: FakePasses
    journeys: FakeJourneys
    settings: FakeSettings
    store: MockStatusStore
    interfaces: ScriptedInterfaces
    memo: Memo
    gates: LiveGates
    environ: dict[str, str] = field(default_factory=dict)

    def run(
        self,
        mode: GateMode,
        module: str | None = None,
        *,
        branch: str | None = None,
        skip_coverage: bool = False,
    ) -> GateRun:
        return self.gates.run(
            self.app, GateRequest(mode, module, branch, skip_coverage)
        )

    def results(self, part: str) -> Path:
        return self.app.results_dir / part

    def gate_events(self) -> list[Event]:
        return [e for e in self.events.events if e.kind is EventKind.GATE_STEP]


def make_rig(
    tmp_path: Path,
    *,
    parts: Sequence[tuple[str, Stack]] | None = None,
    modules: Sequence[tuple[str, str]] = (("Counter", "app"),),
    explicit_parts: bool = False,
    adoption_stage: int | None = None,
    interface_entries: Sequence[InterfaceEntry] = (),
    environ: Mapping[str, str] | None = None,
) -> Rig:
    """An app in `tmp_path`.

    `parts` are (name, stack); one part named `app` is the implicit part unless
    `explicit_parts` (each part then gets `.bull/parts/<name>.toml` and its own folder).
    `modules` are (name, part-name) in build order; a part named "app" with implicit parts
    is recorded in status as "" (the implicit part).
    """
    app = sample_layout(tmp_path)
    stacks = list(parts) if parts is not None else [("app", make_stack("fixture"))]
    registry = MockStackRegistry()
    registry.stacks = {}
    part_objs: list[Part] = []
    runner = FakeRunner()
    for name, stack in stacks:
        registry.stacks[stack.manifest.name] = stack
        root = tmp_path / name if explicit_parts else tmp_path
        root.mkdir(parents=True, exist_ok=True)
        if explicit_parts:
            app.parts_dir.mkdir(parents=True, exist_ok=True)
            (app.parts_dir / f"{name}.toml").write_text("format = 1\n")
        part_objs.append(
            Part(
                name=name,
                stack=stack.manifest.name,
                dir=name if explicit_parts else ".",
                root=root,
                source_dir=Path("src"),
                test_dir=Path("tests"),
            )
        )
        runner.root_names[root] = name
    mock_parts = MockParts()
    mock_parts.parts = part_objs

    base = sample_status()
    status = replace(
        base,
        modules=tuple(
            ModuleStatus(
                name=name,
                part="" if (part == "app" and not explicit_parts) else part,
                depends=(),
                state=ModuleState.DONE,
                units=(),
                reference_tests=False,
                scan=None,
            )
            for name, part in modules
        ),
        adoption=Track(adoption_stage, ()) if adoption_stage is not None else None,
    )
    store = MockStatusStore(status)
    memo = replace(sample_memo(), interfaces=tuple(interface_entries))
    git = MockGit()
    git.heads = {"HEAD": HEAD_SHA, "main": HEAD_SHA}
    events = MockEventLog()
    clock = MockClock(datetime(2026, 11, 11, tzinfo=UTC))
    triage = MockCoverageTriage()
    api = ScriptedApi()
    passes = FakePasses()
    journeys = FakeJourneys()
    settings = FakeSettings()
    interfaces = ScriptedInterfaces()
    env = dict(environ) if environ is not None else {"INHERITED": "yes"}
    files = LiveFiles()
    gates = LiveGates(
        files=files,
        git=git,
        runner=runner,
        events=events,
        clock=clock,
        stacks=registry,
        parts=mock_parts,
        triage=triage,
        api=api,
        passes=passes,
        journeys=cast(Any, journeys),
        settings=lambda _app: settings,
        store=lambda _app: store,
        refs=lambda _app: MockRefs(),
        memo=lambda _app: memo,
        interfaces=lambda _app: interfaces,
        python="PY",
        environ=env,
    )
    return Rig(
        app=app,
        root=tmp_path,
        files=files,
        git=git,
        runner=runner,
        events=events,
        clock=clock,
        registry=registry,
        parts=mock_parts,
        triage=triage,
        api=api,
        passes=passes,
        journeys=cast(Any, journeys),
        settings=settings,
        store=store,
        interfaces=interfaces,
        memo=memo,
        gates=gates,
        environ=env,
    )


def shape(run: GateRun) -> list[str]:
    """Each step as `gate:part[:module]` (module only for the per-module gates)."""
    per_module = {"lint", "api", "coverage", "interface"}
    out: list[str] = []
    for step in run.steps:
        text = f"{step.gate.value}:{step.part}"
        if step.gate.value in per_module and step.module:
            text += f":{step.module}"
        out.append(text)
    return out


def status_of(run: GateRun, gate: str, part: str | None = None) -> StepResult:
    for step in run.steps:
        if step.gate.value == gate and (part is None or step.part == part):
            return step
    raise AssertionError(f"no {gate} step for {part} in {shape(run)}")


__all__ = [
    "BRANCH_SHA",
    "HEAD_SHA",
    "FakeJourneys",
    "FakePasses",
    "FakeRunner",
    "FakeSettings",
    "Rig",
    "ScriptedApi",
    "ScriptedInterfaces",
    "make_rig",
    "make_stack",
    "shape",
    "status_of",
]
