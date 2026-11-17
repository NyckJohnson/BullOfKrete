"""Tests for the stackflow mocks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.stackflow.Contracts import (
    StackInstaller,
    StackRepoStatus,
    StackStage,
    StackWorkflow,
)
from bull.Modules.stackflow.mocks import (
    SAMPLE_SHA,
    MockStackInstaller,
    MockStackWorkflow,
)
from bull.Modules.stacks.Contracts import Maturity
from bull.Modules.stacktest.Contracts import (
    CaseResult,
    CaseVerdict,
    StackTestReport,
)

PATH = Path("/tmp/go_cli")


def _report(static: bool) -> StackTestReport:
    cases = (
        ()
        if static
        else (CaseResult(id="c", verdict=CaseVerdict.PASS, expected="p", got="p"),)
    )
    return StackTestReport(stack="go_cli", static=static, problems=(), cases=cases)


def test_workflow_mock_satisfies_protocol() -> None:
    workflow: StackWorkflow = MockStackWorkflow()
    assert isinstance(workflow, MockStackWorkflow)


def test_workflow_starts_as_go_cli_at_stage_one() -> None:
    mock = MockStackWorkflow()
    assert mock.calls == []
    assert mock.status == StackRepoStatus(
        format=1,
        name="go_cli",
        stage=StackStage.DISCUSS,
        checkpoints=(),
        static_pass=None,
        test_pass=None,
    )


def test_load_returns_status_and_records_call() -> None:
    mock = MockStackWorkflow()
    assert mock.load(PATH) is mock.status
    assert mock.calls == [("load", (PATH,))]


def test_init_names_the_status_after_the_folder() -> None:
    mock = MockStackWorkflow()
    status = mock.init(Path("/x/my_stack"))
    assert status.name == "my_stack"
    assert status.stage is StackStage.DISCUSS
    assert mock.load(PATH).name == "my_stack"
    assert mock.calls[0] == ("init", (Path("/x/my_stack"),))


@pytest.mark.parametrize("stage", [1, 2, 3, 4, 5, 6])
def test_set_stage_applies_any_stage_without_rules(stage: int) -> None:
    mock = MockStackWorkflow()
    status = mock.set_stage(PATH, stage)
    assert status.stage == StackStage(stage)
    assert mock.load(PATH).stage == StackStage(stage)
    assert mock.calls[0] == ("set_stage", (PATH, stage))


def test_set_stage_rejects_an_unknown_stage_number() -> None:
    with pytest.raises(ValueError):
        MockStackWorkflow().set_stage(PATH, 9)


def test_checkpoint_is_added_without_needing_a_stage() -> None:
    mock = MockStackWorkflow()
    status = mock.checkpoint(PATH, "accepted")
    assert status.checkpoints == ("accepted",)
    assert mock.calls == [("checkpoint", (PATH, "accepted"))]


def test_checkpoints_keep_order_and_ignore_repeats() -> None:
    mock = MockStackWorkflow()
    mock.checkpoint(PATH, "design-approved")
    mock.checkpoint(PATH, "rules-approved")
    status = mock.checkpoint(PATH, "design-approved")
    assert status.checkpoints == ("design-approved", "rules-approved")
    assert len(mock.calls) == 3


def test_record_test_with_static_report_sets_static_pass() -> None:
    mock = MockStackWorkflow()
    status = mock.record_test(PATH, _report(static=True))
    assert status.static_pass == SAMPLE_SHA
    assert status.test_pass is None
    assert mock.calls[0][0] == "record_test"


def test_record_test_with_full_report_sets_test_pass() -> None:
    mock = MockStackWorkflow()
    report = _report(static=False)
    status = mock.record_test(PATH, report)
    assert status.test_pass == SAMPLE_SHA
    assert status.static_pass is None
    assert mock.calls == [("record_test", (PATH, report))]


@pytest.mark.parametrize("static", [True, False])
def test_record_test_with_failing_report_leaves_status_unchanged(static: bool) -> None:
    mock = MockStackWorkflow()
    report = replace(_report(static=static), problems=("boom",))
    assert not report.ok
    status = mock.record_test(PATH, report)
    assert status.static_pass is None
    assert status.test_pass is None
    assert mock.calls == [("record_test", (PATH, report))]


def test_next_step_returns_the_discuss_instruction_and_records_call() -> None:
    mock = MockStackWorkflow()
    step = mock.next_step(PATH)
    assert "DESIGN.md" in step
    assert "design-approved" in step
    assert mock.calls == [("next_step", (PATH,))]


@pytest.mark.parametrize(
    ("kind", "name"),
    [("tag", "design-approved"), ("branch", "fixture"), ("tag", "accepted")],
)
def test_ref_returns_stack_slash_name(kind: str, name: str) -> None:
    mock = MockStackWorkflow()
    assert mock.ref(kind, name) == f"stack/{name}"
    assert mock.calls == [("ref", (kind, name))]


def test_workflow_instances_do_not_share_state() -> None:
    first, second = MockStackWorkflow(), MockStackWorkflow()
    first.checkpoint(PATH, "design-approved")
    assert second.status.checkpoints == ()
    assert second.calls == []


def test_installer_mock_satisfies_protocol() -> None:
    installer: StackInstaller = MockStackInstaller()
    assert isinstance(installer, MockStackInstaller)


def test_installer_starts_with_no_calls() -> None:
    assert MockStackInstaller().calls == []


def test_install_returns_a_stack_named_after_the_folder() -> None:
    mock = MockStackInstaller()
    stack = mock.install(Path("/x/my_stack"))
    assert stack.manifest.name == "my_stack"
    assert mock.calls == [("install", (Path("/x/my_stack"),))]


def test_install_returns_an_experimental_stack() -> None:
    stack = MockStackInstaller().install(PATH)
    assert stack.manifest.maturity is Maturity.EXPERIMENTAL
