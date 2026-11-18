"""ios gate steps: `{python} {stack_dir}/gates.py <step> …`.

bull runs each step in the part root with its `BULL_*` environment (`BULL_PART_ROOT`,
`BULL_RESULTS`, `BULL_STACK_DIR`, `BULL_ADOPT_MODE`, `BULL_SCOPE_MODULE`, `BULL_SETTINGS`, and
`BULL_URL_<PART>` for journeys). Stdlib only; every tool runs through `subprocess.run`.

Steps:
- `preflight`: choose the simulator (`simulator.choose`) and store its UDID in
  `{results}/simulator.txt`; nothing matches → exit 2 naming the `simulator` setting.
- `setup`: `xcodebuild -version` and `xcodebuild -list -project <project>` succeed.
- `build-test`: the unit test target (`BULL_SCOPE_MODULE` set → only that module's suites).
- `build-test-fast <module>`: only the module's suites.
- `rerun <ids…>`: `-only-testing:<unit target>/<id>` per id.
- `journeys`: the UI test target, `BULL_URL_<PART>` passed as `TEST_RUNNER_BULL_URL_<PART>`;
  after a failure, the failures' attachments (screenshots) are exported.
- `lint <module>`: `swiftlint lint --strict` and `xcrun swift-format lint --strict` on the
  module's source and test folders, with the app's own config at the part root when it has one.
- `prune`: delete `.bull/build/` and the result bundles.

Every xcodebuild run uses the simulator in `simulator.txt`, one destination, no parallel
testing, DerivedData under `.bull/build/`, a result bundle `{results}/<step>.xcresult`, and
diagnostics collected only on failure. Swift 6 with warnings as errors; in adopt mode the
project's language mode is kept with complete concurrency checking, and a warning in `Modules/`
or a module test folder fails the build. A "simulator busy" failure is rerun, at most 3 runs.
The whole output goes to `{results}/<step>.log`; the printed tail leaves out launch noise.
Failures print `bull-fail: <label>` lines.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# Imported relatively when loaded as a package (tests, bull's readers); as a script, the
# stack folder is the first entry of `sys.path`.
if __package__:
    from . import simulator
else:
    import simulator  # type: ignore[import-not-found,no-redef]  # coverage-exempt: script mode only

_USAGE = (
    "usage: gates.py <step> [args]\n"
    "steps: preflight | setup | build-test | build-test-fast <module> | lint <module> | "
    "rerun <test ids…> | journeys | prune"
)
_DERIVED_DATA = ".bull/build/DerivedData"
_BUILD_DIR = ".bull/build"
_BUNDLE_SUFFIX = ".xcresult"
_UNIT_STEPS = ("build-test", "build-test-fast", "rerun")
_ATTACHMENTS = "journeys-attachments"
_MAX_RUNS = 3
_BUSY_WAIT_SECONDS = 10.0
_BUSY = "simulator busy"
_TAIL_LINES = 60
_NOISE = (
    "IDETestOperationsObserverDebug",
    "Writing diagnostic log for test session",
    "Using the first of multiple matching destinations",
)
_DIAGNOSTIC = re.compile(
    r"^(?P<file>[^:\n]+\.swift):(?P<line>\d+):(?:\d+:)?\s*(?P<kind>error|warning):"
)
_LINT_PROBLEM = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:\d+:)?\s*(?:error|warning)"
)
_XCTEST_FAILED = re.compile(
    r"Test Case '-\[(?:[\w.]+\.)?(?P<suite>\w+) (?P<test>\w+)\]' failed"
)
_APP_SWIFTLINT = ".swiftlint.yml"
_APP_SWIFT_FORMAT = ".swift-format"
_URL_PREFIX = "BULL_URL_"
_RUNNER_PREFIX = "TEST_RUNNER_"
_TYPE_DECL = re.compile(r"\b(?:struct|class|actor|enum)\s+([A-Za-z_]\w*)")
_SWIFT_NOISE = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*[\s\S]*?\*/')


class _UsageError(Exception):
    """A step was called with the wrong arguments, an unknown name, or a bad environment."""


class _LaunchError(Exception):
    """A tool could not be started at all (missing, not executable): the step can't go on."""


