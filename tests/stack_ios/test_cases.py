"""Tests for the ios stack's `cases.json` (its self-test cases and fixture layout)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

import pytest

import bull.Modules.stack_ios as pkg
from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacks.registry import LiveStackRegistry
from bull.Modules.stacktest.Contracts import Case
from bull.Modules.stacktest.runner import LiveStackTester
from bull.Modules.stacktest.static import static

_FOLDER = Path(pkg.__file__).parent / "ios"
_CASES = _FOLDER / "cases.json"
_FIXTURE = _FOLDER / "fixture"
_BULL = (sys.executable, "-m", "bull")

_REQUIRED_IDS = {
    "clean",
    "fast",
    "no-tests",
    "failing-test",
    "build-warning",
    "lint",
    "contract-change",
    "uncovered",
    "exemption",
    "setup-broken",
    "journey",
    "journey-failing",
    "adopt-mode",
}

_LAYOUT = {
    "project/": ".",
    "app/": "App/Fixture/Fixture/",
    "tests/": "App/Fixture/FixtureTests/",
    "ui-tests/": "App/Fixture/FixtureUITests/",
}
_SETTINGS = {
    "project": "App/Fixture/Fixture.xcodeproj",
    "scheme": "Fixture",
    "source_dir": "App/Fixture/Fixture",
    "test_dir": "App/Fixture/FixtureTests",
    "ui_test_dir": "App/Fixture/FixtureUITests",
    "unit_test_target": "FixtureTests",
    "ui_test_target": "FixtureUITests",
}

_COUNTER = "App/Fixture/Fixture/Modules/Counter/Counter.swift"
_STORE = "App/Fixture/Fixture/Modules/Counter/Contracts/CounterStore.swift"
_TESTS = "App/Fixture/FixtureTests/Counter/CounterTests.swift"
_JOURNEY = "App/Fixture/FixtureUITests/JourneyTests.swift"
_SCHEME = "App/Fixture/Fixture.xcodeproj/xcshareddata/xcschemes/Fixture.xcscheme"


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    return LiveStackRegistry([], tmp_path_factory.mktemp("userdata")).load_path(_FOLDER)


@pytest.fixture(scope="module")
def cases(stack: Stack) -> list[Case]:
    return LiveStackTester(_BULL).load_cases(stack)


@pytest.fixture(scope="module")
def raw() -> dict[str, object]:
    data = json.loads(_CASES.read_text())
    assert isinstance(data, dict)
    return data


def _case(cases: list[Case], case_id: str) -> Case:
    return next(c for c in cases if c.id == case_id)


def _change(case: Case, kind: str) -> dict[str, str]:
    value = case.change.get(kind, {})
    return dict(cast("dict[str, str]", value))


def _source_of(path: str) -> Path | None:
    """The fixture file an app-relative path comes from, by the layout (longest folder wins)."""
    best: tuple[str, str] | None = None
    for source, dest in _LAYOUT.items():
        prefix = "" if dest == "." else dest
        if path.startswith(prefix) and (best is None or len(prefix) > len(best[1])):
            best = (source, prefix)
    if best is None:
        return None
    return _FIXTURE / best[0] / path[len(best[1]) :]


def test_cases_json_declares_format_1(raw: dict[str, object]) -> None:
    assert raw["format"] == 1


def test_cases_json_loads_through_load_cases(cases: list[Case]) -> None:
    assert cases


def test_layout_maps_the_four_fixture_folders(raw: dict[str, object]) -> None:
    assert raw["layout"] == _LAYOUT


def test_settings_point_at_the_fixture_xcode_project(raw: dict[str, object]) -> None:
    assert raw["settings"] == _SETTINGS


def test_cases_cover_every_required_id(cases: list[Case]) -> None:
    assert _REQUIRED_IDS <= {c.id for c in cases}


def test_cases_omit_interface_drift_because_there_are_no_interfaces(
    cases: list[Case],
) -> None:
    assert "interface-drift" not in {c.id for c in cases}


def test_case_ids_are_unique(cases: list[Case]) -> None:
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))


def test_every_case_runs_a_bull_command(cases: list[Case]) -> None:
    assert all(c.run for c in cases)


def test_static_check_reports_no_problems_for_the_ios_stack(stack: Stack) -> None:
    report = static(stack)
    assert report.problems == ()
    assert report.ok


def test_clean_case_expects_a_recorded_pass(cases: list[Case]) -> None:
    case = _case(cases, "clean")
    assert case.run[:2] == ("gates", "Counter")
    assert "--fast" not in case.run
    assert case.expect["verdict"] == "pass"
    assert case.expect["recorded"] is True
    assert not case.change


def test_fast_case_runs_the_fast_gates_and_expects_an_unrecorded_pass(
    cases: list[Case],
) -> None:
    case = _case(cases, "fast")
    assert case.run == ("gates", "Counter", "--fast")
    assert case.expect["verdict"] == "pass"
    assert case.expect["recorded"] is False
    assert not case.change


def test_no_tests_case_empties_the_test_file_down_to_the_import(
    cases: list[Case],
) -> None:
    case = _case(cases, "no-tests")
    text = _change(case, "replace")[_TESTS]
    assert "import Testing" in text
    assert "@Test" not in text
    assert "@Suite" not in text
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "tests"
    assert "no tests ran" in str(case.expect["output"])


def test_failing_test_case_fails_the_tests_gate_naming_a_test(
    cases: list[Case],
) -> None:
    case = _case(cases, "failing-test")
    assert _TESTS in _change(case, "replace")
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "tests"
    assert str(case.expect["output"])


def test_failing_test_case_has_a_then_step_rerunning_one_failed_test(
    cases: list[Case],
) -> None:
    case = _case(cases, "failing-test")
    assert case.then is not None
    assert case.then.run[:2] == ("gates", "--failed")
    assert case.then.expect["verdict"] == "fail"
    assert case.then.expect["ran"] == 1


def test_build_warning_case_adds_an_unused_let_and_fails_the_build_gate(
    cases: list[Case],
) -> None:
    case = _case(cases, "build-warning")
    text = _change(case, "replace")[_COUNTER]
    assert "let " in text
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "build"
    assert "Counter.swift" in str(case.expect["output"])


def test_lint_case_forces_a_try_or_cast_in_counter_and_fails_lint(
    cases: list[Case],
) -> None:
    case = _case(cases, "lint")
    text = _change(case, "replace")[_COUNTER]
    assert "try!" in text or "as!" in text
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "lint"


def test_contract_change_case_edits_the_protocol_and_its_implementation(
    cases: list[Case],
) -> None:
    case = _case(cases, "contract-change")
    replaced = _change(case, "replace")
    assert _STORE in replaced
    assert _COUNTER in replaced
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "api"


def test_uncovered_case_adds_an_untested_method_and_fails_coverage(
    cases: list[Case],
) -> None:
    case = _case(cases, "uncovered")
    assert _COUNTER in _change(case, "replace")
    assert "coverage-exempt" not in _change(case, "replace")[_COUNTER]
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "coverage"
    assert "coverage not clean for Counter" in str(case.expect["output"])


def test_exemption_case_marks_the_untested_method_exempt_with_a_reason(
    cases: list[Case],
) -> None:
    case = _case(cases, "exemption")
    text = _change(case, "replace")[_COUNTER]
    marker = text.split("// coverage-exempt:", 1)
    assert len(marker) == 2
    assert marker[1].strip().splitlines()[0].strip()
    assert case.expect["verdict"] == "pass"


def test_setup_broken_case_deletes_the_shared_scheme(cases: list[Case]) -> None:
    case = _case(cases, "setup-broken")
    assert _SCHEME in case.change.get("delete", ())
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "setup"
    assert "scheme" in str(case.expect["output"]).lower()


def test_journey_case_runs_the_journeys_and_expects_an_unrecorded_pass(
    cases: list[Case],
) -> None:
    case = _case(cases, "journey")
    assert case.run == ("gates", "--journeys")
    assert case.expect["verdict"] == "pass"
    assert case.expect["recorded"] is False


def test_journey_failing_case_fails_the_journeys_gate_naming_the_journey(
    cases: list[Case],
) -> None:
    case = _case(cases, "journey-failing")
    assert _JOURNEY in _change(case, "replace")
    assert case.run == ("gates", "--journeys")
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "journeys"
    assert "testJourney1_AppOpens" in str(case.expect["output"])


def test_adopt_mode_case_activates_an_adoption_and_adds_a_legacy_file(
    cases: list[Case],
) -> None:
    case = _case(cases, "adopt-mode")
    touched = {**_change(case, "add"), **_change(case, "replace")}
    status = touched[".bull/status.json"]
    assert json.loads(status)["adoption"] is not None
    legacy = [
        p
        for p in touched
        if p.startswith("App/Fixture/Fixture/")
        and "/Modules/" not in p
        and p.endswith(".swift")
    ]
    assert legacy
    assert case.expect["verdict"] == "pass"


def test_every_change_path_is_one_the_layout_produces(cases: list[Case]) -> None:
    prefixes = (
        "App/",
        ".bull/",
    )
    for case in cases:
        for each in (case, case.then):
            if each is None:
                continue
            paths = [
                *_change(each, "add"),
                *_change(each, "replace"),
                *each.change.get("delete", ()),  # type: ignore[misc]
            ]
            for path in paths:
                assert path.startswith(prefixes), (each.id, path)
                assert not Path(path).is_absolute()
                assert ".." not in Path(path).parts


def test_replace_and_delete_targets_exist_in_the_fixture_sources(
    cases: list[Case],
) -> None:
    hand_made = (_FIXTURE / "project" / "App").exists()
    for case in cases:
        targets = [
            *_change(case, "replace"),
            *case.change.get("delete", ()),  # type: ignore[misc]
        ]
        for path in targets:
            if path.startswith(".bull/"):
                continue  # written by the runner, not part of the fixture
            if path.startswith("App/Fixture/Fixture.xcodeproj") and not hand_made:
                continue  # the Xcode project is made by hand (fixture/SETUP.md)
            source = _source_of(path)
            assert source is not None and source.is_file(), (case.id, path)
