"""The gate driver: runs the steps of each mode and decides the verdict."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bull.Modules.api.Contracts import ApiSnapshots
from bull.Modules.coverage.Contracts import CoverageReport, CoverageTriage
from bull.Modules.events.Contracts import EventLog
from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    Clock,
    Files,
    Runner,
)
from bull.Modules.gates import report
from bull.Modules.gates.after_merge import after_merge_skip
from bull.Modules.gates.Contracts import (
    Gate,
    GateMode,
    GateRequest,
    GateRun,
    Gates,
    PassRecords,
    StepResult,
    Verdict,
)
from bull.Modules.gates.failed import read_failed, write_failed
from bull.Modules.gates.journeys import JourneyRunner, Provider
from bull.Modules.gates.steps import (
    LiveSteps,
    StepOutput,
    fill,
    settings_json,
    step_env,
)
from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.interfaces.Contracts import Interfaces
from bull.Modules.memo.Contracts import Memo
from bull.Modules.parts.Contracts import Part, Parts
from bull.Modules.settings.Contracts import Settings, SettingValue
from bull.Modules.stacks.Contracts import Stack, StackRegistry
from bull.Modules.status.Contracts import ModuleStatus, Refs, Status, StatusStore

_MODULE_MODES = frozenset({GateMode.MODULE, GateMode.FAST, GateMode.COVERAGE_REPORT})
_TAIL_LINES = 40
_ABORT_EXIT = 2


@dataclass(frozen=True)
class _PartRun:
    """One part as a run sees it: its stack, results folder and settings part argument."""

    part: Part
    stack: Stack
    results: Path
    settings_part: str | None


@dataclass
class _Tally:
    """What a run has gathered so far."""

    steps: list[StepResult] = field(default_factory=list)
    tests_run: int = 0
    failed_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    coverage: list[CoverageReport] = field(default_factory=list)

    def aborted(self) -> bool:
        return any(s.verdict is Verdict.ABORTED for s in self.steps)

    def verdict(self) -> Verdict:
        if self.aborted():
            return Verdict.ABORTED
        if any(s.verdict is Verdict.FAIL for s in self.steps):
            return Verdict.FAIL
        return Verdict.PASS


@dataclass
class _Session:
    """Per-run collaborators resolved once for `app`."""

    app: AppLayout
    status: Status
    settings: Settings
    adopting: bool
    memo_cache: list[Memo] = field(default_factory=list)


class LiveGates(Gates):
    """Runs gate steps per part, adds bull's own gates and records passes."""

    def __init__(
        self,
        files: Files,
        git: Git,
        runner: Runner,
        events: EventLog,
        clock: Clock,
        stacks: StackRegistry,
        parts: Parts,
        triage: CoverageTriage,
        api: ApiSnapshots,
        passes: PassRecords,
        journeys: JourneyRunner,
        settings: Callable[[AppLayout], Settings],
        store: Callable[[AppLayout], StatusStore],
        refs: Callable[[AppLayout], Refs],
        memo: Callable[[AppLayout], Memo],
        interfaces: Callable[[AppLayout], Interfaces],
        python: str = sys.executable,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._files = files
        self._git = git
        self._clock = clock
        self._stacks = stacks
        self._parts = parts
        self._triage = triage
        self._api = api
        self._passes = passes
        self._journeys = journeys
        self._settings = settings
        self._store = store
        self._refs = refs
        self._memo = memo
        self._interfaces = interfaces
        self._python = python
        self._environ: Mapping[str, str] = (
            environ if environ is not None else os.environ
        )
        self._steps = LiveSteps(runner, events, files)
        self._comments: dict[str, str] = {}

    # --- Gates ----------------------------------------------------------

    def run(self, app: AppLayout, request: GateRequest) -> GateRun:
        _check_request(request)
        status = self._store(app).load()
        self._check_branch(app, status)
        if request.module is not None:
            _find_module(status, request.module)
        adopting = status.adoption is not None and status.adoption.stage <= 5
        session = _Session(app, status, self._settings(app), adopting)
        mode = request.mode
        if mode is GateMode.FAILED:
            return self._run_failed(session, request)
        if mode is GateMode.JOURNEYS:
            return self._run_journeys(session, request)
        if mode is GateMode.AFTER_MERGE:
            skipped = self._after_merge(session, request)
            if skipped is not None:
                return skipped
        if request.module is not None:
            return self._run_module(session, request, request.module)
        return self._run_all(session, request)

    def coverage(self, app: AppLayout, module: str) -> CoverageReport:
        status = self._store(app).load()
        entry = _find_module(status, module)
        target = self._part_run(app, self._module_part(app, entry))
        if target.stack.readers.test_results(target.results) is None:
            raise BullError(
                f"no coverage data for {module}", f"run `bull gates {module}` first"
            )
        settings = self._settings(app)
        exclude = _str_list(
            "coverage.exclude", settings.get("coverage.exclude", target.settings_part)
        ) + _str_list(
            "coverage.exclude_extra",
            settings.get("coverage.exclude_extra", target.settings_part),
        )
        manifest = target.stack.manifest
        sources = self._triage.sources(
            self._parts.module_src(target.part, module),
            target.part.root,
            manifest.source_glob,
            exclude,
        )
        data = target.stack.readers.uncovered(target.part.root, sources, target.results)
        self._comments[module] = manifest.comment
        return self._triage.report(module, sources, data, manifest.comment)

    def render(self, run: GateRun) -> str:
        comments = {r.module: self._comments.get(r.module, "#") for r in run.coverage}
        comments.update(self._comments)
        return report.render(run, self._triage, comments)

    # --- modes ----------------------------------------------------------

    def _run_module(
        self, session: _Session, request: GateRequest, module: str
    ) -> GateRun:
        app = session.app
        mode = request.mode
        entry = _find_module(session.status, module)
        target = self._part_run(app, self._module_part(app, entry))
        record = mode is GateMode.MODULE
        clean_before = self._git.is_clean(app.root) if record else True
        self._prepare(target)
        scope = module if session.adopting else None
        env = self._env(session, target, scope)
        values = self._values(app, target, module)
        tally = _Tally()

        self._module_steps(tally, session, request, target, module, env, values)
        if not record:
            return self._finish(
                session,
                request,
                tally,
                None,
                False,
                (),
                f"not recorded: partial run ({mode.value})",
            )
        return self._finish(
            session,
            request,
            tally,
            f"gates {module}",
            clean_before,
            (target.part.name,),
            "",
        )

    def _module_steps(
        self,
        tally: _Tally,
        session: _Session,
        request: GateRequest,
        target: _PartRun,
        module: str,
        env: Mapping[str, str],
        values: Mapping[str, str],
    ) -> None:
        """MODULE, FAST and COVERAGE_REPORT steps on the module's part."""
        mode = request.mode
        gates = target.stack.manifest.gates
        self._command(
            tally,
            target,
            Gate.PREFLIGHT,
            "preflight",
            gates.preflight,
            values,
            env,
            None,
        )
        if tally.aborted():
            return
        if mode is GateMode.FAST:
            self._build_test(
                tally, target, "build_test_fast", gates.build_test_fast, values, env
            )
            self._lint_and_api(tally, session, target, module, values, env)
            return
        if not self._command(
            tally, target, Gate.SETUP, "setup", gates.setup, values, env, None
        ):
            return
        built = self._build_test(
            tally, target, "build_test", gates.build_test, values, env
        )
        self._lint_and_api(tally, session, target, module, values, env)
        if built and not request.skip_coverage:
            self._coverage_step(tally, session.app, target, module)
        if mode is GateMode.MODULE:
            self._interface_step(tally, session, target, module)
            if session.adopting:
                self._journeys_step(tally, session, target, env, values)

    def _run_all(self, session: _Session, request: GateRequest) -> GateRun:
        app = session.app
        if request.mode is GateMode.AFTER_MERGE:
            command = f"gates --after-merge {request.branch}"
        else:
            command = "gates --all"
        clean_before = self._git.is_clean(app.root)
        owners = {
            entry.name: self._module_part(app, entry).name
            for entry in session.status.modules
        }
        tally = _Tally()
        ran: list[_PartRun] = []
        journey_parts: list[tuple[_PartRun, dict[str, str], dict[str, str]]] = []
        for part in sorted(self._parts.all(app), key=lambda p: p.name):
            target = self._part_run(app, part)
            self._prepare(target)
            ran.append(target)
            env = self._env(session, target, None)
            values = self._values(app, target, None)
            gates = target.stack.manifest.gates
            self._command(
                tally,
                target,
                Gate.PREFLIGHT,
                "preflight",
                gates.preflight,
                values,
                env,
                None,
            )
            if tally.aborted():
                break
            if not self._command(
                tally, target, Gate.SETUP, "setup", gates.setup, values, env, None
            ):
                continue
            built = self._build_test(
                tally, target, "build_test", gates.build_test, values, env
            )
            for entry in session.status.modules:
                if owners[entry.name] != part.name:
                    continue
                module_values = self._values(app, target, entry.name)
                self._lint_and_api(
                    tally, session, target, entry.name, module_values, env
                )
                if built and not request.skip_coverage:
                    self._coverage_step(tally, app, target, entry.name)
                self._interface_step(tally, session, target, entry.name)
            journey_parts.append((target, env, values))

        if not tally.aborted():
            self._app_interface_step(tally, session)
            for target, env, values in journey_parts:
                self._journeys_step(tally, session, target, env, values)

        return self._finish(
            session,
            request,
            tally,
            command,
            clean_before,
            tuple(t.part.name for t in ran),
            "",
        )

    def _run_failed(self, session: _Session, request: GateRequest) -> GateRun:
        app = session.app
        tally = _Tally()
        for part in self._parts.all(app):
            results = app.results_dir / part.name
            ids = read_failed(self._files, results)
            if not ids:
                continue
            target = self._part_run(app, part)
            self._prepare(target)
            env = self._env(session, target, None)
            values = self._values(app, target, None)
            out = self._execute(
                target,
                "rerun_failed",
                target.stack.manifest.gates.rerun_failed,
                values,
                env,
                ids,
            )
            tally.tests_run += len(ids)
            if out.exit == 0:
                write_failed(self._files, results, ())
                self._add(
                    tally,
                    Gate.TESTS,
                    part.name,
                    None,
                    Verdict.PASS,
                    (),
                    out.seconds,
                    out.tail,
                )
                continue
            found = target.stack.readers.test_results(results)
            new_ids = found.failed if found is not None else ()
            labels = out.labels
            if new_ids:
                write_failed(self._files, results, new_ids)
                tally.failed_ids[part.name] = new_ids
                labels = new_ids
            self._add(
                tally,
                Gate.TESTS,
                part.name,
                None,
                Verdict.FAIL,
                labels,
                out.seconds,
                out.tail,
            )
        note = (
            "not recorded: partial run (failed)"
            if tally.steps
            else "no failed tests recorded"
        )
        return self._finish(session, request, tally, None, False, (), note)

    def _run_journeys(self, session: _Session, request: GateRequest) -> GateRun:
        app = session.app
        tally = _Tally()
        notes: list[str] = []
        for part in sorted(self._parts.all(app), key=lambda p: p.name):
            target = self._part_run(app, part)
            if target.stack.manifest.gates.journeys is None:
                notes.append(f"no journey tests: {part.name}")
                continue
            self._prepare(target)
            env = self._env(session, target, None)
            values = self._values(app, target, None)
            self._journeys_step(tally, session, target, env, values)
        notes.append(f"not recorded: partial run ({request.mode.value})")
        return self._finish(session, request, tally, None, False, (), "; ".join(notes))

    def _after_merge(self, session: _Session, request: GateRequest) -> GateRun | None:
        """The skipped run when the merge holds gated code, else None (run everything)."""
        app = session.app
        branch = request.branch
        if branch is None:  # pragma: no cover - refused by _check_request
            raise BullError("--after-merge needs a branch")
        bookkeeping = _str_list(
            "bookkeeping_paths", session.settings.get("bookkeeping_paths", None)
        )
        found = after_merge_skip(app, branch, self._git, self._passes, bookkeeping)
        if found is None:
            return None
        sha = self._head(app)
        self._passes.record(
            app,
            sha,
            self._git.current_branch(app.root),
            f"gates --after-merge {branch}",
            found.parts,
        )
        return GateRun(
            request=request,
            verdict=Verdict.PASS,
            steps=(),
            tests_run=0,
            failed_ids={},
            coverage=(),
            recorded=True,
            note="merge holds the gated code",
        )

    # --- steps ----------------------------------------------------------

    def _command(
        self,
        tally: _Tally,
        target: _PartRun,
        gate: Gate,
        step: str,
        argv: Sequence[str],
        values: Mapping[str, str],
        env: Mapping[str, str],
        module: str | None,
    ) -> bool:
        """Run a stack step and report it; True when it passed."""
        out = self._execute(target, step, argv, values, env)
        if out.exit == 0:
            verdict = Verdict.PASS
        elif gate is Gate.PREFLIGHT and out.exit == _ABORT_EXIT:
            verdict = Verdict.ABORTED
        else:
            verdict = Verdict.FAIL
        self._add(
            tally,
            gate,
            target.part.name,
            module,
            verdict,
            out.labels,
            out.seconds,
            out.tail,
        )
        return verdict is Verdict.PASS

    def _build_test(
        self,
        tally: _Tally,
        target: _PartRun,
        step: str,
        argv: Sequence[str],
        values: Mapping[str, str],
        env: Mapping[str, str],
    ) -> bool:
        """Run build_test (or build_test_fast): a BUILD then a TESTS step; True when both pass."""
        out = self._execute(target, step, argv, values, env)
        found = target.stack.readers.test_results(target.results)
        failed = found.failed if found is not None else ()
        write_failed(self._files, target.results, failed)
        if found is not None:
            tally.tests_run += found.count
        if failed:
            tally.failed_ids[target.part.name] = failed
        name = target.part.name
        built = out.exit == 0 or bool(failed)
        if built:
            self._add(tally, Gate.BUILD, name, None, Verdict.PASS, (), 0, "")
        else:
            self._add(
                tally, Gate.BUILD, name, None, Verdict.FAIL, out.labels, 0, out.tail
            )
        if found is None or found.count == 0:
            labels: tuple[str, ...] = ("no tests ran",)
        else:
            labels = failed
        tests_ok = not labels
        self._add(
            tally,
            Gate.TESTS,
            name,
            None,
            Verdict.PASS if tests_ok else Verdict.FAIL,
            labels,
            out.seconds,
            out.tail,
        )
        return built and tests_ok

    def _lint_and_api(
        self,
        tally: _Tally,
        session: _Session,
        target: _PartRun,
        module: str,
        values: Mapping[str, str],
        env: Mapping[str, str],
    ) -> None:
        gates = target.stack.manifest.gates
        self._command(tally, target, Gate.LINT, "lint", gates.lint, values, env, module)
        start = time.perf_counter()
        check = self._api.check(session.app, module)
        if check.ok:
            labels: tuple[str, ...] = ()
            tail = ""
        else:
            labels = (f"contract differs from docs/api/{module}.md",)
            tail = _tail(check.diff)
        verdict = Verdict.PASS if check.ok else Verdict.FAIL
        self._add(
            tally,
            Gate.API,
            target.part.name,
            module,
            verdict,
            labels,
            _since(start),
            tail,
        )

    def _coverage_step(
        self, tally: _Tally, app: AppLayout, target: _PartRun, module: str
    ) -> None:
        start = time.perf_counter()
        found = self.coverage(app, module)
        tally.coverage.append(found)
        labels: tuple[str, ...] = (
            () if found.clean else (f"coverage not clean for {module}",)
        )
        verdict = Verdict.FAIL if labels else Verdict.PASS
        self._add(
            tally,
            Gate.COVERAGE,
            target.part.name,
            module,
            verdict,
            labels,
            _since(start),
            "",
        )

    def _interface_step(
        self, tally: _Tally, session: _Session, target: _PartRun, module: str
    ) -> None:
        start = time.perf_counter()
        app = session.app
        results = self._interfaces(app).check_module(
            app, self._memo_of(session), module
        )
        labels = tuple(
            f"{result.interface}: {item.item} — {item.fix}"
            for result in results
            for item in result.items
            if not item.ok
        )
        verdict = Verdict.FAIL if labels else Verdict.PASS
        self._add(
            tally,
            Gate.INTERFACE,
            target.part.name,
            module,
            verdict,
            labels,
            _since(start),
            "",
        )

    def _app_interface_step(self, tally: _Tally, session: _Session) -> None:
        """ALL's app-wide check: interface snapshots and the memo's interface problems."""
        start = time.perf_counter()
        app = session.app
        memo = self._memo_of(session)
        labels: list[str] = []
        for entry in memo.interfaces:
            if not self._api.check_interface(app, entry.name).ok:
                labels.append(f"interface {entry.name} differs from its snapshot")
        labels.extend(self._interfaces(app).problems(app, memo))
        verdict = Verdict.FAIL if labels else Verdict.PASS
        self._add(tally, Gate.INTERFACE, "", None, verdict, labels, _since(start), "")

    def _journeys_step(
        self,
        tally: _Tally,
        session: _Session,
        target: _PartRun,
        env: Mapping[str, str],
        values: Mapping[str, str],
    ) -> None:
        if target.stack.manifest.gates.journeys is None:
            return
        app = session.app
        providers: list[Provider] = []
        for name in self._interfaces(app).parts_to_run(
            self._memo_of(session), target.part.name
        ):
            other = self._part_run(app, self._parts.get(app, name))
            self._prepare(other)
            providers.append(
                Provider(
                    part=other.part,
                    stack=other.stack,
                    env=self._env(session, other, None),
                    values=self._values(app, other, None),
                    results=other.results,
                )
            )
        tally.steps.append(
            self._journeys.run(
                target.part,
                target.stack,
                env,
                values,
                target.results,
                providers,
                session.adopting,
            )
        )

    # --- helpers --------------------------------------------------------

    def _finish(
        self,
        session: _Session,
        request: GateRequest,
        tally: _Tally,
        command: str | None,
        clean_before: bool,
        parts_run: Sequence[str],
        note: str,
    ) -> GateRun:
        """The run's verdict, and its pass record when `command` is given and it qualifies."""
        verdict = tally.verdict()
        recorded = False
        if command is not None:
            app = session.app
            clean_after = self._git.is_clean(app.root)
            if verdict is not Verdict.PASS:
                note = "not recorded: gates failed"
            elif request.skip_coverage:
                note = "not recorded: coverage skipped"
            elif not (clean_before and clean_after):
                note = "not recorded: working tree has changes"
            else:
                self._passes.record(
                    app,
                    self._head(app),
                    self._git.current_branch(app.root),
                    command,
                    parts_run,
                )
                recorded = True
                note = ""
        return GateRun(
            request=request,
            verdict=verdict,
            steps=tuple(tally.steps),
            tests_run=tally.tests_run,
            failed_ids=dict(tally.failed_ids),
            coverage=tuple(tally.coverage),
            recorded=recorded,
            note=note,
        )

    def _execute(
        self,
        target: _PartRun,
        step: str,
        argv: Sequence[str],
        values: Mapping[str, str],
        env: Mapping[str, str],
        failed_ids: Sequence[str] = (),
    ) -> StepOutput:
        return self._steps.execute(
            step, fill(argv, values, failed_ids), target.part.root, env, target.results
        )

    def _add(
        self,
        tally: _Tally,
        gate: Gate,
        part: str,
        module: str | None,
        verdict: Verdict,
        labels: Sequence[str],
        seconds: float,
        tail: str,
    ) -> None:
        tally.steps.append(
            self._steps.result(gate, part, module, verdict, labels, seconds, tail)
        )

    def _check_branch(self, app: AppLayout, status: Status) -> None:
        """Refuse to run on a module branch whose module isn't in status."""
        branch = self._git.current_branch(app.root)
        if branch is None:
            return
        module = self._refs(app).module_for_branch(branch)
        if module is None or any(m.name == module for m in status.modules):
            return
        raise BullError(
            f"branch {branch} is for module {module}, which is not in status",
            "run `bull status init-modules` or switch branch",
        )

    def _module_part(self, app: AppLayout, entry: ModuleStatus) -> Part:
        return self._parts.get(app, entry.part or None)

    def _part_run(self, app: AppLayout, part: Part) -> _PartRun:
        has_file = (app.parts_dir / f"{part.name}.toml").is_file()
        return _PartRun(
            part=part,
            stack=self._stacks.get(part.stack),
            results=app.results_dir / part.name,
            settings_part=part.name if has_file else None,
        )

    @staticmethod
    def _prepare(target: _PartRun) -> None:
        target.results.mkdir(parents=True, exist_ok=True)

    def _env(
        self, session: _Session, target: _PartRun, scope: str | None
    ) -> dict[str, str]:
        return step_env(
            self._environ,
            session.app,
            target.part,
            target.stack,
            target.results,
            settings_json(session.settings, target.settings_part),
            session.adopting,
            scope,
        )

    def _values(
        self, app: AppLayout, target: _PartRun, module: str | None
    ) -> dict[str, str]:
        part = target.part
        return {
            "python": self._python,
            "stack_dir": str(target.stack.home),
            "app_root": str(app.root.absolute()),
            "part_root": str(part.root.absolute()),
            "results": str(target.results.absolute()),
            "module": module or "",
            "module_src": str(self._parts.module_src(part, module).absolute())
            if module
            else "",
            "module_tests": str(self._parts.module_tests(part, module).absolute())
            if module
            else "",
        }

    def _memo_of(self, session: _Session) -> Memo:
        if not session.memo_cache:
            session.memo_cache.append(self._memo(session.app))
        return session.memo_cache[0]

    def _head(self, app: AppLayout) -> str:
        sha = self._git.head(app.root, "HEAD")
        if sha is None:
            raise BullError("no commit at HEAD", "commit before recording a gate pass")
        return sha


def _check_request(request: GateRequest) -> None:
    """Refuse requests whose module or branch doesn't fit the mode."""
    mode = request.mode
    if mode in _MODULE_MODES:
        if request.module is None:
            raise BullError(
                f"gates {mode.value} needs a module", "run `bull gates <Module>`"
            )
    elif request.module is not None:
        raise BullError(
            f"gates --{mode.value} takes no module", f"run `bull gates --{mode.value}`"
        )
    if mode is GateMode.AFTER_MERGE and request.branch is None:
        raise BullError(
            "gates --after-merge needs a branch",
            "run `bull gates --after-merge <branch>`",
        )


def _find_module(status: Status, name: str) -> ModuleStatus:
    for entry in status.modules:
        if entry.name == name:
            return entry
    names = [entry.name for entry in status.modules]
    match = next((n for n in names if n.lower() == name.lower()), None)
    if match is not None:
        fix = f"did you mean {match}?"
    elif names:
        fix = "modules: " + ", ".join(names)
    else:
        fix = "this app has no modules yet"
    raise BullError(f"unknown module {name}", fix)


def _str_list(key: str, value: SettingValue) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, str):
        return (value,) if value else ()
    raise BullError(f"setting {key} must be a list of strings")


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-_TAIL_LINES:])


def _since(start: float) -> float:
    return time.perf_counter() - start
