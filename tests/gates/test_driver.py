"""Tests for `bull.Modules.gates.driver` (LiveGates)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.api.Contracts import ApiCheck
from bull.Modules.coverage.Contracts import CoverageReport
from bull.Modules.coverage.mocks import sample_report
from bull.Modules.events.Contracts import EventKind
from bull.Modules.foundation.Contracts import BullError
from bull.Modules.gates.Contracts import Gate, GateMode, PassRecord, StepResult, Verdict
from bull.Modules.interfaces.Contracts import InterfaceResult
from bull.Modules.interfaces.mocks import SAMPLE_INTERFACE
from bull.Modules.memo.Contracts import InterfaceEntry, SideRef
from bull.Modules.stacks.Contracts import CheckItem, CoverageData, Role
from bull.Modules.stacks.Contracts import TestRun as RunSummary
from bull.Modules.stacks.mocks import MockStackReaders

from .rig import HEAD_SHA, Rig, make_rig, make_stack, shape, status_of

MODULE_STEPS = [
    "preflight:app",
    "setup:app",
    "build:app",
    "tests:app",
    "lint:app:Counter",
    "api:app:Counter",
    "coverage:app:Counter",
    "interface:app:Counter",
]


def two_parts(tmp_path: Path, **kwargs: object) -> Rig:
    """Parts `web` (journeys) and `api` (no journeys), listed web first on purpose."""
    return make_rig(
        tmp_path,
        parts=[
            ("web", make_stack("webstack")),
            ("api", make_stack("apistack", journeys=False)),
        ],
        modules=[("Store", "api"), ("Page", "web"), ("Core", "api")],
        explicit_parts=True,
        **kwargs,  # type: ignore[arg-type]
    )


# --- resolution ---------------------------------------------------------


def test_module_runs_in_its_own_part_folder(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.triage.result = CoverageReport("Page", {}, (), (), ())
    run = rig.run(GateMode.MODULE, "Page")
    assert run.verdict is Verdict.PASS
    assert {cwd for _, cwd, _ in rig.runner.calls} == {tmp_path / "web"}
    assert {s.part for s in run.steps if s.gate.value != "interface"} == {"web"}


def test_module_resolves_stack_from_its_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.registry.stacks["webstack"].readers.run = RunSummary(count=3, failed=())  # type: ignore[attr-defined]
    run = rig.run(GateMode.MODULE, "Page")
    assert run.tests_run == 3
    assert ("get", ("webstack",)) in rig.registry.calls


def test_part_resolved_by_status_part_name(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.run(GateMode.MODULE, "Store")
    assert ("get", (rig.app, "api")) in rig.parts.calls


def test_module_without_part_uses_the_implicit_part(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run(GateMode.MODULE, "Counter")
    assert ("get", (rig.app, None)) in rig.parts.calls


def test_settings_part_argument_is_none_for_the_implicit_part(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run(GateMode.MODULE, "Counter")
    env = rig.runner.envs("lint")[0]
    assert '"marker": "None"' in env["BULL_SETTINGS"]
    assert all(part is None for _, part in rig.settings.calls)


def test_settings_part_argument_is_the_name_for_a_part_with_a_file(
    tmp_path: Path,
) -> None:
    rig = two_parts(tmp_path)
    rig.run(GateMode.MODULE, "Page")
    env = rig.runner.envs("lint")[0]
    assert '"marker": "web"' in env["BULL_SETTINGS"]


def test_results_folder_is_created_for_the_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.run(GateMode.MODULE, "Page")
    assert rig.results("web").is_dir()


def test_steps_get_placeholder_values_and_env(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, environ={"INHERITED": "yes"})
    stack = rig.registry.stacks["fixture"]
    manifest = replace(
        stack.manifest,
        gates=replace(
            stack.manifest.gates,
            lint=(
                "{python}",
                "lint",
                "{module}",
                "{module_src}",
                "{module_tests}",
                "{stack_dir}",
                "{app_root}",
                "{part_root}",
                "{results}",
            ),
        ),
    )
    rig.registry.stacks["fixture"] = replace(stack, manifest=manifest)
    rig.run(GateMode.MODULE, "Counter")
    argv = next(a for a, _, _ in rig.runner.calls if a[1] == "lint")
    part = rig.parts.parts[0]
    assert argv[0] == "PY"
    assert argv[2] == "Counter"
    assert argv[3] == str(rig.parts.module_src(part, "Counter"))
    assert argv[4] == str(rig.parts.module_tests(part, "Counter"))
    assert argv[5] == str(stack.home)
    assert argv[6] == str(tmp_path)
    assert argv[7] == str(part.root)
    assert argv[8] == str(tmp_path / ".bull" / "results" / "app")
    env = rig.runner.envs("lint")[0]
    assert env["INHERITED"] == "yes"
    assert env["BULL_PART"] == "app"


# --- refusals -----------------------------------------------------------


def test_unknown_module_with_other_case_suggests_the_right_name(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(BullError) as exc:
        rig.run(GateMode.MODULE, "counter")
    assert exc.value.message == "unknown module counter"
    assert exc.value.fix == "did you mean Counter?"
    assert rig.runner.calls == []


def test_unknown_module_lists_the_modules(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, modules=[("Store", "app"), ("Counter", "app")])
    with pytest.raises(BullError) as exc:
        rig.run(GateMode.MODULE, "Nope")
    assert exc.value.message == "unknown module Nope"
    assert exc.value.fix == "modules: Store, Counter"
    assert rig.runner.calls == []


def test_unknown_module_in_an_app_without_modules(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, modules=[])
    with pytest.raises(BullError) as exc:
        rig.run(GateMode.MODULE, "Counter")
    assert exc.value.fix == "this app has no modules yet"


@pytest.mark.parametrize("mode", [GateMode.FAST, GateMode.COVERAGE_REPORT])
def test_unknown_module_is_refused_in_every_module_mode(
    tmp_path: Path, mode: GateMode
) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(BullError):
        rig.run(mode, "Missing")
    assert rig.runner.calls == []


@pytest.mark.parametrize(
    "mode", [GateMode.MODULE, GateMode.FAST, GateMode.COVERAGE_REPORT]
)
def test_module_modes_need_a_module(tmp_path: Path, mode: GateMode) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(BullError):
        rig.run(mode)
    assert rig.runner.calls == []


@pytest.mark.parametrize("mode", [GateMode.FAILED, GateMode.ALL, GateMode.JOURNEYS])
def test_other_modes_refuse_a_module(tmp_path: Path, mode: GateMode) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(BullError):
        rig.run(mode, "Counter")
    assert rig.runner.calls == []


def test_after_merge_refuses_a_module(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.git.heads["feature"] = HEAD_SHA
    with pytest.raises(BullError):
        rig.run(GateMode.AFTER_MERGE, "Counter", branch="feature")


@pytest.mark.parametrize("mode", [GateMode.MODULE, GateMode.ALL])
def test_module_branch_for_a_module_not_in_status_is_refused(
    tmp_path: Path, mode: GateMode
) -> None:
    rig = make_rig(tmp_path)
    rig.git.branch = "module/Ghost"
    module = "Counter" if mode is GateMode.MODULE else None
    with pytest.raises(BullError) as exc:
        rig.run(mode, module)
    assert exc.value.message == (
        "branch module/Ghost is for module Ghost, which is not in status"
    )
    assert exc.value.fix == "run `bull status init-modules` or switch branch"
    assert rig.runner.calls == []


def test_module_branch_for_a_module_in_status_runs(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.triage.result = CoverageReport("Counter", {}, (), (), ())
    rig.git.branch = "module/Counter"
    assert rig.run(GateMode.MODULE, "Counter").verdict is Verdict.PASS


# --- adopting -----------------------------------------------------------


@pytest.mark.parametrize("mode", [GateMode.MODULE, GateMode.FAST])
@pytest.mark.parametrize("stage", [1, 5])
def test_module_runs_while_adopting_are_adopt_scoped(
    tmp_path: Path, mode: GateMode, stage: int
) -> None:
    rig = make_rig(tmp_path, adoption_stage=stage)
    rig.run(mode, "Counter")
    for env in rig.runner.envs("preflight") + rig.runner.envs("lint"):
        assert env["BULL_ADOPT_MODE"] == "1"
        assert env["BULL_SCOPE_MODULE"] == "Counter"


def test_coverage_report_while_adopting_is_scoped(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, adoption_stage=3)
    rig.run(GateMode.COVERAGE_REPORT, "Counter")
    env = rig.runner.envs("lint")[0]
    assert env["BULL_ADOPT_MODE"] == "1"
    assert env["BULL_SCOPE_MODULE"] == "Counter"


@pytest.mark.parametrize("stage", [None, 6])
def test_module_runs_outside_adoption_are_not_scoped(
    tmp_path: Path, stage: int | None
) -> None:
    rig = make_rig(tmp_path, adoption_stage=stage)
    rig.run(GateMode.MODULE, "Counter")
    for env in rig.runner.envs("lint"):
        assert env["BULL_ADOPT_MODE"] == "0"
        assert env["BULL_SCOPE_MODULE"] == ""
    assert rig.journeys.calls == []


def test_module_run_while_adopting_adds_journeys(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, adoption_stage=4)
    run = rig.run(GateMode.MODULE, "Counter")
    assert shape(run) == [*MODULE_STEPS, "journeys:app"]
    assert rig.journeys.calls[0]["adopt"] is True


def test_fast_run_while_adopting_has_no_journeys(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, adoption_stage=4)
    rig.run(GateMode.FAST, "Counter")
    assert rig.journeys.calls == []


@pytest.mark.parametrize("mode", [GateMode.ALL, GateMode.JOURNEYS])
def test_all_and_journeys_adopt_without_scope_while_adopting(
    tmp_path: Path, mode: GateMode
) -> None:
    rig = make_rig(tmp_path, adoption_stage=2)
    rig.run(mode)
    assert rig.journeys.calls[0]["adopt"] is True
    assert rig.journeys.calls[0]["env"]["BULL_ADOPT_MODE"] == "1"  # type: ignore[index]
    assert rig.journeys.calls[0]["env"]["BULL_SCOPE_MODULE"] == ""  # type: ignore[index]
    for env in rig.runner.envs("preflight"):
        assert env["BULL_SCOPE_MODULE"] == ""


@pytest.mark.parametrize("stage", [None, 6])
def test_all_outside_adoption_does_not_adopt(tmp_path: Path, stage: int | None) -> None:
    rig = make_rig(tmp_path, adoption_stage=stage)
    rig.run(GateMode.ALL)
    assert rig.journeys.calls[0]["adopt"] is False
    assert rig.runner.envs("preflight")[0]["BULL_ADOPT_MODE"] == "0"


# --- step order per mode ------------------------------------------------


def test_module_mode_step_order(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.triage.result = CoverageReport("Counter", {}, (), (), ())
    run = rig.run(GateMode.MODULE, "Counter")
    assert shape(run) == MODULE_STEPS
    assert rig.runner.steps() == ["preflight", "setup", "build-test", "lint"]
    assert run.verdict is Verdict.PASS


def test_module_build_and_tests_steps_pass_with_ten_tests(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.tests_run == 10
    assert run.failed_ids == {}


def test_fast_mode_step_order(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.FAST, "Counter")
    assert shape(run) == [
        "preflight:app",
        "build:app",
        "tests:app",
        "lint:app:Counter",
        "api:app:Counter",
    ]
    assert rig.runner.steps() == ["preflight", "build-test-fast", "lint"]
    argv = rig.runner.calls[1][0]
    assert argv == ("PY", "build-test-fast", "Counter")
    assert run.coverage == ()


def test_coverage_report_mode_stops_after_coverage(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.COVERAGE_REPORT, "Counter")
    assert shape(run) == MODULE_STEPS[:-1]
    assert run.coverage == (rig.triage.result,)
    assert run.recorded is False
    assert run.note == "not recorded: partial run (coverage-report)"


def test_all_mode_runs_parts_in_name_order_with_modules_in_build_order(
    tmp_path: Path,
) -> None:
    rig = two_parts(tmp_path)
    run = rig.run(GateMode.ALL)
    assert shape(run) == [
        "preflight:api",
        "setup:api",
        "build:api",
        "tests:api",
        "lint:api:Store",
        "api:api:Store",
        "coverage:api:Store",
        "interface:api:Store",
        "lint:api:Core",
        "api:api:Core",
        "coverage:api:Core",
        "interface:api:Core",
        "preflight:web",
        "setup:web",
        "build:web",
        "tests:web",
        "lint:web:Page",
        "api:web:Page",
        "coverage:web:Page",
        "interface:web:Page",
        "interface:",
        "journeys:web",
    ]


def test_all_mode_build_test_runs_once_per_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.run(GateMode.ALL)
    assert rig.runner.steps("api").count("build-test") == 1
    assert rig.runner.steps("web").count("build-test") == 1


def test_all_mode_app_wide_interface_step_has_no_part_or_module(
    tmp_path: Path,
) -> None:
    rig = two_parts(tmp_path)
    run = rig.run(GateMode.ALL)
    step = status_of(run, "interface", "")
    assert step.module is None
    assert step.verdict is Verdict.PASS


def test_all_mode_sums_tests_and_reports_failed_ids_per_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.registry.stacks["apistack"].readers.run = RunSummary(count=5, failed=())  # type: ignore[attr-defined]
    rig.registry.stacks["webstack"].readers.run = RunSummary(count=7, failed=("t::x",))  # type: ignore[attr-defined]
    rig.runner.set("build-test", part="web", code=1)
    run = rig.run(GateMode.ALL)
    assert run.tests_run == 12
    assert run.failed_ids == {"web": ("t::x",)}


def test_journeys_mode_runs_only_journeys_for_parts_that_have_them(
    tmp_path: Path,
) -> None:
    rig = two_parts(tmp_path)
    run = rig.run(GateMode.JOURNEYS)
    assert shape(run) == ["journeys:web"]
    assert rig.runner.calls == []
    assert rig.journeys.parts() == ["web"]
    assert "no journey tests: api" in run.note
    assert run.recorded is False


def test_journeys_mode_without_any_journey_stack_reports_each_part(
    tmp_path: Path,
) -> None:
    rig = make_rig(
        tmp_path,
        parts=[
            ("a", make_stack("sa", journeys=False)),
            ("b", make_stack("sb", journeys=False)),
        ],
        modules=[],
        explicit_parts=True,
    )
    run = rig.run(GateMode.JOURNEYS)
    assert run.steps == ()
    assert run.verdict is Verdict.PASS
    assert "no journey tests: a" in run.note
    assert "no journey tests: b" in run.note
    assert "; " in run.note


def test_journeys_only_run_for_stacks_that_define_them(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.run(GateMode.ALL)
    assert rig.journeys.parts() == ["web"]


def test_journeys_get_the_part_its_stack_and_providers(tmp_path: Path) -> None:
    rig = make_rig(
        tmp_path,
        parts=[
            ("cli", make_stack("clistack")),
            ("web", make_stack("webstack")),
        ],
        modules=[],
        explicit_parts=True,
    )
    rig.run(GateMode.JOURNEYS)
    by_part = {str(c["part"].name): c for c in rig.journeys.calls}  # type: ignore[attr-defined]
    cli_call = by_part["cli"]
    assert cli_call["stack"] is rig.registry.stacks["clistack"]
    assert cli_call["results"] == rig.results("cli")
    assert [p.part.name for p in cli_call["providers"]] == ["web"]  # type: ignore[attr-defined]
    assert by_part["web"]["providers"] == []


def test_a_failing_journey_fails_the_run(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.journeys.verdicts["app"] = "fail"
    run = rig.run(GateMode.JOURNEYS)
    assert run.verdict is Verdict.FAIL


# --- preflight / setup --------------------------------------------------


def test_preflight_exit_2_aborts_and_nothing_else_runs(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("preflight", code=2)
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.verdict is Verdict.ABORTED
    assert shape(run) == ["preflight:app"]
    assert run.steps[0].verdict is Verdict.ABORTED
    assert rig.runner.steps() == ["preflight"]


def test_preflight_abort_in_all_skips_later_parts(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.runner.set("preflight", part="api", code=2)
    run = rig.run(GateMode.ALL)
    assert run.verdict is Verdict.ABORTED
    assert shape(run) == ["preflight:api"]
    assert rig.runner.steps("web") == []
    assert rig.journeys.calls == []


def test_abort_in_a_later_part_outranks_an_earlier_failure(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.runner.set("lint", part="api", code=1)
    rig.runner.set("preflight", part="web", code=2)
    run = rig.run(GateMode.ALL)
    assert run.verdict is Verdict.ABORTED


def test_preflight_other_failure_fails_but_later_steps_still_run(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("preflight", code=1)
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.verdict is Verdict.FAIL
    assert status_of(run, "preflight").verdict is Verdict.FAIL
    assert "setup:app" in shape(run)
    assert "lint:app:Counter" in shape(run)


def test_setup_failure_stops_the_parts_remaining_steps(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("setup", code=1)
    run = rig.run(GateMode.MODULE, "Counter")
    assert shape(run) == ["preflight:app", "setup:app"]
    assert run.verdict is Verdict.FAIL
    assert rig.runner.steps() == ["preflight", "setup"]


def test_setup_failure_in_all_goes_on_with_the_next_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.runner.set("setup", part="api", code=1)
    run = rig.run(GateMode.ALL)
    steps = shape(run)
    assert steps[:2] == ["preflight:api", "setup:api"]
    assert "build:api" not in steps
    assert "tests:web" in steps
    assert run.verdict is Verdict.FAIL


def test_step_labels_come_from_bull_fail_lines(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("lint", code=1, stdout="noise\nbull-fail: x.py:3 bad name\n")
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "lint").labels == ("x.py:3 bad name",)
    assert status_of(run, "lint").verdict is Verdict.FAIL
    assert run.verdict is Verdict.FAIL


def test_non_zero_step_without_labels_gets_a_generic_label(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("lint", code=3)
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "lint").labels == ("lint failed (exit 3)",)


def test_failing_step_keeps_the_last_forty_output_lines(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("lint", code=1, stdout="\n".join(f"l{i}" for i in range(60)))
    run = rig.run(GateMode.MODULE, "Counter")
    tail = status_of(run, "lint").output_tail.splitlines()
    assert len(tail) == 40
    assert tail[-1] == "l59"


def test_a_failed_step_does_not_stop_the_other_steps(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("lint", code=1)
    run = rig.run(GateMode.MODULE, "Counter")
    assert shape(run) == MODULE_STEPS


# --- build / tests ------------------------------------------------------


def test_build_and_tests_seconds_come_from_the_run(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("build-test", seconds=4.5)
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "build").seconds == 0
    assert status_of(run, "tests").seconds == 4.5


def test_no_test_results_fails_tests_even_with_exit_0(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", run=None))])
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "build").verdict is Verdict.PASS
    tests = status_of(run, "tests")
    assert tests.verdict is Verdict.FAIL
    assert tests.labels == ("no tests ran",)
    assert run.verdict is Verdict.FAIL
    assert run.tests_run == 0


def test_zero_tests_fail_tests_even_with_exit_0(tmp_path: Path) -> None:
    rig = make_rig(
        tmp_path, parts=[("app", make_stack("fixture", run=RunSummary(0, ())))]
    )
    run = rig.run(GateMode.MODULE, "Counter")
    tests = status_of(run, "tests")
    assert tests.verdict is Verdict.FAIL
    assert tests.labels == ("no tests ran",)
    assert run.tests_run == 0


def test_failed_test_ids_become_the_labels_of_a_failed_tests_step(
    tmp_path: Path,
) -> None:
    run_result = RunSummary(count=4, failed=("t::a", "t::b"))
    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", run=run_result))])
    rig.runner.set("build-test", code=1)
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "tests").verdict is Verdict.FAIL
    assert status_of(run, "tests").labels == ("t::a", "t::b")
    assert status_of(run, "build").verdict is Verdict.PASS
    assert run.tests_run == 4
    assert run.failed_ids == {"app": ("t::a", "t::b")}


def test_non_zero_exit_without_failed_tests_is_a_build_failure(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("build-test", code=2)
    run = rig.run(GateMode.MODULE, "Counter")
    steps = shape(run)
    assert steps.index("build:app") < steps.index("tests:app")
    assert status_of(run, "build").verdict is Verdict.FAIL
    assert run.verdict is Verdict.FAIL
    assert run.failed_ids == {}


def test_failed_ids_replace_failed_txt_after_a_run(tmp_path: Path) -> None:
    run_result = RunSummary(count=4, failed=("t::a", "t::b"))
    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", run=run_result))])
    rig.results("app").mkdir(parents=True)
    (rig.results("app") / "failed.txt").write_text("old::one\n")
    rig.runner.set("build-test", code=1)
    rig.run(GateMode.MODULE, "Counter")
    assert (rig.results("app") / "failed.txt").read_text() == "t::a\nt::b\n"


def test_a_passing_run_empties_failed_txt(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.results("app").mkdir(parents=True)
    (rig.results("app") / "failed.txt").write_text("old::one\n")
    rig.run(GateMode.MODULE, "Counter")
    assert (rig.results("app") / "failed.txt").read_text() == ""


def test_fast_mode_replaces_failed_txt_with_new_failures(tmp_path: Path) -> None:
    run_result = RunSummary(count=2, failed=("t::z",))
    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", run=run_result))])
    rig.results("app").mkdir(parents=True)
    (rig.results("app") / "failed.txt").write_text("old::one\n")
    rig.runner.set("build-test-fast", code=1)
    run = rig.run(GateMode.FAST, "Counter")
    assert (rig.results("app") / "failed.txt").read_text() == "t::z\n"
    assert status_of(run, "tests").labels == ("t::z",)


def test_fast_mode_passing_run_empties_failed_txt(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.results("app").mkdir(parents=True)
    (rig.results("app") / "failed.txt").write_text("old::one\n")
    rig.run(GateMode.FAST, "Counter")
    assert (rig.results("app") / "failed.txt").read_text() == ""


def test_test_results_are_read_from_the_parts_results_folder(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run(GateMode.MODULE, "Counter")
    readers = rig.registry.stacks["fixture"].readers
    assert isinstance(readers, MockStackReaders)
    assert ("test_results", (rig.results("app"),)) in readers.calls


# --- coverage / api / interface steps -----------------------------------


def test_coverage_is_skipped_when_tests_failed(tmp_path: Path) -> None:
    run_result = RunSummary(count=2, failed=("t::z",))
    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", run=run_result))])
    rig.runner.set("build-test", code=1)
    run = rig.run(GateMode.MODULE, "Counter")
    assert not any(s.startswith("coverage") for s in shape(run))
    assert "api:app:Counter" in shape(run)
    assert "interface:app:Counter" in shape(run)
    assert run.coverage == ()


def test_coverage_is_skipped_when_the_build_failed(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("build-test", code=2)
    run = rig.run(GateMode.MODULE, "Counter")
    assert not any(s.startswith("coverage") for s in shape(run))


def test_coverage_skipped_in_one_part_still_runs_in_the_other(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.registry.stacks["apistack"].readers.run = RunSummary(count=0, failed=())  # type: ignore[attr-defined]
    run = rig.run(GateMode.ALL)
    steps = shape(run)
    assert "coverage:api:Store" not in steps
    assert "coverage:web:Page" in steps


def test_skip_coverage_leaves_out_the_coverage_step(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.MODULE, "Counter", skip_coverage=True)
    assert shape(run) == [s for s in MODULE_STEPS if not s.startswith("coverage")]
    assert run.coverage == ()


def test_skip_coverage_in_all_mode(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.ALL, skip_coverage=True)
    assert not any(s.startswith("coverage") for s in shape(run))


def test_clean_coverage_passes_and_is_reported(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    clean = CoverageReport("Counter", {}, (), (), ())
    rig.triage.result = clean
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "coverage").verdict is Verdict.PASS
    assert run.coverage == (clean,)


def test_unclean_coverage_fails_with_a_label_and_is_reported(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.MODULE, "Counter")
    step = status_of(run, "coverage")
    assert step.verdict is Verdict.FAIL
    assert step.labels == ("coverage not clean for Counter",)
    assert run.coverage == (sample_report("Counter"),)
    assert run.verdict is Verdict.FAIL


def test_coverage_step_reads_the_last_runs_data(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run(GateMode.MODULE, "Counter")
    names = [c[0] for c in rig.triage.calls]
    assert names == ["sources", "report"]


def test_api_step_passes_when_the_contract_matches(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "api").verdict is Verdict.PASS
    assert ("check", (rig.app, "Counter")) in rig.api.calls


def test_api_step_fails_with_the_diff_tail(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    diff = "\n".join(f"- line {i}" for i in range(55))
    rig.api.module_checks["Counter"] = ApiCheck("Counter", False, True, diff)
    run = rig.run(GateMode.MODULE, "Counter")
    step = status_of(run, "api")
    assert step.verdict is Verdict.FAIL
    assert step.labels == ("contract differs from docs/api/Counter.md",)
    tail = step.output_tail.splitlines()
    assert len(tail) == 40
    assert tail[-1] == "- line 54"
    assert tail[0] == "- line 15"


def test_interface_step_without_results_passes(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.MODULE, "Counter")
    step = status_of(run, "interface")
    assert step.verdict is Verdict.PASS
    assert step.labels == ()


def test_interface_step_labels_each_failed_item(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.interfaces.module_results["Counter"] = [
        InterfaceResult(
            "TallyEvents",
            "app",
            "Counter",
            Role.PROVIDER,
            (
                CheckItem(False, "field count missing", "add count"),
                CheckItem(True, "field name present", ""),
                CheckItem(False, "field time missing", "add time"),
            ),
        )
    ]
    run = rig.run(GateMode.MODULE, "Counter")
    step = status_of(run, "interface")
    assert step.verdict is Verdict.FAIL
    assert step.labels == (
        "TallyEvents: field count missing — add count",
        "TallyEvents: field time missing — add time",
    )


def test_interface_step_with_only_passing_items_passes(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.interfaces.module_results["Counter"] = [
        InterfaceResult(
            "TallyEvents",
            "app",
            "Counter",
            Role.PROVIDER,
            (CheckItem(True, "field name present", ""),),
        )
    ]
    run = rig.run(GateMode.MODULE, "Counter")
    assert status_of(run, "interface").verdict is Verdict.PASS


OTHER_INTERFACE = InterfaceEntry(
    name="Other",
    file="interfaces/other.json",
    format="json-schema",
    provider=SideRef("api", "Core"),
    consumers=(),
    contract_changes={},
)


def test_all_interface_step_flags_snapshots_that_differ(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, interface_entries=[SAMPLE_INTERFACE, OTHER_INTERFACE])
    rig.api.interface_checks["TallyEvents"] = ApiCheck("TallyEvents", False, True, "d")
    run = rig.run(GateMode.ALL)
    step = status_of(run, "interface", "")
    assert step.verdict is Verdict.FAIL
    assert step.labels == ("interface TallyEvents differs from its snapshot",)
    checked = [c[1][1] for c in rig.api.calls if c[0] == "check_interface"]
    assert checked == ["TallyEvents", "Other"]


def test_all_interface_step_reports_interface_problems(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, interface_entries=[SAMPLE_INTERFACE])
    rig.interfaces.found_problems = ["interface X: no provider", "interface Y: bad"]
    run = rig.run(GateMode.ALL)
    step = status_of(run, "interface", "")
    assert step.verdict is Verdict.FAIL
    assert step.labels == ("interface X: no provider", "interface Y: bad")


def test_all_interface_step_passes_when_snapshots_and_problems_are_clean(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path, interface_entries=[SAMPLE_INTERFACE])
    run = rig.run(GateMode.ALL)
    assert status_of(run, "interface", "").verdict is Verdict.PASS


def test_own_steps_measure_wall_time(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.MODULE, "Counter")
    for gate in ("api", "coverage", "interface"):
        assert status_of(run, gate).seconds >= 0


# --- events -------------------------------------------------------------


def test_every_step_appends_a_gate_step_event(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.MODULE, "Counter")
    events = rig.gate_events()
    assert len(events) == len(run.steps)
    assert [e.data["gate"] for e in events] == [s.gate.value for s in run.steps]


def test_gate_step_event_carries_part_module_verdict_and_seconds(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path)
    rig.runner.set("lint", code=1, seconds=2.5)
    rig.run(GateMode.MODULE, "Counter")
    event = next(e for e in rig.gate_events() if e.data["gate"] == "lint")
    assert event.kind is EventKind.GATE_STEP
    assert event.data["part"] == "app"
    assert event.data["module"] == "Counter"
    assert event.data["verdict"] == "fail"
    assert event.data["seconds"] == 2.5


def test_bulls_own_steps_also_log_events(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run(GateMode.MODULE, "Counter")
    gates = {e.data["gate"] for e in rig.gate_events()}
    assert {"api", "coverage", "interface"} <= gates


# --- verdict and recording ----------------------------------------------


def test_verdict_is_pass_when_every_step_passes(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.triage.result = CoverageReport("Counter", {}, (), (), ())
    assert rig.run(GateMode.MODULE, "Counter").verdict is Verdict.PASS


def clean_rig(tmp_path: Path, **kwargs: object) -> Rig:
    rig = make_rig(tmp_path, **kwargs)  # type: ignore[arg-type]
    rig.triage.result = CoverageReport("Counter", {}, (), (), ())
    return rig


def test_module_pass_on_a_clean_tree_is_recorded(tmp_path: Path) -> None:
    rig = clean_rig(tmp_path)
    rig.git.branch = "module/Counter"
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.verdict is Verdict.PASS
    assert run.recorded is True
    assert rig.passes.recorded == [
        (HEAD_SHA, "module/Counter", "gates Counter", ("app",))
    ]


def test_all_pass_is_recorded_with_every_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.triage.result = CoverageReport("x", {}, (), (), ())
    run = rig.run(GateMode.ALL)
    assert run.verdict is Verdict.PASS
    assert run.recorded is True
    sha, branch, command, parts = rig.passes.recorded[0]
    assert sha == HEAD_SHA
    assert branch == "main"
    assert command == "gates --all"
    assert sorted(parts) == ["api", "web"]


def test_dirty_tree_before_the_run_records_nothing(tmp_path: Path) -> None:
    rig = clean_rig(tmp_path)
    rig.git.clean = False
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.recorded is False
    assert run.note == "not recorded: working tree has changes"
    assert rig.passes.recorded == []


def test_tree_dirtied_during_the_run_records_nothing(tmp_path: Path) -> None:
    rig = clean_rig(tmp_path)

    def dirty(step: str) -> None:
        if step == "lint":
            rig.git.clean = False

    rig.runner.on_run = dirty
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.recorded is False
    assert run.note == "not recorded: working tree has changes"
    assert rig.passes.recorded == []


@pytest.mark.parametrize("fail_step", ["lint", "setup"])
def test_failed_run_records_nothing(tmp_path: Path, fail_step: str) -> None:
    rig = clean_rig(tmp_path)
    rig.runner.set(fail_step, code=1)
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.recorded is False
    assert run.note == "not recorded: gates failed"
    assert rig.passes.recorded == []


def test_aborted_run_records_nothing(tmp_path: Path) -> None:
    rig = clean_rig(tmp_path)
    rig.runner.set("preflight", code=2)
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.recorded is False
    assert run.note == "not recorded: gates failed"


@pytest.mark.parametrize("module", ["Counter", None])
def test_skip_coverage_runs_are_not_recorded(
    tmp_path: Path, module: str | None
) -> None:
    rig = clean_rig(tmp_path)
    mode = GateMode.MODULE if module else GateMode.ALL
    run = rig.run(mode, module, skip_coverage=True)
    assert run.verdict is Verdict.PASS
    assert run.recorded is False
    assert run.note == "not recorded: coverage skipped"
    assert rig.passes.recorded == []


@pytest.mark.parametrize(
    "mode",
    [GateMode.FAST, GateMode.COVERAGE_REPORT],
)
def test_partial_module_runs_are_never_recorded(tmp_path: Path, mode: GateMode) -> None:
    rig = clean_rig(tmp_path)
    run = rig.run(mode, "Counter")
    assert run.recorded is False
    assert run.note == f"not recorded: partial run ({mode.value})"
    assert rig.passes.recorded == []


def test_journeys_runs_are_never_recorded(tmp_path: Path) -> None:
    rig = clean_rig(tmp_path)
    run = rig.run(GateMode.JOURNEYS)
    assert run.recorded is False
    assert "not recorded: partial run (journeys)" in run.note
    assert rig.passes.recorded == []


def test_git_clean_is_checked_before_and_after_a_recorded_run(
    tmp_path: Path,
) -> None:
    rig = clean_rig(tmp_path)
    rig.run(GateMode.MODULE, "Counter")
    assert [c[0] for c in rig.git.calls].count("is_clean") >= 2


# --- FAILED -------------------------------------------------------------


def seed_failed(rig: Rig, part: str, ids: str) -> Path:
    results = rig.results(part)
    results.mkdir(parents=True, exist_ok=True)
    path = results / "failed.txt"
    path.write_text(ids)
    return path


def test_failed_reruns_the_recorded_ids_in_their_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    seed_failed(rig, "web", "t::a\nt::b\n")
    run = rig.run(GateMode.FAILED)
    assert shape(run) == ["tests:web"]
    assert rig.runner.calls[0][0] == ("PY", "rerun", "t::a", "t::b")
    assert rig.runner.calls[0][1] == tmp_path / "web"
    assert len(rig.runner.calls) == 1
    assert run.tests_run == 2
    assert run.verdict is Verdict.PASS
    assert run.recorded is False
    assert run.note == "not recorded: partial run (failed)"


def test_failed_pass_empties_failed_txt(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    path = seed_failed(rig, "app", "t::a\n")
    rig.run(GateMode.FAILED)
    assert path.read_text() == ""


def test_failed_fail_replaces_failed_txt_with_the_new_failures(
    tmp_path: Path,
) -> None:
    stack = make_stack("fixture", run=RunSummary(count=2, failed=("t::b",)))
    rig = make_rig(tmp_path, parts=[("app", stack)])
    path = seed_failed(rig, "app", "t::a\nt::b\n")
    rig.runner.set("rerun", code=1)
    run = rig.run(GateMode.FAILED)
    assert run.verdict is Verdict.FAIL
    assert path.read_text() == "t::b\n"


def test_failed_fail_without_new_ids_keeps_failed_txt(tmp_path: Path) -> None:
    stack = make_stack("fixture", run=RunSummary(count=2, failed=()))
    rig = make_rig(tmp_path, parts=[("app", stack)])
    path = seed_failed(rig, "app", "t::a\nt::b\n")
    rig.runner.set("rerun", code=1)
    run = rig.run(GateMode.FAILED)
    assert run.verdict is Verdict.FAIL
    assert path.read_text() == "t::a\nt::b\n"


def test_failed_fail_with_no_test_results_keeps_failed_txt(tmp_path: Path) -> None:
    stack = make_stack("fixture", run=None)
    rig = make_rig(tmp_path, parts=[("app", stack)])
    path = seed_failed(rig, "app", "t::a\n")
    rig.runner.set("rerun", code=1)
    run = rig.run(GateMode.FAILED)
    assert run.verdict is Verdict.FAIL
    assert path.read_text() == "t::a\n"


def test_failed_with_nothing_recorded_fails_with_a_tests_step(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    run = rig.run(GateMode.FAILED)
    assert run.verdict is Verdict.FAIL
    assert run.steps == (
        StepResult(
            Gate.TESTS,
            "",
            None,
            Verdict.FAIL,
            ("no failed tests recorded; run `bull gates <M> --fast`",),
            0,
            run.steps[0].output_tail,
        ),
    )
    assert run.tests_run == 0
    assert run.note == "no failed tests recorded"
    assert run.recorded is False
    assert rig.runner.calls == []


def test_failed_with_an_empty_failed_txt_fails_with_nothing_to_rerun(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path)
    seed_failed(rig, "app", "\n")
    run = rig.run(GateMode.FAILED)
    assert run.verdict is Verdict.FAIL
    assert len(run.steps) == 1
    step = run.steps[0]
    assert (step.gate, step.part, step.module, step.verdict) == (
        Gate.TESTS,
        "",
        None,
        Verdict.FAIL,
    )
    assert step.labels == ("no failed tests recorded; run `bull gates <M> --fast`",)
    assert step.seconds == 0
    assert run.tests_run == 0
    assert run.note == "no failed tests recorded"
    assert run.recorded is False
    assert rig.runner.calls == []


def test_failed_reruns_each_part_with_ids_in_parts_order(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    seed_failed(rig, "api", "t::api\n")
    seed_failed(rig, "web", "t::w1\nt::w2\nt::w3\n")
    run = rig.run(GateMode.FAILED)
    assert shape(run) == ["tests:web", "tests:api"]
    assert run.tests_run == 4
    assert [c[0] for c in rig.runner.calls] == [
        ("PY", "rerun", "t::w1", "t::w2", "t::w3"),
        ("PY", "rerun", "t::api"),
    ]


def test_failed_never_records_even_on_a_clean_pass(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    seed_failed(rig, "app", "t::a\n")
    rig.run(GateMode.FAILED)
    assert rig.passes.recorded == []


# --- coverage(app, M) ---------------------------------------------------


def test_coverage_without_test_results_is_refused(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", run=None))])
    with pytest.raises(BullError) as exc:
        rig.gates.coverage(rig.app, "Counter")
    assert exc.value.message == "no coverage data for Counter"
    assert exc.value.fix == "run `bull gates Counter` first"


def test_coverage_of_an_unknown_module_is_refused(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(BullError):
        rig.gates.coverage(rig.app, "Nope")


def test_coverage_builds_the_report_from_the_parts_data(tmp_path: Path) -> None:
    stack = make_stack("fixture", comment="//")
    rig = make_rig(tmp_path, parts=[("app", stack)])
    data = CoverageData(uncovered={Path("a.fx"): (1,)}, no_data=())
    stack.readers.coverage = data  # type: ignore[attr-defined]
    report = rig.gates.coverage(rig.app, "Counter")
    assert report is rig.triage.result
    part = rig.parts.parts[0]
    src = rig.parts.module_src(part, "Counter")
    sources_call = next(c for c in rig.triage.calls if c[0] == "sources")
    assert sources_call[1][:3] == (src, part.root, stack.manifest.source_glob)
    uncovered = next(c for c in stack.readers.calls if c[0] == "uncovered")  # type: ignore[attr-defined]
    assert uncovered[1] == (part.root, (src / "counter.fx",), rig.results("app"))
    report_call = next(c for c in rig.triage.calls if c[0] == "report")
    assert report_call[1] == ("Counter", (src / "counter.fx",), data, "//")


def test_coverage_exclude_is_the_defaults_followed_by_the_extras(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path)
    rig.settings.values["coverage.exclude"] = ("*/mocks/*", "*/gen/*")
    rig.settings.values["coverage.exclude_extra"] = ("legacy/*",)
    rig.gates.coverage(rig.app, "Counter")
    sources_call = next(c for c in rig.triage.calls if c[0] == "sources")
    assert sources_call[1][3] == ("*/mocks/*", "*/gen/*", "legacy/*")


def test_coverage_with_no_extras_passes_the_defaults_alone(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.gates.coverage(rig.app, "Counter")
    sources_call = next(c for c in rig.triage.calls if c[0] == "sources")
    assert sources_call[1][3] == ("*/mocks/*",)


def test_coverage_reads_settings_for_the_modules_part(tmp_path: Path) -> None:
    rig = two_parts(tmp_path)
    rig.gates.coverage(rig.app, "Page")
    keys = {k: p for k, p in rig.settings.calls if k.startswith("coverage.")}
    assert keys == {"coverage.exclude": "web", "coverage.exclude_extra": "web"}


def test_coverage_in_the_implicit_part_reads_settings_without_a_part(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path)
    rig.gates.coverage(rig.app, "Counter")
    keys = {k: p for k, p in rig.settings.calls if k.startswith("coverage.")}
    assert keys == {"coverage.exclude": None, "coverage.exclude_extra": None}


# --- unit 3 review follow-ups -------------------------------------------


def test_render_passes_the_remembered_stack_comment_of_each_covered_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bull.Modules.gates import report as report_module

    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", comment="//"))])
    seen: list[dict[str, str]] = []

    def fake_render(run: object, triage: object, comments: dict[str, str]) -> str:
        seen.append(dict(comments))
        return "rendered"

    monkeypatch.setattr(report_module, "render", fake_render)
    run = rig.run(GateMode.MODULE, "Counter")
    assert rig.gates.render(run) == "rendered"
    assert seen[0]["Counter"] == "//"


def test_render_comment_follows_an_explicit_coverage_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bull.Modules.gates import report as report_module

    rig = make_rig(tmp_path, parts=[("app", make_stack("fixture", comment="--"))])
    seen: list[dict[str, str]] = []

    def fake_render(run: object, triage: object, comments: dict[str, str]) -> str:
        seen.append(dict(comments))
        return ""

    monkeypatch.setattr(report_module, "render", fake_render)
    report_ = rig.gates.coverage(rig.app, "Counter")
    run = replace(rig.run(GateMode.FAILED), coverage=(report_,))
    rig.gates.render(run)
    assert seen[0]["Counter"] == "--"


def test_failed_reruns_get_the_adopt_env_without_a_scope_while_adopting(
    tmp_path: Path,
) -> None:
    rig = make_rig(tmp_path, adoption_stage=3)
    seed_failed(rig, "app", "t::a\n")
    rig.run(GateMode.FAILED)
    (env,) = rig.runner.envs("rerun")
    assert env["BULL_ADOPT_MODE"] == "1"
    assert env["BULL_SCOPE_MODULE"] == ""


def test_failed_reruns_outside_adoption_are_not_adopt(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    seed_failed(rig, "app", "t::a\n")
    rig.run(GateMode.FAILED)
    (env,) = rig.runner.envs("rerun")
    assert env["BULL_ADOPT_MODE"] == "0"
    assert env["BULL_SCOPE_MODULE"] == ""


def test_all_gives_a_part_whose_setup_failed_no_journeys_call(
    tmp_path: Path,
) -> None:
    rig = make_rig(
        tmp_path,
        parts=[("a", make_stack("astack")), ("b", make_stack("bstack"))],
        modules=[("A", "a"), ("B", "b")],
        explicit_parts=True,
    )
    rig.runner.set("setup", part="a", code=1)
    run = rig.run(GateMode.ALL)
    assert rig.journeys.parts() == ["b"]
    assert run.verdict is Verdict.FAIL


def test_failing_run_with_skipped_coverage_on_a_dirty_tree_notes_gates_failed(
    tmp_path: Path,
) -> None:
    rig = clean_rig(tmp_path)
    rig.git.clean = False
    rig.runner.set("lint", code=1)
    run = rig.run(GateMode.MODULE, "Counter", skip_coverage=True)
    assert run.recorded is False
    assert run.note == "not recorded: gates failed"


def test_passing_run_with_skipped_coverage_on_a_dirty_tree_notes_coverage_skipped(
    tmp_path: Path,
) -> None:
    rig = clean_rig(tmp_path)
    rig.git.clean = False
    run = rig.run(GateMode.MODULE, "Counter", skip_coverage=True)
    assert run.verdict is Verdict.PASS
    assert run.recorded is False
    assert run.note == "not recorded: coverage skipped"


# --- coverage triage follow-ups -----------------------------------------


def _clean_module_rig(tmp_path: Path) -> Rig:
    rig = make_rig(tmp_path)
    rig.triage.result = CoverageReport("Counter", {}, (), (), ())
    return rig


def test_detached_head_skips_the_module_branch_check(tmp_path: Path) -> None:
    rig = _clean_module_rig(tmp_path)
    rig.git.branch = None
    run = rig.run(GateMode.MODULE, "Counter")
    assert run.verdict is Verdict.PASS


def test_recording_without_a_commit_at_head_is_refused(tmp_path: Path) -> None:
    rig = _clean_module_rig(tmp_path)
    del rig.git.heads["HEAD"]
    with pytest.raises(BullError) as exc:
        rig.run(GateMode.MODULE, "Counter")
    assert exc.value.message == "no commit at HEAD"
    assert exc.value.fix == "commit before recording a gate pass"
    assert rig.passes.recorded == []


def test_after_merge_without_a_branch_is_refused(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    with pytest.raises(BullError) as exc:
        rig.run(GateMode.AFTER_MERGE)
    assert exc.value.message == "gates --after-merge needs a branch"
    assert exc.value.fix == "run `bull gates --after-merge <branch>`"
    assert rig.runner.calls == []


def _exclude_passed(rig: Rig) -> object:
    rig.gates.coverage(rig.app, "Counter")
    return next(c for c in rig.triage.calls if c[0] == "sources")[1][3]


@pytest.mark.parametrize("key", ["coverage.exclude", "coverage.exclude_extra"])
def test_coverage_list_setting_given_as_a_string_is_a_one_item_list(
    tmp_path: Path, key: str
) -> None:
    rig = make_rig(tmp_path)
    rig.settings.values["coverage.exclude"] = ()
    rig.settings.values["coverage.exclude_extra"] = ()
    rig.settings.values[key] = "gen/*"
    assert _exclude_passed(rig) == ("gen/*",)


@pytest.mark.parametrize("key", ["coverage.exclude", "coverage.exclude_extra"])
def test_coverage_list_setting_given_as_an_empty_string_is_empty(
    tmp_path: Path, key: str
) -> None:
    rig = make_rig(tmp_path)
    rig.settings.values["coverage.exclude"] = ()
    rig.settings.values["coverage.exclude_extra"] = ()
    rig.settings.values[key] = ""
    assert _exclude_passed(rig) == ()


@pytest.mark.parametrize("key", ["coverage.exclude", "coverage.exclude_extra"])
@pytest.mark.parametrize("bad", [3, True])
def test_coverage_list_setting_that_is_not_a_list_is_refused(
    tmp_path: Path, key: str, bad: object
) -> None:
    rig = make_rig(tmp_path)
    rig.settings.values[key] = bad  # type: ignore[assignment]
    with pytest.raises(BullError) as exc:
        rig.gates.coverage(rig.app, "Counter")
    assert exc.value.message == f"setting {key} must be a list of strings"


def _merged(tmp_path: Path, changed: list[str]) -> Rig:
    from .rig import BRANCH_SHA

    rig = make_rig(tmp_path)
    rig.git.heads["feature/x"] = BRANCH_SHA
    rig.git.changed = changed
    rig.passes.records[BRANCH_SHA] = PassRecord(
        BRANCH_SHA, "feature/x", "gates Counter", rig.clock.now(), ("app",)
    )
    rig.triage.result = CoverageReport("Counter", {}, (), (), ())
    return rig


def test_bookkeeping_paths_given_as_a_string_is_a_one_item_list(
    tmp_path: Path,
) -> None:
    rig = _merged(tmp_path, ["CHANGELOG.md"])
    rig.settings.values["bookkeeping_paths"] = "CHANGELOG.md"
    run = rig.run(GateMode.AFTER_MERGE, branch="feature/x")
    assert run.note == "merge holds the gated code"
    assert rig.runner.calls == []


def test_bookkeeping_paths_given_as_an_empty_string_is_empty(tmp_path: Path) -> None:
    rig = _merged(tmp_path, ["docs/api/Counter.md"])
    rig.settings.values["bookkeeping_paths"] = ""
    rig.run(GateMode.AFTER_MERGE, branch="feature/x")
    assert rig.runner.calls != []


@pytest.mark.parametrize("bad", [3, True])
def test_bookkeeping_paths_that_is_not_a_list_is_refused(
    tmp_path: Path, bad: object
) -> None:
    rig = _merged(tmp_path, ["docs/api/Counter.md"])
    rig.settings.values["bookkeeping_paths"] = bad  # type: ignore[assignment]
    with pytest.raises(BullError) as exc:
        rig.run(GateMode.AFTER_MERGE, branch="feature/x")
    assert exc.value.message == "setting bookkeeping_paths must be a list of strings"
