"""Tests for the stacktest contract types."""

from __future__ import annotations

import dataclasses

import pytest

from bull.Modules.stacktest.Contracts import (
    Case,
    CaseResult,
    CaseVerdict,
    StackTestReport,
)


def _result(verdict: CaseVerdict, id: str = "c") -> CaseResult:
    return CaseResult(id=id, verdict=verdict, expected="pass", got="pass")


def _report(
    problems: tuple[str, ...] = (),
    cases: tuple[CaseResult, ...] = (),
) -> StackTestReport:
    return StackTestReport(
        stack="fixture", static=False, problems=problems, cases=cases
    )


def test_case_verdict_values() -> None:
    assert CaseVerdict.PASS.value == "pass"
    assert CaseVerdict.FAIL.value == "fail"
    assert CaseVerdict.NOT_RUN.value == "not run"


def test_case_verdict_has_exactly_three_members() -> None:
    assert {v.name for v in CaseVerdict} == {"PASS", "FAIL", "NOT_RUN"}


def test_case_holds_spec_fields() -> None:
    inner = Case(
        id="a/then", change={}, run=("gates", "--failed"), expect={}, then=None
    )
    case = Case(
        id="a",
        change={"add": {"x": "y"}},
        run=("gates", "counter"),
        expect={"verdict": "pass"},
        then=inner,
    )
    assert case.id == "a"
    assert case.change == {"add": {"x": "y"}}
    assert case.run == ("gates", "counter")
    assert case.expect == {"verdict": "pass"}
    assert case.then is inner
    assert inner.then is None


def test_case_field_names() -> None:
    assert [f.name for f in dataclasses.fields(Case)] == [
        "id",
        "change",
        "run",
        "expect",
        "then",
    ]


def test_case_result_holds_spec_fields() -> None:
    result = CaseResult(id="a", verdict=CaseVerdict.FAIL, expected="pass", got="fail")
    assert (result.id, result.verdict, result.expected, result.got) == (
        "a",
        CaseVerdict.FAIL,
        "pass",
        "fail",
    )


def test_report_holds_spec_fields() -> None:
    cases = (_result(CaseVerdict.PASS),)
    report = StackTestReport(stack="fx", static=True, problems=("p",), cases=cases)
    assert report.stack == "fx"
    assert report.static is True
    assert report.problems == ("p",)
    assert report.cases == cases


@pytest.mark.parametrize(
    "instance",
    [
        Case(id="a", change={}, run=(), expect={}, then=None),
        CaseResult(id="a", verdict=CaseVerdict.PASS, expected="", got=""),
        StackTestReport(stack="s", static=False, problems=(), cases=()),
    ],
)
def test_contract_dataclasses_are_frozen(instance: object) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, "id" if hasattr(instance, "id") else "stack", "changed")


def test_report_ok_with_no_cases_and_no_problems() -> None:
    assert _report().ok is True


def test_report_ok_when_every_case_passes() -> None:
    cases = (_result(CaseVerdict.PASS, "a"), _result(CaseVerdict.PASS, "b"))
    assert _report(cases=cases).ok is True


def test_report_not_ok_with_a_problem() -> None:
    assert _report(problems=("manifest missing",)).ok is False


def test_report_not_ok_with_problem_even_if_cases_pass() -> None:
    report = _report(problems=("x",), cases=(_result(CaseVerdict.PASS),))
    assert report.ok is False


def test_report_not_ok_with_a_failed_case() -> None:
    cases = (_result(CaseVerdict.PASS, "a"), _result(CaseVerdict.FAIL, "b"))
    assert _report(cases=cases).ok is False


def test_report_not_ok_with_a_not_run_case() -> None:
    cases = (_result(CaseVerdict.PASS, "a"), _result(CaseVerdict.NOT_RUN, "b"))
    assert _report(cases=cases).ok is False


@pytest.mark.parametrize("verdict", [CaseVerdict.FAIL, CaseVerdict.NOT_RUN])
def test_report_not_ok_with_only_non_pass_case(verdict: CaseVerdict) -> None:
    assert _report(cases=(_result(verdict),)).ok is False
