"""Tests for `bull.Modules.gates.cli`."""

from __future__ import annotations

import argparse
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.coverage.Contracts import CoverageReport
from bull.Modules.coverage.mocks import MockCoverageTriage
from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.gates import cli, report
from bull.Modules.gates.Contracts import GateMode, GateRequest, GateRun, Verdict
from bull.Modules.gates.mocks import MockGates, sample_run

APP = sample_layout(Path("/tmp/apps/tally"))
UNCOVERED = Path("src/a.fx")


class _UncleanGates(MockGates):
    def coverage(self, app: AppLayout, module: str) -> CoverageReport:
        self.calls.append(("coverage", (app, module)))
        return CoverageReport(module, {UNCOVERED: (3, 7)}, (), (), ())


def _run(
    gates: MockGates, argv: list[str], triage: MockCoverageTriage | None = None
) -> tuple[int, str]:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    triage = triage or MockCoverageTriage()
    cli.register(commands, lambda: gates, lambda: APP, lambda: triage)
    args = parser.parse_args(argv)
    out = io.StringIO()
    code = args.run(args, out)
    return code, out.getvalue()


def _request(gates: MockGates) -> GateRequest:
    run_calls = [c for c in gates.calls if c[0] == "run"]
    assert len(run_calls) == 1
    app, request = run_calls[0][1]
    assert app == APP
    assert isinstance(request, GateRequest)
    return request


# --- registration -----------------------------------------------------------


def test_register_adds_gates_and_coverage_commands() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    cli.register(
        commands, lambda: MockGates(), lambda: APP, lambda: MockCoverageTriage()
    )
    assert parser.parse_args(["gates", "--all"]).command == "gates"
    assert parser.parse_args(["coverage", "Counter"]).command == "coverage"


def test_providers_are_not_called_while_registering() -> None:
    def boom() -> object:
        raise AssertionError("called while registering")

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    cli.register(commands, boom, boom, boom)  # type: ignore[arg-type]
    parser.parse_args(["gates", "Counter"])


# --- mode mapping -----------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["Counter"], GateRequest(GateMode.MODULE, "Counter")),
        (["Counter", "--fast"], GateRequest(GateMode.FAST, "Counter")),
        (
            ["Counter", "--coverage-report"],
            GateRequest(GateMode.COVERAGE_REPORT, "Counter"),
        ),
        (
            ["Counter", "--skip-coverage"],
            GateRequest(GateMode.MODULE, "Counter", skip_coverage=True),
        ),
        (["--failed"], GateRequest(GateMode.FAILED)),
        (["--all"], GateRequest(GateMode.ALL)),
        (["--all", "--skip-coverage"], GateRequest(GateMode.ALL, skip_coverage=True)),
        (
            ["--after-merge", "module/Counter"],
            GateRequest(GateMode.AFTER_MERGE, branch="module/Counter"),
        ),
        (["--journeys"], GateRequest(GateMode.JOURNEYS)),
    ],
)
def test_flags_map_to_the_gate_request(argv: list[str], expected: GateRequest) -> None:
    gates = MockGates()
    _run(gates, ["gates", *argv])
    assert _request(gates) == expected


# --- refusals -----------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["Counter", "--all"],
        ["Counter", "--failed"],
        ["Counter", "--journeys"],
        ["Counter", "--after-merge", "b"],
        ["--all", "--failed"],
        ["--all", "--journeys"],
        ["--all", "--after-merge", "b"],
        ["--failed", "--journeys"],
        ["--failed", "--after-merge", "b"],
        ["--journeys", "--after-merge", "b"],
        ["--fast"],
        ["--coverage-report"],
        ["--all", "--fast"],
        ["--all", "--coverage-report"],
        ["--failed", "--fast"],
        ["--journeys", "--coverage-report"],
        ["--after-merge", "b", "--fast"],
        ["Counter", "--fast", "--coverage-report"],
        ["--skip-coverage"],
        ["--failed", "--skip-coverage"],
        ["--journeys", "--skip-coverage"],
        ["--after-merge", "b", "--skip-coverage"],
        ["Counter", "--fast", "--skip-coverage"],
        ["Counter", "--coverage-report", "--skip-coverage"],
    ],
)
def test_flag_combinations_that_make_no_sense_are_refused(argv: list[str]) -> None:
    gates = MockGates()
    with pytest.raises(BullError):
        _run(gates, ["gates", *argv])
    assert [c for c in gates.calls if c[0] == "run"] == []


# --- output and exit codes ----------------------------------------------------------


def test_text_output_is_the_rendered_run() -> None:
    gates = MockGates()
    code, out = _run(gates, ["gates", "Counter"])
    run = sample_run(GateRequest(GateMode.MODULE, "Counter"))
    assert code == 0
    assert out.rstrip("\n") == gates.render(run).rstrip("\n")
    assert out.strip() != ""


def test_json_output_is_the_run_json_alone() -> None:
    gates = MockGates()
    code, out = _run(gates, ["gates", "Counter", "--json"])
    run = sample_run(GateRequest(GateMode.MODULE, "Counter"))
    assert code == 0
    assert json.loads(out) == report.run_json(run)
    assert not any(c[0] == "render" for c in gates.calls)


@pytest.mark.parametrize(
    ("verdict", "code"),
    [(Verdict.PASS, 0), (Verdict.FAIL, 1), (Verdict.ABORTED, 2)],
)
@pytest.mark.parametrize("flags", [[], ["--json"]])
def test_exit_code_follows_the_verdict(
    verdict: Verdict, code: int, flags: list[str]
) -> None:
    gates = MockGates()
    gates.result = replace(sample_run(GateRequest(GateMode.ALL)), verdict=verdict)
    got, _ = _run(gates, ["gates", "--all", *flags])
    assert got == code


def test_the_result_of_the_run_is_what_is_rendered() -> None:
    gates = MockGates()
    result: GateRun = replace(
        sample_run(GateRequest(GateMode.ALL)), note="custom note", recorded=False
    )
    gates.result = result
    _, out = _run(gates, ["gates", "--all", "--json"])
    assert json.loads(out)["note"] == "custom note"


# --- coverage ------------------------------------------------------------------


def test_coverage_prints_the_triage_text_and_exits_zero_when_clean() -> None:
    gates = MockGates()
    triage = MockCoverageTriage()
    code, out = _run(gates, ["coverage", "Counter"], triage)
    assert code == 0
    assert ("coverage", (APP, "Counter")) in gates.calls
    (call,) = [c for c in triage.calls if c[0] == "render"]
    assert call[1][0].module == "Counter"  # type: ignore[attr-defined]
    assert "lines 3, 7-9" in out


def test_coverage_exits_one_when_the_report_is_not_clean() -> None:
    code, out = _run(_UncleanGates(), ["coverage", "Counter"])
    assert code == 1
    assert "lines 3, 7-9" in out


def test_coverage_json_prints_the_report_alone() -> None:
    code, out = _run(_UncleanGates(), ["coverage", "Counter", "--json"])
    data = json.loads(out)
    assert code == 1
    assert data["module"] == "Counter"
    assert data["clean"] is False
    assert data["uncovered"] == {"src/a.fx": [3, 7]}


def test_coverage_json_of_a_clean_report_exits_zero() -> None:
    code, out = _run(MockGates(), ["coverage", "Counter", "--json"])
    assert code == 0
    assert json.loads(out)["clean"] is True
