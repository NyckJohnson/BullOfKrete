"""Runs a stack's self-test: the static check and the cases against its fixture.

`LiveStackTester.run` builds, for every case, a fresh app folder from the stack's
`fixture/` (per `cases.json`'s `layout`), writes the `.bull/` files `bull init`
would, commits, applies the case's `change`, runs `bull <run…> --json` as a
subprocess, and compares bull's JSON output with the case's `expect`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from bull.Modules.stacks.Contracts import Stack, StackError
from bull.Modules.stacktest import static as _static
from bull.Modules.stacktest.cases import load_cases
from bull.Modules.stacktest.Contracts import (
    Case,
    CaseResult,
    CaseVerdict,
    StackTester,
    StackTestReport,
)

_MACHINE_LOCAL_IGNORES = (
    ".bull/usage.json",
    ".bull/events.jsonl",
    ".bull/passes/",
    ".bull/results/",
    ".bull/plugin/",
    ".bull/run/",
)
_CHECKPOINTS = ("outline-approved", "setup", "skeleton", "ui-approved")
_FAILING_STEP = ("fail", "aborted")
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "bull stack test",
    "GIT_AUTHOR_EMAIL": "stack-test@bull.invalid",
    "GIT_COMMITTER_NAME": "bull stack test",
    "GIT_COMMITTER_EMAIL": "stack-test@bull.invalid",
}
# Variables that point git at some other repository (`git rev-parse
# --local-env-vars`, plus the work tree and discovery settings). Left in the
# child env they would make git, and bull's own git calls, act on the caller's
# repo instead of the throwaway app folder.
_GIT_LOCATION_VARS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_GRAFT_FILE",
        "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_SHALLOW_FILE",
        "GIT_QUARANTINE_PATH",
        "GIT_INTERNAL_SUPER_PREFIX",
    }
)


class _ChangeDoesNotApply(Exception):
    """A `replace`/`delete` path of a case's change does not exist."""


class _SetupFailed(Exception):
    """Building the case's app folder (copy, `.bull/`, git) failed."""


