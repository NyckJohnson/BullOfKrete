"""python_cli gate steps: `{python} {stack_dir}/gates.py <step> …`.

bull runs each step with its `BULL_*` environment (`BULL_PART_ROOT`, `BULL_RESULTS`,
`BULL_STACK_DIR`, `BULL_SCOPE_MODULE`, `BULL_SETTINGS`, …). Every tool runs through `uv run`
with the part root as its working folder; paths handed to the tools are part-root-relative.
Stdlib only: this file runs on bull's interpreter, not the app's venv.

Steps:
- `preflight`: `uv` on PATH and `uv sync` succeeds; otherwise exit 2 (bull aborts the run).
- `setup`: `pyproject.toml` exists, the package imports, the app's Python is 3.11 or newer.
- `build-test`: `mypy --strict` on the source folder (each error → `bull-fail: mypy <file>:<line>`),
  then pytest over the test folder minus `<test_dir>/journey` (or only `BULL_SCOPE_MODULE`'s
  tests) with coverage into `<results>/coverage.json` and `<results>/junit.xml`.
- `build-test-fast <module>`: mypy as above, then pytest over that module's tests, junit only.
- `lint <module>`: `ruff check` and `ruff format --check` (both `--output-format=concise`) on the
  module's source and tests, with the app's own ruff config when it has one, else the stack's
  `lint/ruff.toml`.
- `rerun <ids…>`: pytest on the given node ids, junit written.
- `journeys`: pytest over `<test_dir>/journey`.

Settings fall back to the manifest defaults: `package` → `myapp`, `source_dir` → `src/<package>`.
The `package` setting is never put into Python source: it is passed to the interpreter as an
argument and must be a dotted identifier. A tool that can't be launched (`uv` vanished from PATH,
not executable) prints a message naming `uv` and its fix and exits 2, without a traceback.

A failing test prints `bull-fail: test <node id>`. pytest's "no tests collected" (exit 5) does not
fail a step by itself: bull reads the junit count and reports "no tests" itself.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

UV_HINT = "https://docs.astral.sh/uv/getting-started/installation/"
"""Where to get `uv`; printed by preflight and the readers' `check`."""

_USAGE = (
    "usage: gates.py <step> [args]\n"
    "steps: preflight | setup | build-test | build-test-fast <module> | lint <module> | "
    "rerun <node ids…> | journeys"
)
_JOURNEY = "journey"
_JUNIT = "junit.xml"
_COVERAGE = "coverage.json"
_PYTEST_NO_TESTS = 5
_MYPY_ERROR = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:\d+:)? error:")
_RUFF_PROBLEM = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):\d+: ")
_RUFF_UNFORMATTED = re.compile(r"^(?P<file>[^:\n]+):\d+:\d+: unformatted:")
_APP_RUFF_FILES = ("ruff.toml", ".ruff.toml")
DEFAULT_PACKAGE = "myapp"
"""The manifest's default `package` setting (`stack.toml`)."""
IMPORT_BY_ARGUMENT = "import importlib, sys; importlib.import_module(sys.argv[1])"
"""`python -c` code importing the module named by its first argument (never interpolated)."""


def valid_package(name: str) -> bool:
    """Whether `name` is a dotted Python identifier (`pkg` or `pkg.sub`), safe to import by name."""
    return bool(name) and all(part.isidentifier() for part in name.split("."))


class _UsageError(Exception):
    """A step was called with the wrong arguments, an unknown name, or a bad environment."""


class _LaunchError(Exception):
    """A tool could not be started at all (missing, not executable): the run can't go on."""


@dataclass(frozen=True)
class _Env:
    """The parts of the step environment the steps use."""

    root: Path
    results: Path
    stack_dir: Path
    source_dir: str
    test_dir: str
    package: str
    scope: str

    @staticmethod
    def load() -> _Env:
        root = Path(os.environ.get("BULL_PART_ROOT") or Path.cwd())
        results = Path(os.environ.get("BULL_RESULTS") or root / "results")
        stack_dir = Path(os.environ.get("BULL_STACK_DIR") or Path(__file__).parent)
        try:
            raw = json.loads(os.environ.get("BULL_SETTINGS") or "{}")
        except json.JSONDecodeError as exc:
            raise _UsageError(f"BULL_SETTINGS is not JSON: {exc}") from exc
        settings: dict[str, object] = raw if isinstance(raw, dict) else {}
        package = _text(settings.get("package")) or DEFAULT_PACKAGE
        source_dir = _text(settings.get("source_dir")) or f"src/{package}"
        return _Env(
            root=root,
            results=results,
            stack_dir=stack_dir,
            source_dir=source_dir.rstrip("/"),
            test_dir=(_text(settings.get("test_dir")) or "tests").rstrip("/"),
            package=package,
            scope=os.environ.get("BULL_SCOPE_MODULE", ""),
        )

    @property
    def junit(self) -> Path:
        return self.results / _JUNIT

    def module_tests(self, module: str) -> str:
        return f"{self.test_dir}/{module}"


