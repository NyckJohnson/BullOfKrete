"""Tests for `bull.Modules.stack_ios.ios.gates`.

Tests call `gates.main(argv)` in-process with the `BULL_*` environment set, the current
directory at the part root, and `subprocess.run` replaced by a recorder (no real xcodebuild,
xcrun, swiftlint or simctl). Choices where the spec is open (the code must match these):
- Every tool call goes through `subprocess.run` with an argv list; xcodebuild calls contain the
  word `xcodebuild`, lint calls `swiftlint` / `swift-format`, simctl calls `simctl`. Output may
  be captured (`stdout=PIPE`/`capture_output`) or written to a file object passed as `stdout`.
- Steps read the UDID from `{results}/simulator.txt` (written by preflight, here by the test).
- `preflight` runs `simctl list devices available -j`, writes the UDID, returns 2 and prints a
  message containing `simulator` when nothing matches; 0 otherwise.
- xcodebuild args: `-project`, `-scheme`, `-destination id=<UDID>`, `-parallel-testing-enabled
  NO`, `-derivedDataPath .bull/build/DerivedData`, `-resultBundlePath {results}/<step>.xcresult`
  (step = `build-test`, `build-test-fast`, `rerun`, `journeys`), `-collect-test-diagnostics
  on-failure`, `-only-testing:<target>[/<suite or test id>]` joined with a colon. Swift 6 mode:
  `SWIFT_VERSION=6` and `SWIFT_TREAT_WARNINGS_AS_ERRORS=YES` as build-setting args; adopt mode:
  neither, plus `SWIFT_STRICT_CONCURRENCY=complete`.
- Log: `{results}/<step>.log` holds the whole output; the printed tail leaves out lines holding
  `IDETestOperationsObserverDebug`, `Writing diagnostic log for test session` or `Using the
  first of multiple matching destinations`.
- Busy: a non-zero xcodebuild run whose output contains `simulator busy` (any case) is rerun,
  up to 3 runs in all, sleeping with `time.sleep`.
- Journeys: after a failed run, `xcresulttool export attachments ... --only-failures`;
  `BULL_URL_<PART>` reaches the run as `TEST_RUNNER_BULL_URL_<PART>` (in the call's `env` or as
  a `TEST_RUNNER_...=value` argument).
- Failures print `bull-fail: <label>` lines: `warning <file>:<line>` (adopt-mode warnings),
  `lint <file>:<line>`, a compile `error:` line labelled with its `<file>:<line>`; any other
  non-zero xcodebuild run prints at least one `bull-fail:` line.
- `rerun <ids>`: `-only-testing:<unit target>/<id>` per id. `prune` deletes `.bull/build` and
  every `*.xcresult` in the results folder, leaving other files.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

import bull.Modules.stack_ios as pkg
from bull.Modules.stack_ios.ios import gates

_STACK_DIR = Path(pkg.__file__).parent / "ios"
_SRC = "App/Demo/Demo"
_TESTS = "App/Demo/DemoTests"
_UDID = "UDID-1234"
_BUSY = "xcodebuild: error: Testing failed: Simulator busy, try again"

Rule = Callable[[list[str]], subprocess.CompletedProcess[str] | None]


def _done(rc: int = 0, out: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], rc, out, "")


class Runner:
    """Records every subprocess.run call; `rules` decide each result (default: success)."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, Any]] = []
        self.rules: list[Rule] = []

    def __call__(self, args: Sequence[str] | str, *a: object, **kw: Any) -> Any:
        argv = [str(x) for x in ([args] if isinstance(args, str) else args)]
        self.calls.append(argv)
        self.kwargs.append(kw)
        result = _done()
        for rule in self.rules:
            found = rule(argv)
            if found is not None:
                result = found
                break
        sink = kw.get("stdout")
        if sink is not None and hasattr(sink, "write"):
            sink.write(result.stdout or "")
            sink.flush()
            return subprocess.CompletedProcess(argv, result.returncode, None, "")
        return subprocess.CompletedProcess(argv, result.returncode, result.stdout, "")

    def when(self, *words: str, rc: int = 0, out: str = "") -> None:
        def rule(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
            return _done(rc, out) if all(w in argv for w in words) else None

        self.rules.append(rule)

    def sequence(self, word: str, results: list[tuple[int, str]]) -> None:
        queue = list(results)

        def rule(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
            if word in argv and queue:
                rc, out = queue.pop(0) if len(queue) > 1 else queue[0]
                return _done(rc, out)
            return None

        self.rules.append(rule)

    def xcodebuild(self) -> list[list[str]]:
        return [
            c
            for c in self.calls
            if "xcodebuild" in c and "xcresulttool" not in c and "-version" not in c
        ]

    def with_words(self, *words: str) -> list[list[str]]:
        return [c for c in self.calls if all(w in c for w in words)]


class App:
    def __init__(self, root: Path, mp: pytest.MonkeyPatch, runner: Runner) -> None:
        self.root = root
        self.results = root / "results"
        self.results.mkdir()
        (self.results / "simulator.txt").write_text(_UDID + "\n")
        self.mp = mp
        self.runner = runner
        mp.chdir(root)
        self.env()

    def env(
        self,
        scope: str = "",
        adopt: bool = False,
        settings: dict[str, object] | None = None,
    ) -> None:
        mp = self.mp
        mp.setenv("BULL_PART", "app")
        mp.setenv("BULL_PART_ROOT", str(self.root))
        mp.setenv("BULL_APP_ROOT", str(self.root))
        mp.setenv("BULL_RESULTS", str(self.results))
        mp.setenv("BULL_STACK_DIR", str(_STACK_DIR))
        mp.setenv("BULL_ADOPT_MODE", "1" if adopt else "0")
        mp.setenv("BULL_SCOPE_MODULE", scope)
        data: dict[str, object] = {
            "project": "App/Demo/Demo.xcodeproj",
            "scheme": "Demo",
            "source_dir": _SRC,
            "test_dir": _TESTS,
            "ui_test_dir": "App/Demo/DemoUITests",
            "unit_test_target": "DemoTests",
            "ui_test_target": "DemoUITests",
            "simulator": "iPhone 16",
        }
        data.update(settings or {})
        mp.setenv("BULL_SETTINGS", json.dumps(data))

    def write(self, rel: str, text: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def log(self, step: str) -> str:
        return (self.results / f"{step}.log").read_text()


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    runner = Runner()
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    root = tmp_path / "part"
    root.mkdir()
    return App(root, monkeypatch, runner)


def _out(capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    return captured.out + captured.err


def _after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def _only(argv: list[str]) -> list[str]:
    return [a for a in argv if a.startswith("-only-testing:")]


def _labels(text: str) -> list[str]:
    return [
        line.split("bull-fail:", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("bull-fail:")
    ]


# --- dispatch ------------------------------------------------------------------------------


def test_main_without_arguments_is_a_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main([]) != 0
    assert "usage" in _out(capsys).lower()


def test_main_unknown_step_is_a_usage_error(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gates.main(["bogus"]) != 0
    assert "usage" in _out(capsys).lower()


# --- preflight -----------------------------------------------------------------------------


def _simctl_listing(*devices: tuple[str, str, str]) -> str:
    rt = "com.apple.CoreSimulator.SimRuntime."
    listing: dict[str, list[dict[str, object]]] = {}
    for runtime, udid, name in devices:
        listing.setdefault(rt + runtime, []).append(
            {"udid": udid, "name": name, "isAvailable": True}
        )
    return json.dumps({"devices": listing})


def test_preflight_stores_the_chosen_udid(app: App) -> None:
    (app.results / "simulator.txt").unlink()
    app.runner.when("simctl", out=_simctl_listing(("iOS-18-2", "CHOSEN", "iPhone 16")))
    assert gates.main(["preflight"]) == 0
    assert (app.results / "simulator.txt").read_text().strip() == "CHOSEN"


def test_preflight_with_empty_setting_takes_the_newest_iphone(app: App) -> None:
    (app.results / "simulator.txt").unlink()
    app.env(settings={"simulator": ""})
    app.runner.when(
        "simctl",
        out=_simctl_listing(
            ("iOS-17-5", "OLD", "iPhone 15"), ("iOS-18-2", "NEW", "iPhone 16")
        ),
    )
    assert gates.main(["preflight"]) == 0
    assert (app.results / "simulator.txt").read_text().strip() == "NEW"


def test_preflight_exits_2_naming_the_setting_when_none_match(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    (app.results / "simulator.txt").unlink()
    app.env(settings={"simulator": "iPhone 99"})
    app.runner.when("simctl", out=_simctl_listing(("iOS-18-2", "A", "iPhone 16")))
    assert gates.main(["preflight"]) == 2
    assert "simulator" in _out(capsys)


# --- setup ---------------------------------------------------------------------------------


def test_setup_succeeds_when_the_tools_succeed(app: App) -> None:
    assert gates.main(["setup"]) == 0


def test_setup_fails_when_a_tool_fails(app: App) -> None:
    app.runner.when("xcodebuild", rc=1, out="error: no such project")
    app.runner.when("simctl", rc=1, out="error")
    assert gates.main(["setup"]) != 0


# --- xcodebuild arguments ------------------------------------------------------------------


def test_build_test_passes_the_standard_arguments(app: App) -> None:
    assert gates.main(["build-test"]) == 0
    calls = app.runner.xcodebuild()
    assert len(calls) == 1
    argv = calls[0]
    assert "test" in argv
    assert _after(argv, "-project") == "App/Demo/Demo.xcodeproj"
    assert _after(argv, "-scheme") == "Demo"
    assert argv.count("-destination") == 1
    assert _after(argv, "-destination") == f"id={_UDID}"
    assert _after(argv, "-parallel-testing-enabled") == "NO"
    derived = _after(argv, "-derivedDataPath")
    assert derived.rstrip("/").endswith(".bull/build/DerivedData")
    assert _after(argv, "-resultBundlePath") == str(app.results / "build-test.xcresult")
    assert _after(argv, "-collect-test-diagnostics") == "on-failure"


def test_build_test_runs_the_unit_test_target_only(app: App) -> None:
    gates.main(["build-test"])
    assert _only(app.runner.xcodebuild()[0]) == ["-only-testing:DemoTests"]


def test_build_test_uses_swift_6_with_warnings_as_errors(app: App) -> None:
    gates.main(["build-test"])
    argv = app.runner.xcodebuild()[0]
    assert "SWIFT_VERSION=6" in argv
    assert "SWIFT_TREAT_WARNINGS_AS_ERRORS=YES" in argv


def test_adopt_mode_keeps_the_language_mode_and_allows_warnings(app: App) -> None:
    app.env(adopt=True)
    gates.main(["build-test"])
    argv = app.runner.xcodebuild()[0]
    assert not any(a.startswith("SWIFT_VERSION") for a in argv)
    assert "SWIFT_TREAT_WARNINGS_AS_ERRORS=YES" not in argv
    assert "SWIFT_STRICT_CONCURRENCY=complete" in argv


def test_build_test_with_a_scope_runs_only_that_modules_suites(app: App) -> None:
    app.write(
        f"{_TESTS}/Counter/StoreTests.swift",
        "import Testing\n@Suite struct StoreTests {\n  @Test func a() {}\n}\n",
    )
    app.write(
        f"{_TESTS}/Other/OtherTests.swift",
        "import Testing\n@Suite struct OtherTests {\n}\n",
    )
    app.env(scope="Counter")
    gates.main(["build-test"])
    assert _only(app.runner.xcodebuild()[0]) == ["-only-testing:DemoTests/StoreTests"]


def test_the_chosen_simulator_is_read_from_simulator_txt(app: App) -> None:
    (app.results / "simulator.txt").write_text("OTHER-UDID\n")
    gates.main(["build-test"])
    assert _after(app.runner.xcodebuild()[0], "-destination") == "id=OTHER-UDID"


# --- build-test-fast: suite discovery ------------------------------------------------------


def test_fast_runs_the_modules_top_level_suites(app: App) -> None:
    app.write(
        f"{_TESTS}/Counter/StoreTests.swift",
        "import Testing\n"
        "@Suite struct StoreTests {\n  @Test func a() {}\n}\n"
        "final class LegacyTests {\n}\n"
        "actor ActorTests {\n}\n",
    )
    assert gates.main(["build-test-fast", "Counter"]) == 0
    argv = app.runner.xcodebuild()[0]
    assert sorted(_only(argv)) == [
        "-only-testing:DemoTests/ActorTests",
        "-only-testing:DemoTests/LegacyTests",
        "-only-testing:DemoTests/StoreTests",
    ]
    assert _after(argv, "-resultBundlePath") == str(
        app.results / "build-test-fast.xcresult"
    )


def test_fast_finds_a_suite_by_attribute_when_the_name_has_no_tests_suffix(
    app: App,
) -> None:
    app.write(
        f"{_TESTS}/Counter/Misc.swift",
        '@Suite("Counting")\nstruct Counting {\n}\n',
    )
    gates.main(["build-test-fast", "Counter"])
    assert _only(app.runner.xcodebuild()[0]) == ["-only-testing:DemoTests/Counting"]


def test_fast_ignores_nested_suites_and_helpers(app: App) -> None:
    app.write(
        f"{_TESTS}/Counter/StoreTests.swift",
        "@Suite struct StoreTests {\n"
        "    struct NestedTests {\n    }\n"
        "}\n"
        "struct Helper {\n}\n",
    )
    gates.main(["build-test-fast", "Counter"])
    assert _only(app.runner.xcodebuild()[0]) == ["-only-testing:DemoTests/StoreTests"]


def test_fast_ignores_other_modules_suites(app: App) -> None:
    app.write(f"{_TESTS}/Counter/ATests.swift", "struct AATests {\n}\n")
    app.write(f"{_TESTS}/Other/BTests.swift", "struct BBTests {\n}\n")
    gates.main(["build-test-fast", "Counter"])
    assert _only(app.runner.xcodebuild()[0]) == ["-only-testing:DemoTests/AATests"]


# --- rerun ---------------------------------------------------------------------------------


def test_rerun_runs_each_failed_id(app: App) -> None:
    ids = ["StoreTests/adds()", "StoreTests/removes()"]
    assert gates.main(["rerun", *ids]) == 0
    argv = app.runner.xcodebuild()[0]
    assert sorted(_only(argv)) == [
        "-only-testing:DemoTests/StoreTests/adds()",
        "-only-testing:DemoTests/StoreTests/removes()",
    ]
    assert _after(argv, "-resultBundlePath") == str(app.results / "rerun.xcresult")


# --- busy simulator ------------------------------------------------------------------------


def test_a_busy_simulator_failure_is_retried(app: App) -> None:
    app.runner.sequence("xcodebuild", [(65, _BUSY), (0, "** TEST SUCCEEDED **")])
    assert gates.main(["build-test"]) == 0
    assert len(app.runner.xcodebuild()) == 2


def test_busy_retries_stop_after_three_attempts(app: App) -> None:
    app.runner.when("xcodebuild", rc=65, out=_BUSY)
    assert gates.main(["build-test"]) != 0
    assert len(app.runner.xcodebuild()) == 3


def test_other_failures_are_not_retried(app: App) -> None:
    app.runner.when("xcodebuild", rc=65, out="Test Case 'x' failed")
    assert gates.main(["build-test"]) != 0
    assert len(app.runner.xcodebuild()) == 1


# --- output: log and filtered tail ---------------------------------------------------------


_NOISE = [
    "2026-01-01 xcodebuild[1:2] [MT] IDETestOperationsObserverDebug: 3.2 elapsed",
    "Writing diagnostic log for test session to: /tmp/x.xcresult/diag",
    "--- xcodebuild: WARNING: Using the first of multiple matching destinations:",
]


@pytest.mark.parametrize("noise", _NOISE)
def test_launch_noise_is_hidden_from_the_tail_but_kept_in_the_log(
    app: App, capsys: pytest.CaptureFixture[str], noise: str
) -> None:
    app.runner.when("xcodebuild", rc=65, out=f"{noise}\nreal failure line\n")
    gates.main(["build-test"])
    shown = _out(capsys)
    assert noise not in shown
    assert "real failure line" in shown
    log = app.log("build-test")
    assert noise in log
    assert "real failure line" in log


def test_the_whole_output_goes_to_the_log(app: App) -> None:
    app.runner.when("xcodebuild", rc=0, out="line one\nline two\n")
    gates.main(["build-test"])
    log = app.log("build-test")
    assert "line one" in log and "line two" in log


# --- diagnostics ---------------------------------------------------------------------------


def test_diagnostics_are_collected_only_on_failure_for_every_test_step(
    app: App,
) -> None:
    app.write(f"{_TESTS}/Counter/StoreTests.swift", "struct StoreTests {\n}\n")
    gates.main(["build-test-fast", "Counter"])
    gates.main(["rerun", "StoreTests/a()"])
    gates.main(["journeys"])
    calls = app.runner.xcodebuild()
    assert len(calls) == 3
    assert all(_after(c, "-collect-test-diagnostics") == "on-failure" for c in calls)


# --- journeys ------------------------------------------------------------------------------


def test_journeys_run_the_ui_test_target(app: App) -> None:
    assert gates.main(["journeys"]) == 0
    argv = app.runner.xcodebuild()[0]
    assert _only(argv) == ["-only-testing:DemoUITests"]
    assert _after(argv, "-resultBundlePath") == str(app.results / "journeys.xcresult")
    assert _after(argv, "-destination") == f"id={_UDID}"


def test_journeys_pass_service_urls_to_the_test_runner(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BULL_URL_API", "http://127.0.0.1:8123")
    gates.main(["journeys"])
    call = app.runner.xcodebuild()[0]
    kw = app.runner.kwargs[app.runner.calls.index(call)]
    env = kw.get("env") or {}
    assert (
        env.get("TEST_RUNNER_BULL_URL_API") == "http://127.0.0.1:8123"
        or "TEST_RUNNER_BULL_URL_API=http://127.0.0.1:8123" in call
    )


def test_journeys_keep_screenshots_only_for_failures(app: App) -> None:
    app.runner.when("xcodebuild", rc=65, out="UI test failed")
    assert gates.main(["journeys"]) != 0
    exports = app.runner.with_words("xcresulttool", "export", "attachments")
    assert exports
    assert all("--only-failures" in c for c in exports)


def test_failing_journeys_report_a_label(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when("xcodebuild", rc=65, out="UI test failed")
    gates.main(["journeys"])
    assert _labels(_out(capsys))


# --- failures and labels -------------------------------------------------------------------


def test_a_failing_run_exits_non_zero_with_a_label(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when("xcodebuild", rc=65, out="Test Case 'x' failed")
    assert gates.main(["build-test"]) != 0
    assert _labels(_out(capsys))


def test_a_compile_error_is_labelled_with_file_and_line(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    out = (
        f"{app.root}/{_SRC}/Modules/Counter/Store.swift:14:9: error: cannot find 'x'\n"
    )
    app.runner.when("xcodebuild", rc=65, out=out)
    assert gates.main(["build-test"]) != 0
    assert any("Store.swift:14" in label for label in _labels(_out(capsys)))


def test_a_passing_run_prints_no_labels(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.runner.when("xcodebuild", rc=0, out="** TEST SUCCEEDED **")
    assert gates.main(["build-test"]) == 0
    assert _labels(_out(capsys)) == []


# --- adopt-mode warnings -------------------------------------------------------------------


def _warning(app: App, rel: str, line: int) -> str:
    return f"{app.root}/{rel}:{line}:5: warning: variable was never mutated\n"


def test_adopt_warning_in_modules_fails_the_build(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.env(adopt=True)
    out = _warning(app, f"{_SRC}/Modules/Counter/Store.swift", 12)
    app.runner.when("xcodebuild", rc=0, out=out)
    assert gates.main(["build-test"]) != 0
    labels = _labels(_out(capsys))
    assert any("warning" in lb and "Store.swift:12" in lb for lb in labels)


def test_adopt_warning_in_a_module_test_folder_fails_the_build(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.env(adopt=True)
    out = _warning(app, f"{_TESTS}/Counter/StoreTests.swift", 7)
    app.runner.when("xcodebuild", rc=0, out=out)
    assert gates.main(["build-test"]) != 0
    assert any("StoreTests.swift:7" in lb for lb in _labels(_out(capsys)))


def test_adopt_warning_in_legacy_code_does_not_fail_the_build(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    app.env(adopt=True)
    out = _warning(app, f"{_SRC}/Legacy/Old.swift", 3)
    app.runner.when("xcodebuild", rc=0, out=out)
    assert gates.main(["build-test"]) == 0
    assert _labels(_out(capsys)) == []


def test_adopt_warning_still_shows_in_the_log(app: App) -> None:
    app.env(adopt=True)
    out = _warning(app, f"{_SRC}/Legacy/Old.swift", 3)
    app.runner.when("xcodebuild", rc=0, out=out)
    gates.main(["build-test"])
    assert "Old.swift:3" in app.log("build-test")


# --- lint ----------------------------------------------------------------------------------


def _lint_folders(app: App) -> None:
    app.write(f"{_SRC}/Modules/Counter/Store.swift", "struct Store {}\n")
    app.write(f"{_TESTS}/Counter/StoreTests.swift", "struct StoreTests {}\n")


def test_lint_runs_swiftlint_strict_on_source_and_test_folders(app: App) -> None:
    _lint_folders(app)
    assert gates.main(["lint", "Counter"]) == 0
    calls = app.runner.with_words("swiftlint")
    assert len(calls) == 1
    argv = calls[0]
    assert "lint" in argv and "--strict" in argv
    joined = " ".join(argv)
    assert f"{_SRC}/Modules/Counter" in joined
    assert f"{_TESTS}/Counter" in joined


def test_lint_runs_swift_format_strict_on_source_and_test_folders(app: App) -> None:
    _lint_folders(app)
    gates.main(["lint", "Counter"])
    calls = app.runner.with_words("swift-format")
    assert len(calls) == 1
    argv = calls[0]
    assert "xcrun" in argv
    assert "lint" in argv and "--strict" in argv
    joined = " ".join(argv)
    assert f"{_SRC}/Modules/Counter" in joined
    assert f"{_TESTS}/Counter" in joined


def test_lint_uses_the_stacks_configs_when_the_app_has_none(app: App) -> None:
    _lint_folders(app)
    gates.main(["lint", "Counter"])
    swiftlint = app.runner.with_words("swiftlint")[0]
    fmt = app.runner.with_words("swift-format")[0]
    assert _after(swiftlint, "--config") == str(_STACK_DIR / "lint" / "swiftlint.yml")
    assert _after(fmt, "--configuration") == str(
        _STACK_DIR / "lint" / "swift-format.json"
    )


def test_lint_prefers_the_apps_own_configs_at_the_part_root(app: App) -> None:
    _lint_folders(app)
    own_lint = app.write(".swiftlint.yml", "disabled_rules: []\n")
    own_fmt = app.write(".swift-format", "{}\n")
    gates.main(["lint", "Counter"])
    swiftlint = app.runner.with_words("swiftlint")[0]
    fmt = app.runner.with_words("swift-format")[0]
    assert Path(_after(swiftlint, "--config")).resolve() == own_lint.resolve()
    assert Path(_after(fmt, "--configuration")).resolve() == own_fmt.resolve()


def test_lint_failures_become_labels_naming_file_and_line(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    _lint_folders(app)
    path = f"{app.root}/{_SRC}/Modules/Counter/Store.swift"
    app.runner.when(
        "swiftlint",
        rc=2,
        out=f"{path}:12:3: error: Line Length Violation (line_length)\n",
    )
    assert gates.main(["lint", "Counter"]) != 0
    labels = _labels(_out(capsys))
    assert any(lb.startswith("lint") and "Store.swift:12" in lb for lb in labels)


def test_swift_format_failures_become_labels_too(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    _lint_folders(app)
    path = f"{app.root}/{_TESTS}/Counter/StoreTests.swift"
    app.runner.when(
        "swift-format", rc=1, out=f"{path}:5:1: error: [Indentation] use 4 spaces\n"
    )
    assert gates.main(["lint", "Counter"]) != 0
    assert any("StoreTests.swift:5" in lb for lb in _labels(_out(capsys)))


def test_lint_failing_without_parsable_output_still_fails(app: App) -> None:
    _lint_folders(app)
    app.runner.when("swiftlint", rc=1, out="boom")
    assert gates.main(["lint", "Counter"]) != 0


def test_lint_without_a_module_is_a_usage_error(app: App) -> None:
    assert gates.main(["lint"]) != 0


# --- prune ---------------------------------------------------------------------------------


def test_prune_deletes_the_build_folder_and_result_bundles(app: App) -> None:
    app.write(".bull/build/DerivedData/Products/x.o", "x")
    (app.results / "build-test.xcresult").mkdir()
    (app.results / "build-test.xcresult" / "data").write_text("d")
    (app.results / "journeys.xcresult").mkdir()
    assert gates.main(["prune"]) == 0
    assert not (app.root / ".bull" / "build").exists()
    assert not (app.results / "build-test.xcresult").exists()
    assert not (app.results / "journeys.xcresult").exists()


def test_prune_leaves_other_results_alone(app: App) -> None:
    (app.results / "build-test.log").write_text("log")
    (app.results / "old.xcresult").mkdir()
    gates.main(["prune"])
    assert (app.results / "simulator.txt").exists()
    assert (app.results / "build-test.log").exists()


def test_prune_with_nothing_to_delete_succeeds(app: App) -> None:
    assert gates.main(["prune"]) == 0


# --- review findings: coverage, stale bundles, exit-0 errors, empty modules -----------------


def _run_step(app: App, step: str) -> None:
    if step == "build-test":
        gates.main(["build-test"])
    elif step == "build-test-fast":
        app.write(f"{_TESTS}/Counter/StoreTests.swift", "struct StoreTests {\n}\n")
        gates.main(["build-test-fast", "Counter"])
    else:
        gates.main(["rerun", "StoreTests/a()"])


_UNIT_STEPS = ["build-test", "build-test-fast", "rerun"]


@pytest.mark.parametrize("step", _UNIT_STEPS)
def test_unit_test_runs_enable_code_coverage(app: App, step: str) -> None:
    _run_step(app, step)
    argv = app.runner.xcodebuild()[0]
    assert _after(argv, "-enableCodeCoverage") == "YES"


@pytest.mark.parametrize("step", _UNIT_STEPS)
def test_an_old_journeys_bundle_is_removed_before_a_unit_test_run(
    app: App, step: str
) -> None:
    stale = app.results / "journeys.xcresult"
    stale.mkdir()
    (stale / "data").write_text("old")
    _run_step(app, step)
    assert not stale.exists()


def test_a_compile_error_line_in_a_run_that_exits_zero_passes_with_no_labels(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    out = (
        f"{app.root}/{_SRC}/Modules/Counter/Store.swift:14:9: error: cannot find 'x'\n"
    )
    app.runner.when("xcodebuild", rc=0, out=out)
    assert gates.main(["build-test"]) == 0
    assert _labels(_out(capsys)) == []


def test_fast_for_a_module_without_suites_says_so_and_names_the_test_folder(
    app: App, capsys: pytest.CaptureFixture[str]
) -> None:
    gates.main(["build-test-fast", "Counter"])
    shown = _out(capsys)
    line = next(ln for ln in shown.splitlines() if "no test suites found" in ln)
    assert f"{_TESTS}/Counter" in line
