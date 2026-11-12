"""Tests for the gates contract."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from bull.Modules.gates.Contracts import (
    Gate,
    GateMode,
    GateRequest,
    GateRun,
    PassRecord,
    StepResult,
    Verdict,
)


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (Gate.PREFLIGHT, "preflight"),
        (Gate.SETUP, "setup"),
        (Gate.BUILD, "build"),
        (Gate.TESTS, "tests"),
        (Gate.LINT, "lint"),
        (Gate.API, "api"),
        (Gate.COVERAGE, "coverage"),
        (Gate.INTERFACE, "interface"),
        (Gate.JOURNEYS, "journeys"),
    ],
)
def test_gate_values(member: Gate, value: str) -> None:
    assert member.value == value


def test_gate_has_exactly_nine_members() -> None:
    assert len(Gate) == 9


@pytest.mark.parametrize(
    ("member", "value"),
    [(Verdict.PASS, "pass"), (Verdict.FAIL, "fail"), (Verdict.ABORTED, "aborted")],
)
def test_verdict_values(member: Verdict, value: str) -> None:
    assert member.value == value


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (GateMode.MODULE, "module"),
        (GateMode.FAST, "fast"),
        (GateMode.FAILED, "failed"),
        (GateMode.COVERAGE_REPORT, "coverage-report"),
        (GateMode.ALL, "all"),
        (GateMode.AFTER_MERGE, "after-merge"),
        (GateMode.JOURNEYS, "journeys"),
    ],
)
def test_gate_mode_values(member: GateMode, value: str) -> None:
    assert member.value == value


def test_gate_request_defaults() -> None:
    request = GateRequest(GateMode.ALL)
    assert request.mode is GateMode.ALL
    assert request.module is None
    assert request.branch is None
    assert request.skip_coverage is False


def test_gate_request_keeps_given_fields() -> None:
    request = GateRequest(GateMode.AFTER_MERGE, "Counter", "module/Counter", True)
    assert request.module == "Counter"
    assert request.branch == "module/Counter"
    assert request.skip_coverage is True


def _step() -> StepResult:
    return StepResult(Gate.BUILD, "app", None, Verdict.PASS, ("a",), 1.0, "")


def _run() -> GateRun:
    return GateRun(GateRequest(GateMode.ALL), Verdict.PASS, (), 0, {}, (), False, "")


def _record() -> PassRecord:
    return PassRecord(
        "abc", None, "gates X", datetime(2026, 1, 1, tzinfo=UTC), ("app",)
    )


def test_gate_request_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        GateRequest(GateMode.ALL).module = "x"  # type: ignore[misc]


def test_step_result_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _step().seconds = 2.0  # type: ignore[misc]


def test_gate_run_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _run().note = "x"  # type: ignore[misc]


def test_pass_record_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _record().sha = "x"  # type: ignore[misc]


def test_step_result_holds_fields() -> None:
    step = _step()
    assert (step.gate, step.part, step.module, step.verdict) == (
        Gate.BUILD,
        "app",
        None,
        Verdict.PASS,
    )
    assert step.labels == ("a",)
    assert step.seconds == 1.0
    assert step.output_tail == ""


def test_pass_record_holds_fields() -> None:
    record = _record()
    assert record.sha == "abc"
    assert record.branch is None
    assert record.command == "gates X"
    assert record.parts == ("app",)