class LiveStackTester(StackTester):
    """The real stack tester; `bull` is the command that runs bull (argv prefix)."""

    def __init__(self, bull: tuple[str, ...]) -> None:
        self._bull = tuple(bull)

    def load_cases(self, stack: Stack) -> list[Case]:
        return load_cases(stack)

    def static(self, stack: Stack) -> StackTestReport:
        return _static.static(stack)

    def run(self, stack: Stack, case: str | None = None) -> StackTestReport:
        """Run the stack's cases (or only `case` and its `then`) against its fixture.

        Raises:
            StackError: `cases.json` is malformed, or `case` names no case.
        """
        cases = load_cases(stack)
        if case is not None:
            cases = [c for c in cases if c.id == case]
            if not cases:
                raise StackError(
                    f"{stack.manifest.name}: no case `{case}` in cases.json"
                )
        layout, settings = _layout_and_settings(stack)

        reason = _not_run_reason(stack, layout)
        if reason is not None:
            results = tuple(
                CaseResult(link.id, CaseVerdict.NOT_RUN, "", reason)
                for each in cases
                for link in _chain(each)
            )
            return StackTestReport(stack.manifest.name, False, (), results)

        collected: list[CaseResult] = []
        for each in cases:
            collected.extend(self._run_case(stack, each, layout, settings))
        return StackTestReport(stack.manifest.name, False, (), tuple(collected))

    def render(self, report: StackTestReport) -> str:
        kind = "static check" if report.static else "stack test"
        lines = [f"{kind} {report.stack}"]
        for result in report.cases:
            lines.append(f"  {result.verdict.value:8} {result.id}")
            if result.verdict is CaseVerdict.FAIL:
                lines.append(f"    expected: {result.expected}")
                lines.append(f"    got:      {result.got}")
            elif result.verdict is CaseVerdict.NOT_RUN and result.got:
                lines.append(f"    {result.got}")
        lines.extend(f"  problem: {problem}" for problem in report.problems)
        lines.append("ok" if report.ok else "FAILED")
        verdicts = [result.verdict for result in report.cases]
        lines.append(
            f"{verdicts.count(CaseVerdict.PASS)} passed, "
            f"{verdicts.count(CaseVerdict.FAIL)} failed, "
            f"{verdicts.count(CaseVerdict.NOT_RUN)} not run"
        )
        return "\n".join(lines) + "\n"

    # --- one case ---------------------------------------------------------------

    def _run_case(
        self,
        stack: Stack,
        case: Case,
        layout: Mapping[str, str],
        settings: Mapping[str, object],
    ) -> list[CaseResult]:
        with tempfile.TemporaryDirectory(prefix="bull-stack-test-") as temp:
            root = Path(temp).resolve()
            try:
                _build_app(stack, root, layout, settings)
            except _SetupFailed as error:
                return [
                    CaseResult(c.id, CaseVerdict.FAIL, "app folder set up", str(error))
                    for c in _chain(case)
                ]
            results: list[CaseResult] = []
            current: Case | None = case
            while current is not None:
                try:
                    _apply_change(root, current)
                except _ChangeDoesNotApply as error:
                    results.append(
                        CaseResult(
                            current.id,
                            CaseVerdict.FAIL,
                            "change applies",
                            f"change does not apply: {error}",
                        )
                    )
                    results.extend(
                        CaseResult(
                            later.id,
                            CaseVerdict.NOT_RUN,
                            "",
                            "parent case's change does not apply",
                        )
                        for later in _chain(current.then)
                    )
                    break
                except _SetupFailed as error:
                    results.append(
                        CaseResult(
                            current.id, CaseVerdict.FAIL, "change commits", str(error)
                        )
                    )
                    results.extend(
                        CaseResult(
                            later.id, CaseVerdict.NOT_RUN, "", "parent case failed"
                        )
                        for later in _chain(current.then)
                    )
                    break
                results.append(self._judge(root, current))
                current = current.then
            return results

    def _judge(self, root: Path, case: Case) -> CaseResult:
        argv = [*self._bull, *case.run]
        if case.run and case.run[0] == "gates" and "--json" not in case.run:
            argv.append("--json")
        expected = _describe(case.expect)
        try:
            done = subprocess.run(
                argv,
                cwd=root,
                env=_child_env(),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as error:
            return CaseResult(
                case.id, CaseVerdict.FAIL, expected, f"bull did not start: {error}"
            )
        try:
            data: object = json.loads(done.stdout)
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            output = (done.stdout + done.stderr).strip()
            return CaseResult(
                case.id,
                CaseVerdict.FAIL,
                expected,
                f"output is not a JSON object (exit {done.returncode}): {output}",
            )
        got, matched = _compare(case.expect, cast("dict[str, object]", data))
        verdict = CaseVerdict.PASS if matched else CaseVerdict.FAIL
        return CaseResult(case.id, verdict, expected, got)


# --- preparation ------------------------------------------------------------------


def _chain(case: Case | None) -> list[Case]:
    """The case and its `then` cases, in run order."""
    chain: list[Case] = []
    while case is not None:
        chain.append(case)
        case = case.then
    return chain


def _layout_and_settings(
    stack: Stack,
) -> tuple[dict[str, str], dict[str, object]]:
    """`layout` and `settings` from `cases.json` (already parsed once by `load_cases`)."""
    path = stack.home / "cases.json"
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    # coverage-exempt-begin: cases.json was just parsed by load_cases; a re-read failing is a race
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StackError(f"{path}: cannot read cases.json: {error}") from error
    # coverage-exempt-end
    doc = cast("dict[str, object]", data) if isinstance(data, dict) else {}
    raw_layout = doc.get("layout", {"app/": "."})
    if not isinstance(raw_layout, dict) or not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in cast("dict[object, object]", raw_layout).items()
    ):
        raise StackError(
            f"{path.name}: `layout` must map fixture folders to app folders"
        )
    raw_settings = doc.get("settings", {})
    if not isinstance(raw_settings, dict):
        raise StackError(f"{path.name}: `settings` must be an object")
    return (
        dict(cast("dict[str, str]", raw_layout)),
        dict(cast("dict[str, object]", raw_settings)),
    )


def _not_run_reason(stack: Stack, layout: Mapping[str, str]) -> str | None:
    """Why no case can run: a required tool or a layout fixture folder is missing."""
    hints = {"git": "install git"}
    for req in stack.manifest.requires:
        hints.setdefault(req.tool, req.hint)
    missing = [tool for tool in hints if shutil.which(tool) is None]
    if missing:
        return "; ".join(f"missing {tool}: {hints[tool]}" for tool in missing)
    fixture = stack.home / "fixture"
    absent = [name for name in layout if not (fixture / name).exists()]
    if absent:
        return "; ".join(f"missing fixture/{name}" for name in absent)
    return None


def _inside(root: Path, relative: str) -> Path:
    """`root / relative`, refusing a path that leaves `root`."""
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise _SetupFailed(f"path `{relative}` is outside the app folder")
    return target


