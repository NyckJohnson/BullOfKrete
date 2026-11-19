"""Tests for the `fixture_service` stack's self-test: `cases.json` and the sample app in `fixture_service/fixture/`.

The static check and the end-to-end run both go through the real stacktest module
(`static`, `load_cases`, `LiveStackTester`), and the end-to-end run is repeated through the
`bull stack test` command as a subprocess. The service stack has `[run]` and `[interfaces]` and no journeys
or `detect`, so its required ids are the base ten plus `run-lifecycle` and `interface-drift`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import bull.Modules.stack_fixture as pkg
from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacks.registry import LiveStackRegistry
from bull.Modules.stacktest.Contracts import Case, CaseVerdict
from bull.Modules.stacktest.runner import LiveStackTester
from bull.Modules.stacktest.static import static

_FOLDER = Path(pkg.__file__).parent / "fixture_service"
_CASES = _FOLDER / "cases.json"
_SAMPLE = _FOLDER / "fixture"
_BULL = (sys.executable, "-m", "bull")

_BASE_IDS = {
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
}
_REQUIRED_IDS = _BASE_IDS | {"run-lifecycle", "interface-drift"}
_UNDECLARED_IDS = {"journey", "journey-failing", "adopt-mode"}


def _server_processes() -> set[str]:
    done = subprocess.run(
        ["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False
    )
    return {
        line.strip()
        for line in done.stdout.splitlines()
        if "stack_fixture" in line
        and ("serve" in line or " start" in line)
        and "pytest" not in line
        and "ps -axo" not in line
    }


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    registry = LiveStackRegistry([], tmp_path_factory.mktemp("userdata"))
    return registry.load_path(_FOLDER)


@pytest.fixture(scope="module")
def cases(stack: Stack) -> list[Case]:
    return LiveStackTester(_BULL).load_cases(stack)


@pytest.fixture(scope="module")
def raw() -> dict[str, object]:
    data = json.loads(_CASES.read_text())
    assert isinstance(data, dict)
    return data


def test_cases_json_declares_format_1(raw: dict[str, object]) -> None:
    assert raw["format"] == 1


def test_cases_json_loads_through_the_stacktest_loader(cases: list[Case]) -> None:
    assert cases


def test_cases_cover_every_required_id(cases: list[Case]) -> None:
    assert _REQUIRED_IDS <= {c.id for c in cases}


def test_cases_have_a_run_lifecycle_case(cases: list[Case]) -> None:
    assert "run-lifecycle" in {c.id for c in cases}


def test_cases_have_an_interface_drift_case_failing_the_interface_gate(
    cases: list[Case],
) -> None:
    case = next(c for c in cases if c.id == "interface-drift")
    assert case.expect["verdict"] == "fail"
    assert case.expect["gate"] == "interface"
    assert "not in the schema" in str(case.expect["output"])


def test_cases_omit_ids_for_undeclared_capabilities(cases: list[Case]) -> None:
    assert not _UNDECLARED_IDS & {c.id for c in cases}


def test_case_ids_are_unique(cases: list[Case]) -> None:
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))


def test_failing_test_case_has_a_then_step(cases: list[Case]) -> None:
    case = next(c for c in cases if c.id == "failing-test")
    assert case.then is not None
    assert case.then.run[:2] == ("gates", "--failed")


def test_clean_case_expects_a_recorded_pass(cases: list[Case]) -> None:
    case = next(c for c in cases if c.id == "clean")
    assert case.expect["verdict"] == "pass"
    assert case.expect["recorded"] is True


def test_fast_case_expects_an_unrecorded_pass(cases: list[Case]) -> None:
    case = next(c for c in cases if c.id == "fast")
    assert case.expect["verdict"] == "pass"
    assert case.expect["recorded"] is False


def test_failing_cases_name_a_verdict_of_fail(cases: list[Case]) -> None:
    failing = {"no-tests", "failing-test", "build-warning", "uncovered", "setup-broken"}
    by_id = {c.id: c for c in cases}
    for case_id in failing:
        assert by_id[case_id].expect["verdict"] == "fail", case_id


def test_exemption_case_expects_a_pass(cases: list[Case]) -> None:
    case = next(c for c in cases if c.id == "exemption")
    assert case.expect["verdict"] == "pass"


def test_layout_folders_exist_in_the_sample_app(raw: dict[str, object]) -> None:
    layout = raw["layout"]
    assert isinstance(layout, dict) and layout
    for folder in layout:
        assert (_SAMPLE / str(folder)).is_dir(), folder


def test_sample_app_has_a_counter_module_with_sources_and_tests(
    raw: dict[str, object],
) -> None:
    layout = raw["layout"]
    assert isinstance(layout, dict)
    roots = [_SAMPLE / str(folder) for folder in layout]
    assert any(list(root.rglob("*.fx")) for root in roots)
    assert any(list(root.rglob("*.test")) for root in roots)
    assert any(list(root.rglob("counter")) for root in roots)


def test_sample_app_has_a_fixture_toml(raw: dict[str, object]) -> None:
    layout = raw["layout"]
    assert isinstance(layout, dict)
    assert any(list((_SAMPLE / str(f)).rglob("fixture.toml")) for f in layout)


def test_static_check_passes_for_the_fixture_stack(stack: Stack) -> None:
    report = static(stack)
    assert report.static is True
    assert report.problems == ()
    assert report.ok


def test_every_case_passes_end_to_end(stack: Stack) -> None:
    before = _server_processes()
    report = LiveStackTester(_BULL).run(stack, None)
    assert _server_processes() - before == set()
    assert report.problems == ()
    wrong = [
        f"{r.id}: expected {r.expected}, got {r.got}"
        for r in report.cases
        if r.verdict is not CaseVerdict.PASS
    ]
    assert wrong == []
    assert {r.id for r in report.cases} >= _REQUIRED_IDS
    assert report.ok


def test_bull_stack_test_command_passes_for_the_fixture_stack() -> None:
    done = subprocess.run(
        [*_BULL, "stack", "test", str(_FOLDER), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(done.stdout)
    assert data["stack"] == "fixture_service"
    assert data["problems"] == []
    assert [c for c in data["cases"] if c["verdict"] != "pass"] == []
    assert done.returncode == 0
