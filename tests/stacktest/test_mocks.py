"""Tests for the stacktest mocks."""

from __future__ import annotations

from bull.Modules.stacks.mocks import sample_stack
from bull.Modules.stacktest.Contracts import (
    CaseResult,
    CaseVerdict,
    StackTester,
    StackTestReport,
)
from bull.Modules.stacktest.mocks import SAMPLE_CASES, MockStackTester


def test_mock_satisfies_stack_tester_protocol() -> None:
    tester: StackTester = MockStackTester()
    assert isinstance(tester, MockStackTester)


def test_mock_starts_with_no_calls_and_no_report() -> None:
    mock = MockStackTester()
    assert mock.calls == []
    assert mock.report is None


def test_mock_starts_with_sample_cases() -> None:
    assert MockStackTester().cases == list(SAMPLE_CASES)


def test_load_cases_returns_cases_and_records_stack() -> None:
    mock = MockStackTester()
    stack = sample_stack()
    assert mock.load_cases(stack) == list(SAMPLE_CASES)
    assert mock.calls == [("load_cases", (stack,))]


def test_load_cases_returns_a_copy() -> None:
    mock = MockStackTester()
    mock.load_cases(sample_stack()).clear()
    assert mock.cases == list(SAMPLE_CASES)


def test_static_returns_passing_report_without_cases() -> None:
    mock = MockStackTester()
    stack = sample_stack()
    report = mock.static(stack)
    assert report.stack == stack.manifest.name
    assert report.static is True
    assert report.problems == ()
    assert report.cases == ()
    assert report.ok is True
    assert mock.calls == [("static", (stack,))]


def test_run_passes_every_case_and_records_call() -> None:
    mock = MockStackTester()
    stack = sample_stack()
    report = mock.run(stack)
    assert report.static is False
    assert report.stack == stack.manifest.name
    assert [r.id for r in report.cases] == [c.id for c in mock.cases]
    assert all(r.verdict is CaseVerdict.PASS for r in report.cases)
    assert mock.calls == [("run", (stack, None))]


def test_run_records_case_argument() -> None:
    mock = MockStackTester()
    stack = sample_stack()
    mock.run(stack, "clean")
    assert mock.calls == [("run", (stack, "clean"))]


def test_run_with_no_cases_gives_empty_report() -> None:
    mock = MockStackTester()
    mock.cases = []
    assert mock.run(sample_stack()).cases == ()


def test_replaced_report_is_returned_by_static_and_run() -> None:
    mock = MockStackTester()
    failing = StackTestReport(
        stack="x",
        static=False,
        problems=("boom",),
        cases=(CaseResult("clean", CaseVerdict.FAIL, "pass", "fail"),),
    )
    mock.report = failing
    assert mock.static(sample_stack()) is failing
    assert mock.run(sample_stack()) is failing


def test_render_includes_stack_cases_and_problems_and_records_call() -> None:
    mock = MockStackTester()
    report = StackTestReport(
        stack="fx",
        static=False,
        problems=("bad manifest",),
        cases=(CaseResult("clean", CaseVerdict.PASS, "pass", "pass"),),
    )
    text = mock.render(report)
    assert "fx" in text
    assert "clean" in text
    assert "pass" in text
    assert "bad manifest" in text
    assert text.endswith("\n")
    assert mock.calls == [("render", (report,))]


def test_calls_accumulate_in_order() -> None:
    mock = MockStackTester()
    stack = sample_stack()
    mock.load_cases(stack)
    mock.static(stack)
    mock.run(stack)
    assert [name for name, _ in mock.calls] == ["load_cases", "static", "run"]


def test_run_with_case_id_returns_only_that_case() -> None:
    mock = MockStackTester()
    report = mock.run(sample_stack(), "failing-test")
    assert [r.id for r in report.cases] == ["failing-test"]


def test_run_with_none_returns_all_cases() -> None:
    mock = MockStackTester()
    report = mock.run(sample_stack(), None)
    assert [r.id for r in report.cases] == [c.id for c in SAMPLE_CASES]


def test_passing_results_have_got_equal_to_expected() -> None:
    mock = MockStackTester()
    report = mock.run(sample_stack())
    assert report.cases
    for result in report.cases:
        assert result.verdict is CaseVerdict.PASS
        assert result.got == result.expected
