"""Tests for the gates mocks."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.gates.Contracts import (
    Gate,
    GateMode,
    GateRequest,
    GateRun,
    Gates,
    PassRecords,
    StepResult,
    Verdict,
)
from bull.Modules.gates.mocks import MockGates, MockPassRecords


def test_mock_gates_satisfies_protocol() -> None:
    gates: Gates = MockGates()
    assert isinstance(gates, MockGates)


def test_mock_pass_records_satisfies_protocol() -> None:
    records: PassRecords = MockPassRecords()
    assert isinstance(records, MockPassRecords)


def test_mock_gates_starts_with_no_calls() -> None:
    assert MockGates().calls == []


def test_mock_gates_run_default_passes_and_is_recorded(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    request = GateRequest(GateMode.MODULE, "Counter")
    run = MockGates().run(app, request)
    assert run.request == request
    assert run.verdict is Verdict.PASS
    assert run.recorded is True
    assert run.steps
    assert all(s.verdict is Verdict.PASS for s in run.steps)


def test_mock_gates_run_records_call(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    request = GateRequest(GateMode.FAST, "Counter")
    mock = MockGates()
    mock.run(app, request)
    assert mock.calls == [("run", (app, request))]


def test_mock_gates_run_returns_result_override(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    request = GateRequest(GateMode.ALL)
    fixed = GateRun(request, Verdict.FAIL, (), 3, {}, (), False, "boom")
    mock = MockGates()
    mock.result = fixed
    assert mock.run(app, request) is fixed


def test_mock_gates_coverage_returns_empty_report_for_module(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    mock = MockGates()
    report = mock.coverage(app, "Counter")
    assert report.module == "Counter"
    assert not report.uncovered
    assert not report.no_data
    assert not report.exempted
    assert not report.invalid_markers
    assert mock.calls == [("coverage", (app, "Counter"))]


def test_mock_gates_render_marks_pass_and_fail_steps_and_recorded(
    tmp_path: Path,
) -> None:
    request = GateRequest(GateMode.MODULE, "Counter")
    steps = (
        StepResult(Gate.BUILD, "app", "Counter", Verdict.PASS, (), 1.0, ""),
        StepResult(Gate.TESTS, "app", "Counter", Verdict.FAIL, (), 1.0, ""),
    )
    run = GateRun(request, Verdict.FAIL, steps, 0, {}, (), True, "ignored")
    mock = MockGates()
    lines = mock.render(run).splitlines()
    assert lines[0].startswith("✓")
    assert "build" in lines[0]
    assert lines[1].startswith("✗")
    assert "tests" in lines[1]
    assert lines[-1] == "recorded"
    assert mock.calls == [("render", (run,))]


def test_mock_gates_render_shows_note_when_not_recorded() -> None:
    run = GateRun(
        GateRequest(GateMode.ALL), Verdict.PASS, (), 0, {}, (), False, "dirty tree"
    )
    assert MockGates().render(run).splitlines()[-1] == "dirty tree"


def test_mock_pass_records_get_unknown_sha_is_none(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    mock = MockPassRecords()
    assert mock.get(app, "nope") is None
    assert mock.calls == [("get", (app, "nope"))]


def test_mock_pass_records_record_then_get_round_trip(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    mock = MockPassRecords()
    mock.record(app, "abc", "module/Counter", "gates Counter", ["app", "web"])
    record = mock.get(app, "abc")
    assert record is not None
    assert record.sha == "abc"
    assert record.branch == "module/Counter"
    assert record.command == "gates Counter"
    assert record.parts == ("app", "web")


def test_mock_pass_records_record_accepts_none_branch(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    mock = MockPassRecords()
    mock.record(app, "abc", None, "gates --all", [])
    record = mock.get(app, "abc")
    assert record is not None
    assert record.branch is None
    assert record.parts == ()


def test_mock_pass_records_records_calls(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    mock = MockPassRecords()
    mock.record(app, "abc", None, "cmd", ["app"])
    assert mock.calls == [("record", (app, "abc", None, "cmd", ("app",)))]