def _build_app(
    stack: Stack,
    root: Path,
    layout: Mapping[str, str],
    settings: Mapping[str, object],
) -> None:
    """Copy the fixture by layout, write `.bull/`, init git and commit."""
    fixture = stack.home / "fixture"
    try:
        for source_name, dest_name in layout.items():
            source = fixture / source_name
            dest = _inside(root, dest_name)
            if source.is_dir():
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
        _write_bull_files(stack, root, settings)
    # coverage-exempt-begin: OSError while copying the fixture cannot be provoked portably
    except OSError as error:
        raise _SetupFailed(f"cannot build the app folder: {error}") from error
    # coverage-exempt-end
    _git(root, "init", "--quiet", "--initial-branch=main")
    _git(root, "add", "--all")
    _git(root, "commit", "--quiet", "--no-verify", "-m", "bull: init")


def _write_bull_files(stack: Stack, root: Path, settings: Mapping[str, object]) -> None:
    """The `.bull/` files and `.gitignore` lines `bull init` writes, at stage 5."""
    bull_dir = root / ".bull"
    bull_dir.mkdir(exist_ok=True)
    config = ["format = 1", f"stack = {_toml_value(stack.manifest.name)}"]
    config += [
        f"{_toml_key(k, dotted=True)} = {_toml_value(v)}" for k, v in settings.items()
    ]
    (bull_dir / "config.toml").write_text("\n".join(config) + "\n", encoding="utf-8")

    memo = root / "docs" / "outline.md"
    memo_text = memo.read_text(encoding="utf-8") if memo.is_file() else ""
    status = {
        "format": 1,
        "kind": "app",
        "stage": 5,
        "checkpoints": list(_CHECKPOINTS),
        "modules": _memo_modules(memo_text),
        "pause": None,
        "waiting": None,
        "approvals": [],
        "plan": None,
        "feature": None,
        "adoption": None,
    }
    _write_json(bull_dir / "status.json", status)
    _write_json(bull_dir / "backlog.json", {"format": 1, "items": []})

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    have = set(existing.splitlines())
    wanted = [*_MACHINE_LOCAL_IGNORES, *stack.manifest.gitignore]
    extra = [line for line in dict.fromkeys(wanted) if line not in have]
    if extra:
        prefix = (
            existing if not existing or existing.endswith("\n") else existing + "\n"
        )
        gitignore.write_text(prefix + "\n".join(extra) + "\n", encoding="utf-8")


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(key: str, *, dotted: bool = False) -> str:
    """A TOML key; quoted unless bare.

    With `dotted` (top-level settings keys), `coverage.exclude` stays a dotted
    key and each part is quoted on its own; keys inside a nested object are
    single keys, dots and all.
    """
    parts = key.split(".") if dotted else [key]
    return ".".join(
        part if _BARE_KEY.match(part) else json.dumps(part) for part in parts
    )


def _toml_value(value: object) -> str:
    """A TOML literal for a JSON value (str, bool, int, float, list, object).

    An object becomes an inline table. JSON null has no TOML form.

    Raises:
        _SetupFailed: the value (or one inside it) is null or another type.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        items = cast("list[object]", value)
        return "[" + ", ".join(_toml_value(item) for item in items) + "]"
    if isinstance(value, dict):
        table = cast("dict[object, object]", value)
        entries = [f"{_toml_key(str(k))} = {_toml_value(v)}" for k, v in table.items()]
        return "{" + ", ".join(entries) + "}"
    raise _SetupFailed(f"setting value {value!r} cannot be written to config.toml")


_HEADING2 = re.compile(r"^##\s+(.+?)\s*$")
_HEADING3 = re.compile(r"^###\s+(.+?)\s*$")
_FIELD = re.compile(r"^-\s+([A-Za-z ]+):\s*(.*?)\s*$")


def _memo_modules(memo: str) -> list[dict[str, object]]:
    """Status modules from the memo's `## Modules` section, in memo order."""
    modules: list[dict[str, object]] = []
    in_modules = False
    fields: dict[str, str] | None = None
    name = ""

    def flush() -> None:
        if fields is not None:
            modules.append(_status_module(name, fields))

    for line in memo.splitlines():
        if heading := _HEADING2.match(line):
            flush()
            fields = None
            in_modules = heading.group(1).strip().lower() == "modules"
            continue
        if not in_modules:
            continue
        if sub := _HEADING3.match(line):
            flush()
            name = sub.group(1).strip()
            fields = {}
        elif fields is not None and (field := _FIELD.match(line)):
            fields.setdefault(field.group(1).strip().lower(), field.group(2))
    flush()
    return modules