def _text(value: object) -> str:
    """`value` when it is a non-empty string, else ''."""
    return value if isinstance(value, str) else ""


# --- shared helpers ------------------------------------------------------------------------


def junit_run(path: Path) -> tuple[int, list[str]] | None:
    """(test count, failed or errored node ids) from a pytest junit file; None if unreadable.

    Node ids are rebuilt from `classname`: dots become slashes plus `.py`, and a last part
    starting with `Test` is the test class (`tests/a/test_x.py::TestY::test_z`). A collection
    error (empty `classname`) is reported under its module path.
    """
    if not path.is_file():
        return None
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return None
    count = 0
    failed: list[str] = []
    for case in tree.getroot().iter("testcase"):
        count += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failed.append(_node_id(case.get("classname", ""), case.get("name", "")))
    return count, failed


def _node_id(classname: str, name: str) -> str:
    if not classname:
        return name.replace(".", "/") + ".py"
    parts = classname.split(".")
    test_class = ""
    if len(parts) > 1 and parts[-1].startswith("Test"):
        test_class = parts.pop()
    node = "/".join(parts) + ".py"
    if test_class:
        node += f"::{test_class}"
    return f"{node}::{name}"


def _run(env: _Env, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run one tool in the part root, echoing its output.

    Raises `_LaunchError` when the tool can't be started (an `OSError` from the launch).
    """
    child_env = dict(os.environ)
    child_env["COVERAGE_FILE"] = str(env.results / ".coverage")
    try:
        done = subprocess.run(
            list(argv),
            cwd=env.root,
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise _LaunchError(
            f"could not run `{argv[0]}` ({exc.strerror or exc}): check that `uv` is "
            f"installed and on PATH ({UV_HINT}), then run `uv sync` in the part folder."
        ) from exc
    if done.stdout:
        print(done.stdout, end="" if done.stdout.endswith("\n") else "\n")
    if done.stderr:
        print(done.stderr, end="" if done.stderr.endswith("\n") else "\n")
    return done


def _fail(label: str) -> None:
    print(f"bull-fail: {label}")


def _clear(env: _Env, *names: str) -> None:
    """Remove earlier result files so a broken run can't be read as this one."""
    env.results.mkdir(parents=True, exist_ok=True)
    for name in names:
        (env.results / name).unlink(missing_ok=True)


def _mypy(env: _Env) -> bool:
    done = _run(env, ["uv", "run", "mypy", "--strict", env.source_dir])
    if done.returncode == 0:
        return True
    labels = [
        f"mypy {m['file']}:{m['line']}"
        for m in (_MYPY_ERROR.match(line) for line in done.stdout.splitlines())
        if m
    ]
    for label in labels or ["mypy"]:
        _fail(label)
    return False


def _pytest(env: _Env, args: Sequence[str], junit: bool = True) -> bool:
    argv = ["uv", "run", "pytest", *args]
    if junit:
        argv.append(f"--junitxml={env.junit}")
    done = _run(env, argv)
    if junit:
        found = junit_run(env.junit)
        for node_id in found[1] if found else []:
            _fail(f"test {node_id}")
    return done.returncode in (0, _PYTEST_NO_TESTS)


# --- steps ---------------------------------------------------------------------------------


def _preflight(env: _Env, args: list[str]) -> int:
    _no_args("preflight", args)
    if shutil.which("uv") is None:
        print(f"`uv` is not on PATH. Install it: {UV_HINT}")
        return 2
    done = _run(env, ["uv", "sync"])
    if done.returncode != 0:
        print(
            "`uv sync` failed in the part folder: fix pyproject.toml or the network, "
            "then run `uv sync` there (see `bull stack setup`)."
        )
        return 2
    return 0


def _setup(env: _Env, args: list[str]) -> int:
    _no_args("setup", args)
    if not (env.root / "pyproject.toml").is_file():
        _fail("pyproject.toml missing")
        print("Write pyproject.toml at the part root (see `bull stack setup`).")
        return 1
    ok = True
    if not valid_package(env.package):
        _fail(f"package {env.package!r} is not a valid package name")
        print(
            "Set the package setting to a dotted Python name: `bull config set package …`."
        )
        ok = False
    elif _run(
        env, ["uv", "run", "python", "-c", IMPORT_BY_ARGUMENT, env.package]
    ).returncode:
        _fail(f"package {env.package} not importable")
        ok = False
    version = "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if _run(env, ["uv", "run", "python", "-c", version]).returncode:
        _fail("python older than 3.11")
        ok = False
    return 0 if ok else 1


def _build_test(env: _Env, args: list[str]) -> int:
    _no_args("build-test", args)
    _clear(env, _JUNIT, _COVERAGE)
    typed = _mypy(env)
    if env.scope:
        targets = [env.module_tests(env.scope)]
    else:
        targets = [env.test_dir, f"--ignore={env.test_dir}/{_JOURNEY}"]
    tested = _pytest(
        env,
        [
            *targets,
            f"--cov={env.source_dir}",
            f"--cov-report=json:{env.results / _COVERAGE}",
        ],
    )
    return 0 if typed and tested else 1


def _build_test_fast(env: _Env, args: list[str]) -> int:
    module = _one_module("build-test-fast", args)
    _clear(env, _JUNIT)
    typed = _mypy(env)
    tested = _pytest(env, [env.module_tests(module)])
    return 0 if typed and tested else 1


def _ruff_config(env: _Env) -> list[str]:
    """`--config <stack lint/ruff.toml>` unless the app has its own ruff config."""
    if any((env.root / name).is_file() for name in _APP_RUFF_FILES):
        return []
    pyproject = env.root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text())
        except (tomllib.TOMLDecodeError, OSError):
            data = {}
        tool = data.get("tool")
        if isinstance(tool, dict) and "ruff" in tool:
            return []
    return ["--config", str(env.stack_dir / "lint" / "ruff.toml")]