@dataclass(frozen=True)
class _Env:
    """The parts of the step environment the steps use."""

    root: Path
    results: Path
    stack_dir: Path
    adopt: bool
    scope: str
    project: str
    scheme: str
    source_dir: str
    test_dir: str
    unit_target: str
    ui_target: str
    simulator: str

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

        def text(key: str, default: str) -> str:
            value = settings.get(key)
            return (value if isinstance(value, str) and value else default).rstrip("/")

        sim = settings.get("simulator")
        return _Env(
            root=root,
            results=results,
            stack_dir=stack_dir,
            adopt=os.environ.get("BULL_ADOPT_MODE", "0") == "1",
            scope=os.environ.get("BULL_SCOPE_MODULE", ""),
            project=text("project", "App/MyApp/MyApp.xcodeproj"),
            scheme=text("scheme", "MyApp"),
            source_dir=text("source_dir", "App/MyApp/MyApp"),
            test_dir=text("test_dir", "App/MyApp/MyAppTests"),
            unit_target=text("unit_test_target", "MyAppTests"),
            ui_target=text("ui_test_target", "MyAppUITests"),
            simulator=sim if isinstance(sim, str) else "",
        )

    def module_tests(self, module: str) -> str:
        return f"{self.test_dir}/{module}"

    def module_src(self, module: str) -> str:
        return f"{self.source_dir}/Modules/{module}"

    def rel(self, file: str) -> str | None:
        """`file` relative to the part root; None when it lies outside it."""
        path = Path(file)
        if not path.is_absolute():
            return path.as_posix()
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            try:
                return path.resolve().relative_to(self.root.resolve()).as_posix()
            except (ValueError, OSError):
                return None


# --- running tools -------------------------------------------------------------------------


