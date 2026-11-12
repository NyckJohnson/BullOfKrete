"""The gate run report and its JSON form."""

from __future__ import annotations

from collections.abc import Mapping

from bull.Modules.coverage.Contracts import CoverageReport, CoverageTriage, Exemption
from bull.Modules.gates.Contracts import GateRequest, GateRun, StepResult, Verdict

_MARKS = {Verdict.PASS: "✓", Verdict.FAIL: "✗", Verdict.ABORTED: "!"}
_DEFAULT_COMMENT = "#"


def render(run: GateRun, triage: CoverageTriage, comments: Mapping[str, str]) -> str:
    """The run as text: step lines, failing output, coverage, failed ids, count, ending.

    `comments` maps a module to its stack's line-comment prefix, used in the hint
    for files without coverage data; a module missing from it gets "#".
    """
    lines = [_step_line(step) for step in run.steps]
    for step in run.steps:
        if step.verdict is not Verdict.PASS and step.output_tail:
            lines.append(f"--- {_where(step.gate.value, step.part)} output ---")
            lines.extend(step.output_tail.splitlines())
    for coverage in run.coverage:
        lines.extend(triage.render(coverage).splitlines())
        if coverage.no_data:
            comment = comments.get(coverage.module, _DEFAULT_COMMENT)
            lines.append(
                f'add "{comment} coverage-exempt-file: <reason>" in the first 10 lines'
                " of a file that only declares types"
            )
    for part, ids in run.failed_ids.items():
        lines.append(f"failed tests ({part}):")
        lines.extend(ids)
    lines.append(f"{run.tests_run} tests run")
    if run.recorded:
        lines.append("recorded")
        if run.note:
            lines.append(run.note)
    elif run.note:
        lines.append(run.note)
    return "\n".join(lines) + "\n"


def run_json(run: GateRun) -> dict[str, object]:
    """`run` as JSON-ready data: enums by value, paths as POSIX strings."""
    return {
        "request": _request_json(run.request),
        "verdict": run.verdict.value,
        "steps": [_step_json(step) for step in run.steps],
        "tests_run": run.tests_run,
        "failed_ids": {part: list(ids) for part, ids in run.failed_ids.items()},
        "coverage": [coverage_json(report) for report in run.coverage],
        "recorded": run.recorded,
        "note": run.note,
    }


def coverage_json(report: CoverageReport) -> dict[str, object]:
    """A coverage report as JSON-ready data, with `clean` added."""
    return {
        "module": report.module,
        "uncovered": {
            path.as_posix(): list(lines) for path, lines in report.uncovered.items()
        },
        "no_data": [path.as_posix() for path in report.no_data],
        "exempted": [_exemption_json(item) for item in report.exempted],
        "invalid_markers": list(report.invalid_markers),
        "clean": report.clean,
    }


def _where(gate: str, part: str) -> str:
    return f"{gate} {part}" if part else gate


def _step_line(step: StepResult) -> str:
    line = f"{_MARKS[step.verdict]} {_where(step.gate.value, step.part)}"
    if step.module:
        line += f" {step.module}"
    if step.labels:
        line += " — " + "; ".join(step.labels)
    return line


def _request_json(request: GateRequest) -> dict[str, object]:
    return {
        "mode": request.mode.value,
        "module": request.module,
        "branch": request.branch,
        "skip_coverage": request.skip_coverage,
    }


def _step_json(step: StepResult) -> dict[str, object]:
    return {
        "gate": step.gate.value,
        "part": step.part,
        "module": step.module,
        "verdict": step.verdict.value,
        "labels": list(step.labels),
        "seconds": step.seconds,
        "output_tail": step.output_tail,
    }


def _exemption_json(item: Exemption) -> dict[str, object]:
    return {
        "path": item.path.as_posix(),
        "lines": None if item.lines is None else list(item.lines),
        "reason": item.reason,
    }
