"""The fixture stacks' gate tool: `python -m bull.Modules.stack_fixture.tool <step> …`.

Runs with the part root as cwd and bull's step environment (`BULL_PART_ROOT`, `BULL_RESULTS`,
`BULL_ADOPT_MODE`, `BULL_SCOPE_MODULE`, `BULL_SETTINGS`, …). Steps:

- `preflight`: exit 2 when `fixture.toml` says `broken_toolchain = true`.
- `setup`: `bull-fail: fixture.toml missing` when the part root has no `fixture.toml`.
- `build-test`: every `WARN` line in a source `*.fx` file fails the build
  (`bull-fail: warning <file>:<line>`; ignored outside `Modules/` in adopt mode); then runs the
  module tests (all, or only `BULL_SCOPE_MODULE`) and writes `tests.json` and `coverage.json`.
- `build-test-fast <module>`: the same, with only that module's tests.
- `lint <module>`: every `LINT` line in the module's sources (`bull-fail: lint <file>:<line>`).
- `rerun <ids…>`: runs only the named tests; `tests.json` counts only those.
- `journeys`: runs `tests/journey/*.test`.
- `start` / `ready` / `stop`: the service steps, handed to `fixture_service/serve.py`.

Failing tests are printed as `bull-fail: test <id>` and make the step exit 1.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

_JOURNEY = "journey"
_SERVE_MODULE = "bull.Modules.stack_fixture.fixture_service.serve"


_Step = Callable[["_Env", list[str]], int]


class _UsageError(Exception):
    """A step was called with the wrong arguments or an unknown name."""


@dataclass(frozen=True)
class _Env:
    """The parts of the step environment the tool uses."""

    root: Path
    results: Path
    source_dir: Path
    test_dir: Path
    adopt: bool
    scope: str

    @staticmethod
    def load() -> _Env:
        root = Path(os.environ.get("BULL_PART_ROOT") or Path.cwd())
        results = Path(os.environ.get("BULL_RESULTS") or root / "results")
        try:
            settings = json.loads(os.environ.get("BULL_SETTINGS") or "{}")
        except json.JSONDecodeError as exc:
            raise _UsageError(f"BULL_SETTINGS is not JSON: {exc}") from exc
        if not isinstance(settings, dict):
            settings = {}
        source = settings.get("source_dir")
        tests = settings.get("test_dir")
        return _Env(
            root=root,
            results=results,
            source_dir=root / (source if isinstance(source, str) and source else "src"),
            test_dir=root / (tests if isinstance(tests, str) and tests else "tests"),
            adopt=os.environ.get("BULL_ADOPT_MODE") == "1",
            scope=os.environ.get("BULL_SCOPE_MODULE", ""),
        )

    def rel(self, path: Path) -> str:
        """`path` relative to the part root, posix style."""
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()


@dataclass
class _Run:
    """The outcome of running some tests."""

    count: int = 0
    failed: list[str] = field(default_factory=list)
    covered: dict[str, set[int]] = field(default_factory=dict)


# --- parsing -----------------------------------------------------------------------------


def _lines(path: Path) -> list[tuple[int, str]]:
    """The code lines of a fixture file: (1-based number, stripped text); skips blanks/comments."""
    out: list[tuple[int, str]] = []
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        text = raw.strip()
        if text and not text.startswith("#"):
            out.append((number, text))
    return out


def _expand(spec: str) -> set[int]:
    """`3,5-7` → {3, 5, 6, 7}; malformed parts are ignored."""
    lines: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        start, sep, end = part.partition("-")
        try:
            if sep:
                lines.update(range(int(start), int(end) + 1))
            elif part:
                lines.add(int(part))
        except ValueError:
            continue
    return lines


def _run_file(
    path: Path, test_id_prefix: str, run: _Run, only: set[str] | None
) -> set[str]:
    """Run the tests in one `.test` file into `run`; returns the names it ran.

    `only` limits the run to those test names (and skips coverage); None runs everything.
    """
    ran: set[str] = set()
    for _, text in _lines(path):
        word, _, rest = text.partition(" ")
        rest = rest.strip()
        if word in ("pass", "fail") and rest:
            if only is not None and rest not in only:
                continue
            ran.add(rest)
            run.count += 1
            if word == "fail":
                run.failed.append(f"{test_id_prefix}::{rest}")
        elif word == "covers" and only is None:
            target, _, spec = rest.rpartition(":")
            if target:
                run.covered.setdefault(target, set()).update(_expand(spec))
    return ran


def _test_files(env: _Env, module: str) -> list[Path]:
    folder = env.test_dir / module
    return sorted(folder.glob("*.test")) if folder.is_dir() else []


def _test_modules(env: _Env) -> list[str]:
    if not env.test_dir.is_dir():
        return []
    return sorted(
        p.name for p in env.test_dir.iterdir() if p.is_dir() and p.name != _JOURNEY
    )


def _run_modules(env: _Env, modules: list[str]) -> _Run:
    run = _Run()
    for module in modules:
        for path in _test_files(env, module):
            _run_file(path, f"{module}/{path.stem}", run, None)
    return run


# --- output ------------------------------------------------------------------------------


def _write_tests(env: _Env, run: _Run) -> None:
    env.results.mkdir(parents=True, exist_ok=True)
    (env.results / "tests.json").write_text(
        json.dumps({"count": run.count, "failed": run.failed}) + "\n"
    )


def _write_coverage(env: _Env, run: _Run) -> None:
    env.results.mkdir(parents=True, exist_ok=True)
    data = {path: sorted(lines) for path, lines in sorted(run.covered.items())}
    (env.results / "coverage.json").write_text(json.dumps(data) + "\n")


def _fail(label: str) -> None:
    print(f"bull-fail: {label}")


def _report_tests(run: _Run) -> int:
    for test_id in run.failed:
        _fail(f"test {test_id}")
    print(f"{run.count} tests, {len(run.failed)} failed")
    return 1 if run.failed else 0


# --- steps -------------------------------------------------------------------------------


def _read_fixture_toml(env: _Env) -> dict[str, object] | None:
    path = env.root / "fixture.toml"
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError:
        return {}


def _preflight(env: _Env, args: list[str]) -> int:
    data = _read_fixture_toml(env)
    if data is not None and data.get("broken_toolchain") is True:
        print("fixture toolchain is broken (fixture.toml: broken_toolchain = true)")
        return 2
    return 0


def _setup(env: _Env, args: list[str]) -> int:
    if _read_fixture_toml(env) is None:
        _fail("fixture.toml missing")
        return 1
    return 0


def _warnings(env: _Env) -> list[str]:
    """`warning <file>:<line>` for each `WARN` source line (outside `Modules/` skipped in adopt mode)."""
    if not env.source_dir.is_dir():
        return []
    modules = env.source_dir / "Modules"
    found: list[str] = []
    for path in sorted(env.source_dir.rglob("*.fx")):
        if env.adopt and not path.is_relative_to(modules):
            continue
        found.extend(
            f"warning {env.rel(path)}:{number}"
            for number, text in _lines(path)
            if "WARN" in text
        )
    return found


def _build_and_test(env: _Env, modules: list[str]) -> int:
    warnings = _warnings(env)
    for label in warnings:
        _fail(label)
    run = _run_modules(env, modules)
    _write_tests(env, run)
    _write_coverage(env, run)
    status = _report_tests(run)
    return 1 if warnings else status


def _build_test(env: _Env, args: list[str]) -> int:
    modules = [env.scope] if env.scope else _test_modules(env)
    return _build_and_test(env, modules)


def _one_module(args: list[str], step: str) -> str:
    if len(args) != 1 or not args[0]:
        raise _UsageError(f"{step} takes one module name")
    return args[0]


def _build_test_fast(env: _Env, args: list[str]) -> int:
    return _build_and_test(env, [_one_module(args, "build-test-fast")])


def _lint(env: _Env, args: list[str]) -> int:
    folder = env.source_dir / "Modules" / _one_module(args, "lint")
    found = 0
    if folder.is_dir():
        for path in sorted(folder.rglob("*.fx")):
            for number, text in _lines(path):
                if "LINT" in text:
                    _fail(f"lint {env.rel(path)}:{number}")
                    found += 1
    return 1 if found else 0


def _rerun(env: _Env, args: list[str]) -> int:
    """Runs only the tests named by id (`<module>/<stem>::<name>`); an unknown id fails."""
    wanted: dict[tuple[str, str], set[str]] = {}
    for test_id in args:
        file_part, sep, name = test_id.partition("::")
        module, slash, stem = file_part.partition("/")
        if not (sep and slash and module and stem and name):
            raise _UsageError(f"not a test id: {test_id}")
        wanted.setdefault((module, stem), set()).add(name)
    run = _Run()
    for (module, stem), names in wanted.items():
        path = env.test_dir / module / f"{stem}.test"
        ran = (
            _run_file(path, f"{module}/{stem}", run, names) if path.is_file() else set()
        )
        for missing in sorted(names - ran):
            print(f"test not found: {module}/{stem}::{missing}")
            run.count += 1
            run.failed.append(f"{module}/{stem}::{missing}")
    _write_tests(env, run)
    return _report_tests(run)


def _journeys(env: _Env, args: list[str]) -> int:
    run = _Run()
    for path in _test_files(env, _JOURNEY):
        _run_file(path, f"{_JOURNEY}/{path.stem}", run, None)
    return _report_tests(run)


def _service(step: str) -> _Step:
    """The seam to `fixture_service/serve.py`, which implements `main(argv) -> int`."""

    def run(env: _Env, args: list[str]) -> int:
        serve = importlib.import_module(_SERVE_MODULE)
        result = serve.main([step, *args])
        return int(result)

    return run


_STEPS: dict[str, _Step] = {
    "preflight": _preflight,
    "setup": _setup,
    "build-test": _build_test,
    "build-test-fast": _build_test_fast,
    "lint": _lint,
    "rerun": _rerun,
    "journeys": _journeys,
    "start": _service("start"),
    "ready": _service("ready"),
    "stop": _service("stop"),
}


def main(argv: list[str]) -> int:
    """Run one step; returns its exit code (64 for a usage error)."""
    if not argv or argv[0] not in _STEPS:
        print(f"usage: tool <{'|'.join(_STEPS)}> …", file=sys.stderr)
        return 64
    try:
        return _STEPS[argv[0]](_Env.load(), argv[1:])
    except _UsageError as exc:
        print(f"{argv[0]}: {exc}", file=sys.stderr)
        return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