def _status_module(name: str, fields: Mapping[str, str]) -> dict[str, object]:
    depends_text = fields.get("depends on", "").strip()
    depends = (
        []
        if depends_text.lower() in ("", "none")
        else [d.strip() for d in depends_text.split(",") if d.strip()]
    )
    groups = [g for g in fields.get("files", "").split("|") if g.strip()]
    units = [
        {
            "number": number,
            "files": [f.strip() for f in group.split(",") if f.strip()],
            "kind": "code",
            "state": "pending",
            "attempts": 1,
        }
        for number, group in enumerate(groups, start=1)
    ]
    return {
        "name": name,
        "part": fields.get("part", "").strip(),
        "depends": depends,
        "state": "pending",
        "reference_tests": bool(fields.get("reference tests", "").strip()),
        "scan": None,
        "units": units,
    }


def _child_env() -> dict[str, str]:
    """This process's env without the git repo-location variables."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}


def _git(root: Path, *args: str) -> None:
    env = _child_env()
    for key, value in _GIT_IDENTITY.items():
        env.setdefault(key, value)
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=root,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    # coverage-exempt-begin: git failing to launch (OSError) cannot be simulated without removing git
    except OSError as error:
        raise _SetupFailed(f"git {args[0]} did not start: {error}") from error
    # coverage-exempt-end
    if done.returncode != 0:
        raise _SetupFailed(f"git {args[0]} failed: {done.stderr.strip()}")


# --- change -----------------------------------------------------------------------


def _apply_change(root: Path, case: Case) -> None:
    """Apply `case.change`; commit it unless the case is dirty (or nothing changed).

    Every `replace`/`delete` path is checked before anything is written, so a
    change that does not apply leaves the folder as it was.
    """
    change = case.change
    adds = cast("Mapping[str, str]", change.get("add", {}))
    replaces = cast("Mapping[str, str]", change.get("replace", {}))
    deletes = cast("Sequence[str]", change.get("delete", ()))
    if not adds and not replaces and not deletes:
        return
    try:
        for path in (*replaces, *deletes):
            if not _inside(root, path).is_file():
                raise _ChangeDoesNotApply(f"`{path}` does not exist")
        for path, text in (*adds.items(), *replaces.items()):
            target = _inside(root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        for path in deletes:
            _inside(root, path).unlink()
    except _SetupFailed as error:
        raise _ChangeDoesNotApply(str(error)) from error
    except OSError as error:
        raise _SetupFailed(f"cannot apply the change: {error}") from error
    if not change.get("dirty", False):
        _git(root, "add", "--all")
        _git(root, "commit", "--quiet", "--no-verify", "-m", f"stack test: {case.id}")


# --- expect -----------------------------------------------------------------------


def _describe(values: Mapping[str, object]) -> str:
    return ", ".join(f"{key}={json.dumps(value)}" for key, value in values.items())


def _compare(
    expect: Mapping[str, object], data: Mapping[str, object]
) -> tuple[str, bool]:
    """Bull's value for each expected key (as text) and whether all of them match."""
    got: dict[str, object] = {}
    matched = True
    for key, wanted in expect.items():
        if key == "verdict":
            value: object = data.get("verdict")
            ok = isinstance(value, str) and value == wanted
        elif key == "gate":
            value = _failing_gate(data)
            ok = value == wanted
        elif key == "output":
            labels = _failure_texts(data)
            value = labels
            ok = isinstance(wanted, str) and any(wanted in text for text in labels)
        elif key == "recorded":
            value = data.get("recorded")
            ok = isinstance(value, bool) and value is wanted
        elif key == "ran":
            value = data.get("tests_run")
            ok = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and not isinstance(wanted, bool)
                and value == wanted
            )
        else:
            value = f"unsupported expect key `{key}`"
            ok = False
        got[key] = value
        matched = matched and ok
    return _describe(got), matched


def _steps(data: Mapping[str, object]) -> list[Mapping[str, object]]:
    steps = data.get("steps")
    if not isinstance(steps, list):
        return []
    return [
        cast("Mapping[str, object]", step)
        for step in cast("list[object]", steps)
        if isinstance(step, dict)
    ]


def _failing_gate(data: Mapping[str, object]) -> object:
    """The gate of the first failed or aborted step, or None."""
    for step in _steps(data):
        if step.get("verdict") in _FAILING_STEP:
            return step.get("gate")
    return None


def _failure_texts(data: Mapping[str, object]) -> list[str]:
    """Failure labels of failed steps, plus the item and fix texts of check items."""
    texts: list[str] = []
    for step in _steps(data):
        if step.get("verdict") in _FAILING_STEP:
            labels = step.get("labels")
            if isinstance(labels, list):
                texts += [s for s in cast("list[object]", labels) if isinstance(s, str)]
    items = data.get("items")
    if isinstance(items, list):
        for item in cast("list[object]", items):
            if isinstance(item, dict):
                entry = cast("dict[str, object]", item)
                texts += [
                    text
                    for text in (entry.get("item"), entry.get("fix"))
                    if isinstance(text, str)
                ]
    return texts
