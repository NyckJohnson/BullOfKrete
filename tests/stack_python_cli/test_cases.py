"""Tests for the python_cli stack's `cases.json`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import bull.Modules.stack_python_cli as pkg
from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacks.registry import LiveStackRegistry
from bull.Modules.stacktest.Contracts import Case
from bull.Modules.stacktest.runner import LiveStackTester

_FOLDER = Path(pkg.__file__).parent / "python_cli"
_CASES = _FOLDER / "cases.json"
_BULL = (sys.executable, "-m", "bull")

# journeys and [interfaces] are set; no [run], no detect.
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
    "interface-drift",
}


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


def test_cases_json_declares_format_1(raw: dict[str, object]) -> None:
    assert raw["format"] == 1


def test_layout_maps_the_app_folder_to_the_root(raw: dict[str, object]) -> None:
    assert raw["layout"] == {"app/": "."}


def test_cases_cover_every_required_id(cases: list[Case]) -> None:
    assert _REQUIRED_IDS <= {c.id for c in cases}


@pytest.mark.parametrize("missing", ["run-lifecycle", "adopt-mode"])
def test_cases_omit_ids_for_undeclared_capabilities(
    cases: list[Case], missing: str
) -> None:
    assert missing not in {c.id for c in cases}


def test_case_ids_are_unique(cases: list[Case]) -> None:
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))


def test_failing_test_case_has_a_then_step_rerunning_failed(cases: list[Case]) -> None:
    case = _case(cases, "failing-test")
    assert case.then is not None
    assert case.then.run[:2] == ("gates", "--failed")
    assert case.then.expect["verdict"] == "fail"


def test_clean_case_expects_a_recorded_pass(cases: list[Case]) -> None:
    case = _case(cases, "clean")
    assert case.expect["verdict"] == "pass"
    assert case.expect["recorded"] is True


def test_fast_case_expects_an_unrecorded_pass(cases: list[Case]) -> None:
    case = _case(cases, "fast")
    assert case.expect["verdict"] == "pass"
    assert case.expect["recorded"] is False


@pytest.mark.parametrize(
    "case_id",
    [
        "no-tests",
        "failing-test",
        "build-warning",
        "lint",
        "uncovered",
        "setup-broken",
        "journey-failing",
        "interface-drift",
    ],
)
def test_failing_cases_expect_a_fail_verdict(cases: list[Case], case_id: str) -> None:
    assert _case(cases, case_id).expect["verdict"] == "fail"


@pytest.mark.parametrize("case_id", ["clean", "fast", "exemption", "journey"])
def test_passing_cases_expect_a_pass_verdict(cases: list[Case], case_id: str) -> None:
    assert _case(cases, case_id).expect["verdict"] == "pass"


def test_build_warning_case_expects_a_mypy_label(cases: list[Case]) -> None:
    assert "mypy" in str(_case(cases, "build-warning").expect["output"])


def test_interface_drift_case_fails_the_interface_gate_naming_a_field(
    cases: list[Case],
) -> None:
    expect = _case(cases, "interface-drift").expect
    assert expect["verdict"] == "fail"
    assert expect["gate"] == "interface"
    assert expect.get("output")


def test_journey_failing_case_names_the_journeys_gate(cases: list[Case]) -> None:
    assert _case(cases, "journey-failing").expect.get("gate") == "journeys"


def test_every_case_runs_a_bull_command(cases: list[Case]) -> None:
    assert all(c.run for c in cases)
