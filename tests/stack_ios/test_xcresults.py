"""Tests for `bull.Modules.stack_ios.ios.xcresults` and the readers that pass through to it.

`subprocess.run` is replaced by a fake that answers `xcrun xcresulttool` and `xcrun xccov`
(no real Xcode tool runs). Choices where the spec is open (the code must match these):
- Bundles are `*.xcresult` directories in the results folder; none -> `test_results` is None
  and every source is `no_data`. Tests use one bundle (`build-test.xcresult`).
- Tests come from `xcresulttool get test-results tests --path <bundle>` (Xcode 16/26 JSON):
  `{"testNodes": [...]}`, a tree of `{nodeType, name, nodeIdentifier, result, children}`. Every
  `Test Case` node is a test; a failed one (`result == "Failed"`) puts its `nodeIdentifier`
  (`Suite/test()`) in `failed`, in tree order. A `Unit test bundle` node that failed with no
  `Test Case` below it is a runner that failed to launch: not a test, not in `failed`.
- Coverage: `xccov view --report --json <bundle>` gives `{"targets": [{"files": [{"path":
  <path recorded at build time>, ...}]}]}`; a source is matched to the recorded path ending in
  its part-root-relative path; the lines come from `xccov view --archive --file <recorded path>
  --json <bundle>` -> `{<path>: [{"line", "isExecutable", "executionCount"}]}`; uncovered =
  executable lines with count 0, ascending. A source with no recorded path is in `no_data`; one
  with none uncovered is in neither `uncovered` nor `no_data` (or maps to `()`).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.stack_ios.ios import readers, xcresults
from bull.Modules.stacks.Contracts import TestRun


def _case(ident: str, result: str = "Passed") -> dict[str, Any]:
    return {
        "nodeType": "Test Case",
        "name": ident.split("/")[-1],
        "nodeIdentifier": ident,
        "result": result,
    }


def _tree(
    *cases: dict[str, Any], extra: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    suite = {"nodeType": "Test Suite", "name": "Suite", "children": list(cases)}
    bundle = {
        "nodeType": "Unit test bundle",
        "name": "DemoTests",
        "result": "Passed",
        "children": [suite],
    }
    return {
        "testNodes": [
            {
                "nodeType": "Test Plan",
                "name": "Demo",
                "children": [bundle, *(extra or [])],
            }
        ]
    }


class Tools:
    """Fake `subprocess.run` for xcresulttool and xccov; records every call."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.tests: dict[str, Any] = {"testNodes": []}
        self.report: dict[str, Any] = {"targets": []}
        self.lines: dict[str, list[dict[str, Any]]] = {}

    def __call__(self, args: Any, *a: object, **kw: object) -> object:
        argv = [str(x) for x in args]
        self.calls.append(argv)
        if "xcresulttool" in argv:
            out = json.dumps(self.tests)
        elif "xccov" in argv and "--report" in argv:
            out = json.dumps(self.report)
        elif "xccov" in argv and "--archive" in argv:
            path = argv[argv.index("--file") + 1]
            out = json.dumps({path: self.lines.get(path, [])})
        else:
            out = ""
        return subprocess.CompletedProcess(argv, 0, out, "")


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> Tools:
    fake = Tools()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


@pytest.fixture
def results(tmp_path: Path) -> Path:
    folder = tmp_path / "results"
    (folder / "build-test.xcresult").mkdir(parents=True)
    return folder


# --- test_results --------------------------------------------------------------------------


def test_missing_bundle_gives_none(tools: Tools, tmp_path: Path) -> None:
    empty = tmp_path / "results"
    empty.mkdir()
    assert xcresults.test_results(empty) is None
    assert tools.calls == []


def test_missing_results_folder_gives_none(tools: Tools, tmp_path: Path) -> None:
    assert xcresults.test_results(tmp_path / "nowhere") is None


def test_count_is_the_number_of_test_cases(tools: Tools, results: Path) -> None:
    tools.tests = _tree(_case("S/a()"), _case("S/b()"), _case("S/c()"))
    run = xcresults.test_results(results)
    assert run == TestRun(count=3, failed=())


def test_failed_ids_are_the_failed_test_cases_in_order(
    tools: Tools, results: Path
) -> None:
    tools.tests = _tree(
        _case("S/a()"), _case("S/b()", "Failed"), _case("T/c()", "Failed")
    )
    run = xcresults.test_results(results)
    assert run is not None
    assert run.count == 3
    assert run.failed == ("S/b()", "T/c()")


def test_nested_suites_are_walked(tools: Tools, results: Path) -> None:
    inner = {
        "nodeType": "Test Suite",
        "name": "Inner",
        "children": [_case("Outer/Inner/x()", "Failed")],
    }
    outer = {
        "nodeType": "Test Suite",
        "name": "Outer",
        "children": [inner, _case("Outer/y()")],
    }
    tools.tests = _tree(outer)
    run = xcresults.test_results(results)
    assert run == TestRun(count=2, failed=("Outer/Inner/x()",))


def test_empty_bundle_counts_zero_tests(tools: Tools, results: Path) -> None:
    tools.tests = {"testNodes": []}
    assert xcresults.test_results(results) == TestRun(count=0, failed=())


