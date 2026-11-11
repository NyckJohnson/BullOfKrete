"""Tests for `bull.Modules.gates.steps`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.events.Contracts import EventKind
from bull.Modules.events.mocks import MockEventLog
from bull.Modules.foundation.Contracts import RunResult
from bull.Modules.foundation.mocks import MockFiles, MockRunner, sample_layout
from bull.Modules.gates.Contracts import Gate, StepResult, Verdict
from bull.Modules.gates.steps import (
    PLACEHOLDERS,
    LiveSteps,
    StepOutput,
    fill,
    settings_json,
    step_env,
)
from bull.Modules.parts.mocks import sample_part
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.stacks.mocks import sample_stack

ROOT = Path("/tmp/apps/tally")
APP = sample_layout(ROOT)
RESULTS = ROOT / ".bull" / "results" / "app"


# --- fill ---------------------------------------------------------------


def test_placeholders_name_every_documented_placeholder() -> None:
    assert set(PLACEHOLDERS) >= {
        "python",
        "stack_dir",
        "app_root",
        "part_root",
        "results",
        "module",
        "module_src",
        "module_tests",
        "port",
        "failed_ids",
    }


def test_fill_replaces_a_placeholder_alone_in_an_argument() -> None:
    assert fill(["{python}", "run"], {"python": "/usr/bin/python"}) == [
        "/usr/bin/python",
        "run",
    ]


def test_fill_replaces_a_placeholder_inside_an_argument() -> None:
    assert fill(["{stack_dir}/gates.py"], {"stack_dir": "/stacks/x"}) == [
        "/stacks/x/gates.py"
    ]


def test_fill_replaces_several_placeholders_in_one_argument() -> None:
    values = {"app_root": "/a", "module": "Counter"}
    assert fill(["{app_root}/{module}"], values) == ["/a/Counter"]


def test_fill_replaces_a_repeated_placeholder() -> None:
    assert fill(["{module}-{module}"], {"module": "m"}) == ["m-m"]


def test_fill_expands_failed_ids_to_one_argument_per_id() -> None:
    assert fill(["pytest", "{failed_ids}"], {}, ["a::1", "b::2"]) == [
        "pytest",
        "a::1",
        "b::2",
    ]


def test_fill_removes_failed_ids_when_there_are_none() -> None:
    assert fill(["rerun", "{failed_ids}"], {}) == ["rerun"]


def test_fill_removes_failed_ids_for_an_empty_list() -> None:
    assert fill(["rerun", "{failed_ids}"], {}, []) == ["rerun"]


def test_fill_keeps_failed_ids_in_position_between_other_arguments() -> None:
    assert fill(["a", "{failed_ids}", "z"], {}, ["x", "y"]) == ["a", "x", "y", "z"]


def test_fill_missing_value_becomes_empty_string() -> None:
    assert fill(["{module_src}", "x{module}y"], {}) == ["", "xy"]


def test_fill_keeps_unknown_braces_as_is() -> None:
    assert fill(["{nope}", "a{b}c", "{", "}"], {"nope": "X"}) == [
        "{nope}",
        "a{b}c",
        "{",
        "}",
    ]


def test_fill_keeps_json_like_braces() -> None:
    assert fill(['{"a": 1}'], {}) == ['{"a": 1}']


def test_fill_leaves_plain_arguments_unchanged() -> None:
    assert fill(["--flag", "value"], {"module": "m"}) == ["--flag", "value"]


def test_fill_failed_ids_embedded_in_a_longer_argument_is_not_expanded() -> None:
    result = fill(["--ids={failed_ids}"], {"failed_ids": "q"}, ["a", "b"])
    assert len(result) == 1


def test_fill_does_not_mutate_its_input() -> None:
    argv = ["{module}"]
    fill(argv, {"module": "m"})
    assert argv == ["{module}"]


# --- step_env -----------------------------------------------------------


def env_for(
    *, adopt: bool = False, scope: str | None = None, base: dict[str, str] | None = None
) -> dict[str, str]:
    part = sample_part(ROOT, "app")
    stack = sample_stack("fixture")
    return step_env(
        base if base is not None else {},
        APP,
        part,
        stack,
        RESULTS,
        '{"k": 1}',
        adopt,
        scope,
    )


def test_step_env_sets_the_part_and_path_variables() -> None:
    env = env_for()
    stack = sample_stack("fixture")
    assert env["BULL_PART"] == "app"
    assert env["BULL_PART_ROOT"] == str(ROOT)
    assert env["BULL_APP_ROOT"] == str(ROOT)
    assert env["BULL_RESULTS"] == str(RESULTS)
    assert env["BULL_STACK_DIR"] == str(stack.home)


def test_step_env_sets_settings_json_verbatim() -> None:
    assert env_for()["BULL_SETTINGS"] == '{"k": 1}'


def test_step_env_not_adopting_gives_zero_and_empty_scope() -> None:
    env = env_for()
    assert env["BULL_ADOPT_MODE"] == "0"
    assert env["BULL_SCOPE_MODULE"] == ""


def test_step_env_adopting_gives_one() -> None:
    assert env_for(adopt=True)["BULL_ADOPT_MODE"] == "1"


def test_step_env_scope_module_is_passed_through() -> None:
    assert env_for(adopt=True, scope="Counter")["BULL_SCOPE_MODULE"] == "Counter"


def test_step_env_keeps_the_base_environment() -> None:
    env = env_for(base={"PATH": "/bin", "HOME": "/home/x"})
    assert env["PATH"] == "/bin"
    assert env["HOME"] == "/home/x"


def test_step_env_overrides_base_values_for_bull_variables() -> None:
    env = env_for(base={"BULL_PART": "stale", "BULL_ADOPT_MODE": "1"})
    assert env["BULL_PART"] == "app"
    assert env["BULL_ADOPT_MODE"] == "0"


def test_step_env_does_not_mutate_the_base() -> None:
    base = {"PATH": "/bin"}
    env_for(base=base)
    assert base == {"PATH": "/bin"}


def test_step_env_paths_are_absolute() -> None:
    env = env_for()
    for key in ("BULL_PART_ROOT", "BULL_APP_ROOT", "BULL_RESULTS", "BULL_STACK_DIR"):
        assert Path(env[key]).is_absolute()


# --- settings_json ------------------------------------------------------


def test_settings_json_maps_every_shown_key_to_its_value() -> None:
    settings = MockSettings()
    out = json.loads(settings_json(settings, None))
    assert out == {r.key: r.value for r in settings.show(None)}


def test_settings_json_sorts_keys() -> None:
    text = settings_json(MockSettings(), None)
    keys = list(json.loads(text))
    assert keys == sorted(keys)
    assert text.index(f'"{keys[0]}"') < text.index(f'"{keys[-1]}"')


def test_settings_json_writes_tuples_as_lists() -> None:
    settings = MockSettings()
    settings.values["models.reviewer"] = ("a", "b")
    out = json.loads(settings_json(settings, None))
    assert out["models.reviewer"] == ["a", "b"]


def test_settings_json_uses_the_given_part_layer() -> None:
    settings = MockSettings()
    settings.parts["web"] = {"max_attempts": 9}
    assert json.loads(settings_json(settings, "web"))["max_attempts"] == 9
    assert json.loads(settings_json(settings, None))["max_attempts"] == 3


def test_settings_json_asks_settings_for_the_part() -> None:
    settings = MockSettings()
    settings_json(settings, "web")
    assert ("show", ("web",)) in settings.calls


# --- LiveSteps.execute --------------------------------------------------


def make() -> tuple[LiveSteps, MockRunner, MockEventLog, MockFiles]:
    runner = MockRunner()
    events = MockEventLog()
    files = MockFiles()
    return LiveSteps(runner, events, files), runner, events, files


def run_result(
    stdout: str = "", stderr: str = "", code: int = 0, seconds: float = 0.5
) -> RunResult:
    return RunResult(
        argv=("tool",), returncode=code, stdout=stdout, stderr=stderr, seconds=seconds
    )


def execute(
    steps: LiveSteps, step: str = "lint", argv: tuple[str, ...] = ("tool", "x")
) -> StepOutput:
    return steps.execute(step, list(argv), ROOT, {"K": "V"}, RESULTS)


def test_execute_runs_argv_in_cwd_with_env_and_no_timeout() -> None:
    steps, runner, _, _ = make()
    execute(steps, argv=("tool", "a", "b"))
    assert runner.calls == [("run", (("tool", "a", "b"), ROOT, {"K": "V"}, None))]


def test_execute_exit_zero_gives_no_labels() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(stdout="all good\n")
    out = execute(steps)
    assert out.exit == 0
    assert out.labels == ()


def test_execute_returns_the_runner_seconds() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(seconds=2.5)
    assert execute(steps).seconds == 2.5


def test_execute_writes_stdout_then_stderr_to_the_step_log() -> None:
    steps, runner, _, files = make()
    runner.results["tool"] = run_result(stdout="OUT-LINE\n", stderr="ERR-LINE\n")
    execute(steps, step="build_test")
    log = files.texts[RESULTS / "build_test.log"]
    assert "OUT-LINE" in log
    assert "ERR-LINE" in log
    assert log.index("OUT-LINE") < log.index("ERR-LINE")


def test_execute_log_is_written_atomically() -> None:
    steps, runner, _, files = make()
    runner.results["tool"] = run_result(stdout="x\n")
    execute(steps, step="lint")
    assert any(
        c[0] == "write_atomic" and c[1][0] == RESULTS / "lint.log" for c in files.calls
    )


def test_execute_collects_bull_fail_lines_as_labels_in_order() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(
        stdout="noise\nbull-fail: first\nmore\nbull-fail: second\n", code=1
    )
    assert execute(steps).labels == ("first", "second")


def test_execute_strips_prefix_and_surrounding_spaces_from_labels() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(
        stdout="bull-fail:    spaced label   \n", code=1
    )
    assert execute(steps).labels == ("spaced label",)


def test_execute_ignores_bull_fail_text_that_is_not_at_line_start() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(stdout="see bull-fail: x\n", code=1)
    assert execute(steps).labels == ("lint failed (exit 1)",)


def test_execute_ignores_bull_fail_lines_on_stderr() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(stderr="bull-fail: nope\n", code=3)
    assert execute(steps).labels == ("lint failed (exit 3)",)


def test_execute_nonzero_without_labels_gets_the_default_label() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(stdout="oops\n", code=7)
    out = execute(steps, step="build_test")
    assert out.exit == 7
    assert out.labels == ("build_test failed (exit 7)",)


def test_execute_nonzero_with_labels_does_not_add_the_default_label() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(stdout="bull-fail: real\n", code=1)
    assert execute(steps).labels == ("real",)


def test_execute_tail_is_the_last_forty_lines_of_the_log() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(
        stdout="".join(f"line{i}\n" for i in range(100))
    )
    tail = execute(steps).tail.splitlines()
    assert len(tail) == 40
    assert tail[0] == "line60"
    assert tail[-1] == "line99"


def test_execute_tail_of_a_short_log_is_the_whole_log() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(stdout="a\nb\nc\n")
    assert execute(steps).tail.splitlines() == ["a", "b", "c"]


def test_execute_tail_includes_stderr_lines() -> None:
    steps, runner, _, _ = make()
    runner.results["tool"] = run_result(stdout="a\n", stderr="problem\n")
    assert "problem" in execute(steps).tail


def test_execute_with_no_output_has_an_empty_tail() -> None:
    steps, _, _, _ = make()
    assert execute(steps).tail == ""


def test_step_output_is_frozen() -> None:
    out = StepOutput(exit=0, labels=(), tail="", seconds=0.0)
    with pytest.raises(AttributeError):
        out.exit = 1  # type: ignore[misc]


# --- LiveSteps.result ---------------------------------------------------


def gate_events(events: MockEventLog) -> list[tuple[str, dict[str, object]]]:
    return [
        (e.kind.value, dict(e.data))
        for e in events.read()
        if e.kind is EventKind.GATE_STEP
    ]


def test_result_builds_a_step_result_with_the_given_fields() -> None:
    steps, _, _, _ = make()
    got = steps.result(
        Gate.LINT, "app", "Counter", Verdict.FAIL, ["a", "b"], 1.5, "tail"
    )
    assert got == StepResult(
        gate=Gate.LINT,
        part="app",
        module="Counter",
        verdict=Verdict.FAIL,
        labels=("a", "b"),
        seconds=1.5,
        output_tail="tail",
    )


def test_result_labels_are_a_tuple() -> None:
    steps, _, _, _ = make()
    got = steps.result(Gate.API, "app", None, Verdict.PASS, [], 0.0, "")
    assert got.labels == ()
    assert isinstance(got.labels, tuple)


def test_result_appends_exactly_one_gate_step_event() -> None:
    steps, _, events, _ = make()
    steps.result(Gate.LINT, "app", "Counter", Verdict.PASS, [], 0.25, "")
    assert len(gate_events(events)) == 1


def test_result_event_data_has_gate_part_module_verdict_seconds() -> None:
    steps, _, events, _ = make()
    steps.result(Gate.COVERAGE, "web", "Counter", Verdict.FAIL, ["x"], 3.5, "t")
    assert gate_events(events) == [
        (
            "gate_step",
            {
                "gate": "coverage",
                "part": "web",
                "module": "Counter",
                "verdict": "fail",
                "seconds": 3.5,
            },
        )
    ]


def test_result_event_module_is_none_when_there_is_no_module() -> None:
    steps, _, events, _ = make()
    steps.result(Gate.INTERFACE, "", None, Verdict.PASS, [], 0.0, "")
    ((_, data),) = gate_events(events)
    assert data["module"] is None
    assert data["part"] == ""


@pytest.mark.parametrize(
    ("verdict", "value"),
    [(Verdict.PASS, "pass"), (Verdict.FAIL, "fail"), (Verdict.ABORTED, "aborted")],
)
def test_result_event_verdict_is_the_enum_value(verdict: Verdict, value: str) -> None:
    steps, _, events, _ = make()
    steps.result(Gate.PREFLIGHT, "app", None, verdict, [], 0.0, "")
    ((_, data),) = gate_events(events)
    assert data["verdict"] == value


def test_each_result_call_appends_its_own_event() -> None:
    steps, _, events, _ = make()
    steps.result(Gate.SETUP, "app", None, Verdict.PASS, [], 0.0, "")
    steps.result(Gate.BUILD, "app", None, Verdict.PASS, [], 0.0, "")
    assert [d["gate"] for _, d in gate_events(events)] == ["setup", "build"]