def _lint(env: _Env, args: list[str]) -> int:
    module = _one_module("lint", args)
    paths = [f"{env.source_dir}/Modules/{module}", env.module_tests(module)]
    config = _ruff_config(env)
    check = _run(
        env,
        ["uv", "run", "ruff", "check", "--output-format=concise", *config, *paths],
    )
    found = [m for m in map(_RUFF_PROBLEM.match, check.stdout.splitlines()) if m]
    for match in found:
        _fail(f"lint {match['file']}:{match['line']}")
    if check.returncode and not found:
        _fail("lint")
    fmt = _run(
        env,
        [
            "uv",
            "run",
            "ruff",
            "format",
            "--check",
            "--output-format=concise",
            *config,
            *paths,
        ],
    )
    unformatted = list(
        dict.fromkeys(
            m["file"]
            for m in map(_RUFF_UNFORMATTED.match, fmt.stdout.splitlines())
            if m
        )
    )
    for file in unformatted:
        _fail(f"format {file}")
    if fmt.returncode and not unformatted:
        _fail("format")
    return 1 if check.returncode or fmt.returncode else 0


def _rerun(env: _Env, args: list[str]) -> int:
    if not args:
        raise _UsageError("rerun needs at least one test node id")
    _clear(env, _JUNIT)
    return 0 if _pytest(env, args) else 1


def _journeys(env: _Env, args: list[str]) -> int:
    _no_args("journeys", args)
    done = _run(env, ["uv", "run", "pytest", f"{env.test_dir}/{_JOURNEY}"])
    return 0 if done.returncode in (0, _PYTEST_NO_TESTS) else 1


def _no_args(step: str, args: list[str]) -> None:
    if args:
        raise _UsageError(f"{step} takes no arguments")


def _one_module(step: str, args: list[str]) -> str:
    if len(args) != 1 or not args[0]:
        raise _UsageError(f"{step} needs exactly one module name")
    return args[0]


_STEPS: dict[str, Callable[[_Env, list[str]], int]] = {
    "preflight": _preflight,
    "setup": _setup,
    "build-test": _build_test,
    "build-test-fast": _build_test_fast,
    "lint": _lint,
    "rerun": _rerun,
    "journeys": _journeys,
}


def main(argv: Sequence[str]) -> int:
    """Run one gate step; returns its exit code (2 with a usage line on bad arguments)."""
    if not argv or argv[0] not in _STEPS:
        print(_USAGE)
        return 2
    step, args = argv[0], list(argv[1:])
    try:
        return _STEPS[step](_Env.load(), args)
    except _UsageError as exc:
        print(f"{exc}\n{_USAGE}")
        return 2
    except _LaunchError as exc:
        print(exc)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
