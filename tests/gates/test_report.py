"""Tests for `bull.Modules.gates.report`."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from bull.Modules.coverage.Contracts import CoverageReport, Exemption
from bull.Modules.coverage.mocks import MockCoverageTriage
from bull.Modules.gates import report
from bull.Modules.gates.Contracts import (
    Gate,
    GateMode,
    GateRequest,
    GateRun,
    StepResult,
    Verdict,
)

HINT_TAIL = "coverage-exempt-file: <reason>"
HINT_REST = "in the first 10 lines of a file that only declares types"


class _Triage(MockCoverageTriage):
    def render(self, report: CoverageReport) -> str:
        self.calls.append(("render", (report,)))
        return f"RENDERED {report.module}\n"


def _step(
    gate: Gate = Gate.LINT,
    part: str = "app",
    module: str | None = "Counter",
    verdict: Verdict = Verdict.PASS,
    labels: Sequence[str] = (),
    tail: str = "",
) -> StepResult:
    return StepResult(gate, part, module, verdict, tuple(labels), 0.5, tail)


def _run(
    steps: Sequence[StepResult] = (),
    *,
    verdict: Verdict = Verdict.PASS,
    coverage: Sequence[CoverageReport] = (),
    failed_ids: dict[str, tuple[str, ...]] | None = None,
    tests_run: int = 12,
    recorded: bool = True,
    note: str = "",
) -> GateRun:
    return GateRun(
        request=GateRequest(GateMode.MODULE, "Counter"),
        verdict=verdict,
        steps=tuple(steps),
        tests_run=tests_run,
        failed_ids=failed_ids or {},
        coverage=tuple(coverage),
        recorded=recorded,
        note=note,
    )


def _text(run: GateRun, comments: dict[str, str] | None = None) -> str:
    return report.render(run, _Triage(), comments or {})


def _lines(run: GateRun, comments: dict[str, str] | None = None) -> list[str]:
    return _text(run, comments).splitlines()


def _no_data(module: str = "Counter") -> CoverageReport:
    return CoverageReport(module, {}, (Path("src/types.py"),), (), ())


# --- step lines -----------------------------------------------------------


def test_a_passing_step_line_has_a_check_mark_gate_part_and_module() -> None:
    assert "✓ lint app Counter" in _lines(_run([_step()]))


def test_a_failed_step_line_has_a_cross() -> None:
    lines = _lines(_run([_step(verdict=Verdict.FAIL, labels=["x"])]))
    assert "✗ lint app Counter — x" in lines


def test_an_aborted_step_line_has_an_exclamation_mark() -> None:
    steps = [
        _step(Gate.PREFLIGHT, module=None, verdict=Verdict.ABORTED, labels=["no uv"])
    ]
    assert "! preflight app — no uv" in _lines(_run(steps, verdict=Verdict.ABORTED))


def test_a_step_without_a_module_leaves_the_module_out() -> None:
    assert "✓ build app" in _lines(_run([_step(Gate.BUILD, module=None)]))


def test_a_step_with_an_empty_part_leaves_the_part_out() -> None:
    steps = [_step(Gate.INTERFACE, part="", module=None)]
    assert "✓ interface" in _lines(_run(steps))


def test_labels_are_joined_with_semicolons() -> None:
    steps = [
        _step(Gate.TESTS, module=None, verdict=Verdict.FAIL, labels=["t::a", "t::b"])
    ]
    assert "✗ tests app — t::a; t::b" in _lines(_run(steps, verdict=Verdict.FAIL))


def test_a_step_without_labels_has_no_dash() -> None:
    lines = _lines(_run([_step()]))
    assert not any("—" in line for line in lines if "lint" in line)


def test_steps_are_listed_in_order() -> None:
    text = _text(_run([_step(Gate.BUILD, module=None), _step(Gate.TESTS, module=None)]))
    assert text.index("build app") < text.index("tests app")


# --- output tails -----------------------------------------------------------


def test_a_failed_step_with_a_tail_gets_an_output_section() -> None:
    steps = [_step(verdict=Verdict.FAIL, labels=["x"], tail="line one\nline two")]
    lines = _lines(_run(steps, verdict=Verdict.FAIL))
    at = lines.index("--- lint app output ---")
    assert lines[at + 1 : at + 3] == ["line one", "line two"]


def test_an_aborted_step_with_a_tail_gets_an_output_section() -> None:
    steps = [
        _step(Gate.PREFLIGHT, module=None, verdict=Verdict.ABORTED, tail="uv missing")
    ]
    text = _text(_run(steps, verdict=Verdict.ABORTED))
    assert "--- preflight app output ---" in text
    assert "uv missing" in text


def test_a_passing_step_tail_is_not_shown() -> None:
    text = _text(_run([_step(tail="chatter")]))
    assert "chatter" not in text
    assert "output ---" not in text


def test_a_failed_step_without_a_tail_has_no_output_section() -> None:
    text = _text(
        _run([_step(verdict=Verdict.FAIL, labels=["x"])], verdict=Verdict.FAIL)
    )
    assert "output ---" not in text


def test_output_sections_come_after_the_step_lines() -> None:
    steps = [
        _step(verdict=Verdict.FAIL, labels=["x"], tail="boom"),
        _step(Gate.API, verdict=Verdict.PASS),
    ]
    text = _text(_run(steps, verdict=Verdict.FAIL))
    assert text.index("✓ api") < text.index("--- lint app output ---")


# --- coverage ----------------------------------------------------------------


def test_each_coverage_report_is_rendered_by_the_triage() -> None:
    triage = _Triage()
    reports = [CoverageReport("A", {}, (), (), ()), CoverageReport("B", {}, (), (), ())]
    text = report.render(_run(coverage=reports), triage, {})
    assert "RENDERED A" in text
    assert "RENDERED B" in text
    assert text.index("RENDERED A") < text.index("RENDERED B")
    assert [c[1][0] for c in triage.calls if c[0] == "render"] == reports


def test_no_hint_without_files_lacking_coverage_data() -> None:
    clean = CoverageReport("Counter", {Path("a.py"): (3,)}, (), (), ())
    text = _text(_run(coverage=[clean]))
    assert HINT_TAIL not in text


def test_hint_names_the_file_marker_in_the_stack_comment_syntax() -> None:
    text = _text(_run(coverage=[_no_data()]), {"Counter": "//"})
    assert f'add "// {HINT_TAIL}" {HINT_REST}' in text


def test_hint_falls_back_to_a_hash_comment() -> None:
    text = _text(_run(coverage=[_no_data()]), {})
    assert f'add "# {HINT_TAIL}" {HINT_REST}' in text


def test_hint_uses_the_comment_of_each_report_module() -> None:
    reports = [_no_data("A"), _no_data("B")]
    text = _text(_run(coverage=reports), {"A": "//", "B": "--"})
    assert f'add "// {HINT_TAIL}"' in text
    assert f'add "-- {HINT_TAIL}"' in text


def test_hint_follows_the_rendered_report() -> None:
    text = _text(_run(coverage=[_no_data()]))
    assert text.index("RENDERED Counter") < text.index(HINT_TAIL)


def test_a_report_is_rendered_even_when_it_is_clean() -> None:
    text = _text(_run(coverage=[CoverageReport("Counter", {}, (), (), ())]))
    assert "RENDERED Counter" in text


# --- failed tests, count, ending ------------------------------------------------


def test_failed_tests_are_listed_per_part() -> None:
    run = _run(failed_ids={"web": ("t::a", "t::b"), "api": ("t::c",)})
    lines = _lines(run)
    at = lines.index("failed tests (web):")
    assert lines[at + 1 : at + 3] == ["t::a", "t::b"]
    at = lines.index("failed tests (api):")
    assert lines[at + 1] == "t::c"


def test_no_failed_tests_section_when_none_failed() -> None:
    assert "failed tests" not in _text(_run())


def test_the_number_of_tests_run_is_shown() -> None:
    assert "12 tests run" in _lines(_run(tests_run=12))


def test_a_recorded_run_ends_with_recorded() -> None:
    lines = [line for line in _lines(_run(recorded=True)) if line.strip()]
    assert lines[-1] == "recorded"


def test_a_recorded_run_with_a_note_shows_the_note_on_the_next_line() -> None:
    lines = [
        line
        for line in _lines(_run(recorded=True, note="merge holds the gated code"))
        if line.strip()
    ]
    assert lines[-2:] == ["recorded", "merge holds the gated code"]


def test_an_unrecorded_run_ends_with_its_note() -> None:
    lines = [
        line
        for line in _lines(_run(recorded=False, note="not recorded: gates failed"))
        if line.strip()
    ]
    assert lines[-1] == "not recorded: gates failed"
    assert "recorded" not in lines


def test_sections_come_in_order_steps_coverage_failed_count_ending() -> None:
    run = _run(
        [_step(verdict=Verdict.FAIL, labels=["x"], tail="boom")],
        verdict=Verdict.FAIL,
        coverage=[CoverageReport("Counter", {}, (), (), ())],
        failed_ids={"app": ("t::a",)},
        recorded=False,
        note="not recorded: gates failed",
    )
    text = _text(run)
    marks = [
        "✗ lint app Counter",
        "--- lint app output ---",
        "RENDERED Counter",
        "failed tests (app):",
        "12 tests run",
        "not recorded: gates failed",
    ]
    positions = [text.index(m) for m in marks]
    assert positions == sorted(positions)


# --- run_json ---------------------------------------------------------------------


def _full_run() -> GateRun:
    exempt_line = Exemption(Path("src/a.fx"), (12,), "defensive")
    exempt_file = Exemption(Path("src/types.fx"), None, "types only")
    report = CoverageReport(
        "Counter",
        {Path("src/a.fx"): (3, 7)},
        (Path("src/b.fx"),),
        (exempt_line, exempt_file),
        ("src/c.fx:2: missing reason",),
    )
    return GateRun(
        request=GateRequest(GateMode.AFTER_MERGE, None, "module/Counter", True),
        verdict=Verdict.FAIL,
        steps=(
            StepResult(Gate.TESTS, "app", None, Verdict.FAIL, ("t::a",), 1.5, "tail"),
            StepResult(Gate.LINT, "app", "Counter", Verdict.PASS, (), 0.25, ""),
        ),
        tests_run=4,
        failed_ids={"app": ("t::a",)},
        coverage=(report,),
        recorded=False,
        note="not recorded: gates failed",
    )


def test_run_json_is_json_serializable() -> None:
    assert json.loads(json.dumps(report.run_json(_full_run()))) == report.run_json(
        _full_run()
    )


def test_run_json_top_level_fields() -> None:
    data = report.run_json(_full_run())
    assert data["verdict"] == "fail"
    assert data["tests_run"] == 4
    assert data["recorded"] is False
    assert data["note"] == "not recorded: gates failed"
    assert data["failed_ids"] == {"app": ["t::a"]}


def test_run_json_request_uses_enum_values() -> None:
    assert report.run_json(_full_run())["request"] == {
        "mode": "after-merge",
        "module": None,
        "branch": "module/Counter",
        "skip_coverage": True,
    }


def test_run_json_steps_use_enum_values_and_lists() -> None:
    steps = report.run_json(_full_run())["steps"]
    assert steps == [
        {
            "gate": "tests",
            "part": "app",
            "module": None,
            "verdict": "fail",
            "labels": ["t::a"],
            "seconds": 1.5,
            "output_tail": "tail",
        },
        {
            "gate": "lint",
            "part": "app",
            "module": "Counter",
            "verdict": "pass",
            "labels": [],
            "seconds": 0.25,
            "output_tail": "",
        },
    ]


def test_run_json_coverage_has_posix_paths_and_clean() -> None:
    (cov,) = report.run_json(_full_run())["coverage"]  # type: ignore[misc]
    assert cov["module"] == "Counter"
    assert cov["uncovered"] == {"src/a.fx": [3, 7]}
    assert cov["no_data"] == ["src/b.fx"]
    assert cov["invalid_markers"] == ["src/c.fx:2: missing reason"]
    assert cov["clean"] is False


def test_run_json_exemptions_have_lines_and_null_for_whole_file() -> None:
    (cov,) = report.run_json(_full_run())["coverage"]  # type: ignore[misc]
    assert cov["exempted"] == [
        {"path": "src/a.fx", "lines": [12], "reason": "defensive"},
        {"path": "src/types.fx", "lines": None, "reason": "types only"},
    ]


def test_run_json_marks_a_clean_report_clean() -> None:
    run = replace(_full_run(), coverage=(CoverageReport("Counter", {}, (), (), ()),))
    (cov,) = report.run_json(run)["coverage"]  # type: ignore[misc]
    assert cov["clean"] is True


def test_run_json_of_an_empty_run() -> None:
    run = _run(tests_run=0, recorded=True)
    data = report.run_json(run)
    assert data["steps"] == []
    assert data["coverage"] == []
    assert data["failed_ids"] == {}