def test_a_runner_that_failed_to_launch_is_not_a_test(
    tools: Tools, results: Path
) -> None:
    crashed = {
        "nodeType": "Unit test bundle",
        "name": "OtherTests",
        "result": "Failed",
        "children": [{"nodeType": "Failure Message", "name": "Failed to launch"}],
    }
    tools.tests = _tree(_case("S/a()"), _case("S/b()"), extra=[crashed])
    run = xcresults.test_results(results)
    assert run == TestRun(count=2, failed=())


def test_the_bundle_path_is_passed_to_xcresulttool(tools: Tools, results: Path) -> None:
    tools.tests = _tree(_case("S/a()"))
    xcresults.test_results(results)
    call = tools.calls[0]
    assert "xcresulttool" in call
    assert str(results / "build-test.xcresult") in call


# --- uncovered -----------------------------------------------------------------------------


def _line(n: int, executable: bool, count: int) -> dict[str, Any]:
    return {"line": n, "isExecutable": executable, "executionCount": count}


@pytest.fixture
def part(tmp_path: Path) -> Path:
    root = tmp_path / "part"
    root.mkdir()
    return root


def test_uncovered_lines_are_executable_lines_never_executed(
    tools: Tools, results: Path, part: Path
) -> None:
    source = part / "App/Demo/Modules/Counter/Store.swift"
    recorded = "/ci/checkout/App/Demo/Modules/Counter/Store.swift"
    tools.report = {"targets": [{"files": [{"path": recorded}]}]}
    tools.lines[recorded] = [
        _line(1, False, 0),
        _line(2, True, 5),
        _line(3, True, 0),
        _line(4, False, 0),
        _line(7, True, 0),
    ]
    data = xcresults.uncovered(part, [source], results)
    assert data.uncovered[source] == (3, 7)
    assert data.no_data == ()


def test_xccov_is_asked_for_the_path_the_bundle_recorded(
    tools: Tools, results: Path, part: Path
) -> None:
    source = part / "App/Demo/Modules/Counter/Store.swift"
    recorded = "/somewhere/else/App/Demo/Modules/Counter/Store.swift"
    tools.report = {"targets": [{"files": [{"path": recorded}]}]}
    tools.lines[recorded] = [_line(1, True, 0)]
    xcresults.uncovered(part, [source], results)
    asked = [c[c.index("--file") + 1] for c in tools.calls if "--file" in c]
    assert asked == [recorded]
    assert str(source) not in asked


def test_source_absent_from_the_data_is_no_data(
    tools: Tools, results: Path, part: Path
) -> None:
    covered = part / "App/Demo/Modules/Counter/Store.swift"
    missing = part / "App/Demo/Modules/Counter/Other.swift"
    recorded = "/ci/App/Demo/Modules/Counter/Store.swift"
    tools.report = {"targets": [{"files": [{"path": recorded}]}]}
    tools.lines[recorded] = [_line(1, True, 1)]
    data = xcresults.uncovered(part, [covered, missing], results)
    assert data.no_data == (missing,)
    assert missing not in data.uncovered
    assert data.uncovered.get(covered, ()) == ()


def test_fully_covered_source_has_no_uncovered_lines(
    tools: Tools, results: Path, part: Path
) -> None:
    source = part / "App/Demo/Modules/Counter/Store.swift"
    recorded = "/ci/App/Demo/Modules/Counter/Store.swift"
    tools.report = {"targets": [{"files": [{"path": recorded}]}]}
    tools.lines[recorded] = [_line(1, True, 2), _line(2, True, 1)]
    data = xcresults.uncovered(part, [source], results)
    assert data.uncovered.get(source, ()) == ()
    assert source not in data.no_data


def test_no_bundle_means_every_source_is_no_data(
    tools: Tools, tmp_path: Path, part: Path
) -> None:
    empty = tmp_path / "results"
    empty.mkdir()
    sources = [part / "A.swift", part / "B.swift"]
    data = xcresults.uncovered(part, sources, empty)
    assert set(data.no_data) == set(sources)
    assert dict(data.uncovered) == {}


def test_no_sources_asks_for_nothing(tools: Tools, results: Path, part: Path) -> None:
    data = xcresults.uncovered(part, [], results)
    assert data.no_data == ()
    assert dict(data.uncovered) == {}


# --- readers pass-through ------------------------------------------------------------------


def test_readers_test_results_passes_through_to_xcresults(
    tools: Tools, results: Path
) -> None:
    tools.tests = _tree(_case("S/a()"), _case("S/b()", "Failed"))
    assert readers.test_results(results) == xcresults.test_results(results)
    assert readers.test_results(results) == TestRun(count=2, failed=("S/b()",))


def test_readers_test_results_without_a_bundle_is_none(
    tools: Tools, tmp_path: Path
) -> None:
    assert readers.test_results(tmp_path) is None


def test_readers_uncovered_passes_through_to_xcresults(
    tools: Tools, results: Path, part: Path
) -> None:
    source = part / "App/Store.swift"
    recorded = "/ci/App/Store.swift"
    tools.report = {"targets": [{"files": [{"path": recorded}]}]}
    tools.lines[recorded] = [_line(4, True, 0)]
    data = readers.uncovered(part, [source], results)
    assert data == xcresults.uncovered(part, [source], results)
    assert data.uncovered[source] == (4,)