def _run(
    env: _Env, argv: Sequence[str], child_env: Mapping[str, str] | None = None
) -> tuple[int, str]:
    """Run one tool in the part root; (exit code, stdout and stderr merged).

    Raises `_LaunchError` when the tool can't be started.
    """
    try:
        done = subprocess.run(
            list(argv),
            cwd=env.root,
            env=dict(child_env) if child_env is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise _LaunchError(
            f"could not run `{argv[0]}` ({exc.strerror or exc}): install Xcode 26 or later, "
            "open it once, run `xcode-select -s /Applications/Xcode.app` (and `brew install "
            "swiftlint` for lint), then run the gates again."
        ) from exc
    return done.returncode, done.stdout or ""


def _fail(label: str) -> None:
    print(f"bull-fail: {label}")


def _show_tail(output: str) -> None:
    """Print the last lines of `output`, leaving out known launch noise."""
    lines = [
        line
        for line in output.splitlines()
        if line.strip() and not any(noise in line for noise in _NOISE)
    ]
    for line in lines[-_TAIL_LINES:]:
        print(line)


# --- xcodebuild ----------------------------------------------------------------------------


def _udid(env: _Env) -> str:
    """The UDID preflight stored; chosen now when preflight hasn't run."""
    stored = env.results / simulator.UDID_FILE
    if stored.is_file():
        udid = stored.read_text(encoding="utf-8").strip()
        if udid:
            return udid
    return simulator.choose(env.simulator, env.results)


def _swift_settings(env: _Env) -> list[str]:
    if env.adopt:
        return ["SWIFT_STRICT_CONCURRENCY=complete"]
    return ["SWIFT_VERSION=6", "SWIFT_TREAT_WARNINGS_AS_ERRORS=YES"]


def _xcodebuild(
    env: _Env,
    step: str,
    only: Sequence[str] | None,
    child_env: Mapping[str, str] | None = None,
) -> int:
    """Run one xcodebuild test step; returns 0 on a pass, 1 on a failure.

    `only` lists `-only-testing` targets; an empty list builds the tests without running any
    (`build-for-testing`). Busy-simulator failures are rerun, at most `_MAX_RUNS` runs.
    """
    udid = _udid(env)
    bundle = env.results / f"{step}{_BUNDLE_SUFFIX}"
    log = env.results / f"{step}.log"
    action = "test" if only else "build-for-testing"
    argv = [
        "xcodebuild",
        action,
        "-project",
        env.project,
        "-scheme",
        env.scheme,
        "-destination",
        f"id={udid}",
        "-parallel-testing-enabled",
        "NO",
        "-derivedDataPath",
        _DERIVED_DATA,
        "-resultBundlePath",
        str(bundle),
    ]
    if only:
        argv += ["-collect-test-diagnostics", "on-failure"]
        argv += [f"-only-testing:{target}" for target in only]
    argv += _swift_settings(env)

    code, output = 0, ""
    with log.open("w", encoding="utf-8") as log_file:
        for attempt in range(1, _MAX_RUNS + 1):
            # xcodebuild refuses to write into an existing bundle.
            shutil.rmtree(bundle, ignore_errors=True)
            code, output = _run(env, argv, child_env)
            log_file.write(output)
            log_file.flush()
            if code == 0 or _BUSY not in output.lower() or attempt == _MAX_RUNS:
                break
            print(
                f"simulator busy; running {step} again (run {attempt + 1} of {_MAX_RUNS})"
            )
            time.sleep(_BUSY_WAIT_SECONDS * attempt)

    _show_tail(output)
    labels = _build_labels(env, output)
    if code != 0 and not labels:
        if _BUSY in output.lower():
            labels = [f"{step}: simulator busy after {_MAX_RUNS} runs"]
        else:
            labels = _failed_tests(output) or [
                f"{step} failed (xcodebuild exit {code}; see {log})"
            ]
    for label in labels:
        _fail(label)
    return 1 if code != 0 or labels else 0


def _build_labels(env: _Env, output: str) -> list[str]:
    """Compile errors as `<file>:<line>`; in adopt mode, module warnings as `warning …`."""
    labels: list[str] = []
    for line in output.splitlines():
        match = _DIAGNOSTIC.match(line.strip())
        if match is None:
            continue
        rel = env.rel(match["file"])
        if match["kind"] == "error":
            labels.append(f"{rel or match['file']}:{match['line']}")
        elif env.adopt and rel is not None and _in_module_code(env, rel):
            labels.append(f"warning {rel}:{match['line']}")
    return list(dict.fromkeys(labels))


def _in_module_code(env: _Env, rel: str) -> bool:
    """Whether `rel` lies in `Modules/` or in a module's test folder (`<test_dir>/<Module>/`)."""
    if rel.startswith(f"{env.source_dir}/Modules/"):
        return True
    prefix = f"{env.test_dir}/"
    return rel.startswith(prefix) and "/" in rel[len(prefix) :]


def _failed_tests(output: str) -> list[str]:
    """`test <Suite>/<test>()` for each XCTest case the output reports as failed."""
    found = [
        f"test {m['suite']}/{m['test']}()" for m in _XCTEST_FAILED.finditer(output)
    ]
    return list(dict.fromkeys(found))


# --- suite discovery -----------------------------------------------------------------------


def _suites(folder: Path) -> list[str]:
    """Top-level types in the `.swift` files under `folder` named `…Tests` or marked `@Suite`."""
    if not folder.is_dir():
        return []
    found: list[str] = []
    for path in sorted(folder.rglob("*.swift")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"could not read {path} for its test suites: {exc}")
            continue
        found.extend(_top_level_suites(text))
    return list(dict.fromkeys(found))


def _top_level_suites(text: str) -> list[str]:
    """Suites declared at brace depth 0 of `text` (comments and string contents ignored).

    A type is a suite when its name ends in `Tests` or an `@Suite` attribute precedes it since
    the previous top-level closing brace.
    """
    clean = _SWIFT_NOISE.sub(lambda m: '""' if m.group(0).startswith('"') else "", text)
    suites: list[str] = []
    depth = 0
    boundary = 0  # where the current top-level statement run starts
    position = 0
    for match in _TYPE_DECL.finditer(clean):
        for i in range(position, match.start()):
            char = clean[i]
            if char == "{":
                depth += 1
            elif char == "}":
                depth = max(depth - 1, 0)
                if depth == 0:
                    boundary = i + 1
        position = match.start()
        if depth != 0:
            continue
        name = match.group(1)
        if name.endswith("Tests") or "@Suite" in clean[boundary : match.start()]:
            suites.append(name)
    return suites


# --- steps ---------------------------------------------------------------------------------


def _preflight(env: _Env, args: list[str]) -> int:
    _no_args("preflight", args)
    try:
        udid = simulator.choose(env.simulator, env.results)
    except simulator.SimulatorError as exc:
        print(exc)
        return 2
    print(f"simulator {udid}")
    return 0


def _setup(env: _Env, args: list[str]) -> int:
    _no_args("setup", args)
    ok = True
    code, output = _run(env, ["xcodebuild", "-version"])
    if code != 0:
        _show_tail(output)
        _fail("setup xcodebuild -version")
        print(
            "Install Xcode, open it once, then `xcode-select -s /Applications/Xcode.app`."
        )
        ok = False
    code, output = _run(env, ["xcodebuild", "-list", "-project", env.project])
    if code != 0:
        _show_tail(output)
        _fail(f"setup project {env.project}")
        print("Check the `project` setting and that Xcode can open the project.")
        ok = False
    return 0 if ok else 1


def _build_test(env: _Env, args: list[str]) -> int:
    _no_args("build-test", args)
    _clear_unit_bundles(env)
    if env.scope:
        return _run_suites(env, "build-test", env.scope)
    return _xcodebuild(env, "build-test", [env.unit_target])


def _build_test_fast(env: _Env, args: list[str]) -> int:
    module = _one_module("build-test-fast", args)
    _clear_unit_bundles(env)
    return _run_suites(env, "build-test-fast", module)


def _run_suites(env: _Env, step: str, module: str) -> int:
    suites = _suites(env.root / env.module_tests(module))
    return _xcodebuild(env, step, [f"{env.unit_target}/{suite}" for suite in suites])


def _rerun(env: _Env, args: list[str]) -> int:
    if not args:
        raise _UsageError("rerun needs at least one test id")
    _clear_unit_bundles(env)
    return _xcodebuild(
        env, "rerun", [f"{env.unit_target}/{test_id}" for test_id in args]
    )


def _journeys(env: _Env, args: list[str]) -> int:
    _no_args("journeys", args)
    child_env = dict(os.environ)
    for key, value in os.environ.items():
        if key.startswith(_URL_PREFIX):
            child_env[_RUNNER_PREFIX + key] = value
    result = _xcodebuild(env, "journeys", [env.ui_target], child_env)
    if result != 0:
        _export_failure_attachments(env)
    return result


def _export_failure_attachments(env: _Env) -> None:
    """Keep the failed journeys' screenshots in `{results}/journeys-attachments`."""
    out = env.results / _ATTACHMENTS
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    bundle = env.results / f"journeys{_BUNDLE_SUFFIX}"
    code, output = _run(
        env,
        [
            "xcrun",
            "xcresulttool",
            "export",
            "attachments",
            "--path",
            str(bundle),
            "--output-path",
            str(out),
            "--only-failures",
        ],
    )
    if code != 0:
        print(f"could not export the failures' attachments: {output.strip()}")
    else:
        print(f"failure attachments: {out}")


def _lint(env: _Env, args: list[str]) -> int:
    module = _one_module("lint", args)
    paths = [
        p
        for p in (env.module_src(module), env.module_tests(module))
        if (env.root / p).exists()
    ]
    if not paths:
        print(f"nothing to lint: no folders for module {module}")
        return 0
    own_lint = env.root / _APP_SWIFTLINT
    own_fmt = env.root / _APP_SWIFT_FORMAT
    lint_cfg = (
        own_lint if own_lint.is_file() else env.stack_dir / "lint" / "swiftlint.yml"
    )
    fmt_cfg = (
        own_fmt if own_fmt.is_file() else env.stack_dir / "lint" / "swift-format.json"
    )
    failed = False
    for tool, argv in (
        (
            "swiftlint",
            ["swiftlint", "lint", "--strict", "--config", str(lint_cfg), *paths],
        ),
        (
            "swift-format",
            [
                "xcrun",
                "swift-format",
                "lint",
                "--strict",
                "--recursive",
                "--configuration",
                str(fmt_cfg),
                *paths,
            ],
        ),
    ):
        code, output = _run(env, argv)
        if code == 0:
            continue
        failed = True
        _show_tail(output)
        labels = [
            f"lint {env.rel(m['file']) or m['file']}:{m['line']}"
            for m in (_LINT_PROBLEM.match(line.strip()) for line in output.splitlines())
            if m
        ]
        for label in list(dict.fromkeys(labels)) or [f"lint {tool}"]:
            _fail(label)
    return 1 if failed else 0


def _prune(env: _Env, args: list[str]) -> int:
    _no_args("prune", args)
    build = env.root / _BUILD_DIR
    if build.exists():
        shutil.rmtree(build)
        print(f"removed {build}")
    if env.results.is_dir():
        for bundle in sorted(env.results.glob(f"*{_BUNDLE_SUFFIX}")):
            if bundle.is_dir():
                shutil.rmtree(bundle)
                print(f"removed {bundle}")
    return 0


def _clear_unit_bundles(env: _Env) -> None:
    """Remove earlier unit-test bundles so a broken run can't be read as this one."""
    env.results.mkdir(parents=True, exist_ok=True)
    for step in _UNIT_STEPS:
        shutil.rmtree(env.results / f"{step}{_BUNDLE_SUFFIX}", ignore_errors=True)


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
    "prune": _prune,
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
    except simulator.SimulatorError as exc:
        print(exc)
        return 2


# coverage-exempt-begin: __main__ guard; main() is tested in-process
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# coverage-exempt-end
