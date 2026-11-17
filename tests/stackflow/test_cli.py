"""Tests for `bull.Modules.stackflow.cli` (a stack repo's `bull status`, install check).

Assumed shape (settled in the memo's unit 3 construction entry):
`register_status(commands, workflow, root)` adds `status` to the top-level subparsers, with
`workflow` and `root` as zero-argument providers.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.stackflow import cli
from bull.Modules.stackflow.Contracts import StackRepoStatus, StackStage
from bull.Modules.stackflow.mocks import MockStackWorkflow
from bull.Modules.stacks.Contracts import StackError
from bull.Modules.stacks.mocks import MockStackRegistry
from bull.Modules.stacktest.Contracts import StackTestReport
from bull.Modules.stacktest.mocks import MockStackTester


def _parser(workflow: MockStackWorkflow, root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    cli.register_status(commands, lambda: workflow, lambda: root)
    return parser


def _run(workflow: MockStackWorkflow, root: Path, argv: list[str]) -> tuple[int, str]:
    args = _parser(workflow, root).parse_args(argv)
    out = io.StringIO()
    code = args.run(args, out)
    return code, out.getvalue()


def _calls(workflow: MockStackWorkflow, name: str) -> list[tuple[object, ...]]:
    return [c[1] for c in workflow.calls if c[0] == name]


class _Refusing(MockStackWorkflow):
    def set_stage(self, path: Path, stage: int) -> StackRepoStatus:
        raise BullError("stage 2 needs the design-approved checkpoint")

    def checkpoint(self, path: Path, name: str) -> StackRepoStatus:
        raise BullError("checkpoint needs stage 5")

    def next_step(self, path: Path) -> str:
        raise BullError("not a stack repo")

    def ref(self, kind: str, name: str) -> str:
        raise BullError("unknown ref kind")

    def load(self, path: Path) -> StackRepoStatus:
        raise BullError("not a stack repo")


def test_providers_are_not_called_while_registering() -> None:
    def boom() -> object:
        raise AssertionError("called while registering")

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    cli.register_status(commands, boom, boom)  # type: ignore[arg-type]
    parser.parse_args(["status"])


def test_providers_are_not_called_while_parsing_a_subcommand() -> None:
    def boom() -> object:
        raise AssertionError("called while parsing")

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    cli.register_status(commands, boom, boom)  # type: ignore[arg-type]
    parser.parse_args(["status", "next"])


def test_status_loads_the_repo_at_the_root_and_prints_name_and_stage(
    tmp_path: Path,
) -> None:
    workflow = MockStackWorkflow()
    code, out = _run(workflow, tmp_path, ["status"])
    assert code == 0
    assert _calls(workflow, "load") == [(tmp_path,)]
    assert "stack: go_cli\n" in out
    assert "stage: 1 (discuss)\n" in out


def test_status_prints_checkpoints_and_passes(tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    workflow.status = StackRepoStatus(
        format=1,
        name="go_cli",
        stage=StackStage.GATE_CODE,
        checkpoints=("design-approved",),
        static_pass="abc1234",
        test_pass=None,
    )
    _, out = _run(workflow, tmp_path, ["status"])
    assert out == (
        "stack: go_cli\n"
        "stage: 4 (gate-code)\n"
        "checkpoints: design-approved\n"
        "static pass: abc1234\n"
        "test pass: none\n"
    )


def test_status_renders_unset_passes_and_empty_checkpoints_as_none(
    tmp_path: Path,
) -> None:
    _, out = _run(MockStackWorkflow(), tmp_path, ["status"])
    assert "checkpoints: none\n" in out
    assert "static pass: none\n" in out
    assert "test pass: none\n" in out


def test_status_lists_several_checkpoints_comma_separated(tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    workflow.status = StackRepoStatus(
        format=1,
        name="go_cli",
        stage=StackStage.FIXTURE,
        checkpoints=("a", "b"),
        static_pass=None,
        test_pass=None,
    )
    _, out = _run(workflow, tmp_path, ["status"])
    assert "checkpoints: a, b\n" in out


def test_status_json_writes_json_only(tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    workflow.status = StackRepoStatus(
        format=1,
        name="go_cli",
        stage=StackStage.FIXTURE,
        checkpoints=("design-approved",),
        static_pass=None,
        test_pass=None,
    )
    code, out = _run(workflow, tmp_path, ["status", "--json"])
    data = json.loads(out)
    assert code == 0
    assert isinstance(data, dict)
    assert data["name"] == "go_cli"
    assert data["stage"] == 3
    assert data["stage_name"] == "fixture"
    assert data["checkpoints"] == ["design-approved"]
    assert data["static_pass"] is None
    assert data["test_pass"] is None


def test_status_json_carries_the_pass_values(tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    workflow.status = StackRepoStatus(
        format=1,
        name="go_cli",
        stage=StackStage.GATE_CODE,
        checkpoints=(),
        static_pass="abc1234",
        test_pass="def5678",
    )
    _, out = _run(workflow, tmp_path, ["status", "--json"])
    data = json.loads(out)
    assert data["stage"] == 4
    assert data["stage_name"] == "gate-code"
    assert data["checkpoints"] == []
    assert data["static_pass"] == "abc1234"
    assert data["test_pass"] == "def5678"


def test_status_next_prints_the_next_step(tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    code, out = _run(workflow, tmp_path, ["status", "next"])
    assert code == 0
    assert _calls(workflow, "next_step") == [(tmp_path,)]
    assert workflow.next_step(tmp_path) in out


def test_status_stage_sets_the_stage_and_prints_the_result(tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    code, out = _run(workflow, tmp_path, ["status", "stage", "3"])
    assert code == 0
    assert _calls(workflow, "set_stage") == [(tmp_path, 3)]
    assert workflow.status.stage is StackStage.FIXTURE
    assert out == "stage: 3 (fixture)\n"


def test_status_checkpoint_records_the_checkpoint_and_prints_the_result(
    tmp_path: Path,
) -> None:
    workflow = MockStackWorkflow()
    code, out = _run(workflow, tmp_path, ["status", "checkpoint", "design-approved"])
    assert code == 0
    assert _calls(workflow, "checkpoint") == [(tmp_path, "design-approved")]
    assert out == "checkpoints: design-approved\n"


@pytest.mark.parametrize("kind", ["branch", "tag"])
def test_status_ref_prints_the_ref(kind: str, tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    code, out = _run(workflow, tmp_path, ["status", "ref", kind, "fixture"])
    assert code == 0
    assert _calls(workflow, "ref") == [(kind, "fixture")]
    assert "stack/fixture" in out


def test_status_ref_rejects_an_unknown_kind(tmp_path: Path) -> None:
    workflow = MockStackWorkflow()
    with pytest.raises(SystemExit):
        _parser(workflow, tmp_path).parse_args(["status", "ref", "commit", "x"])


@pytest.mark.parametrize(
    "argv",
    [
        ["status"],
        ["status", "next"],
        ["status", "stage", "2"],
        ["status", "checkpoint", "design-approved"],
        ["status", "ref", "tag", "design-approved"],
    ],
)
def test_a_refusal_from_the_workflow_propagates_as_bull_error(
    argv: list[str], tmp_path: Path
) -> None:
    with pytest.raises(BullError):
        _run(_Refusing(), tmp_path, argv)


def test_before_install_refuses_a_failing_folder(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = StackTestReport("mystack", True, ("rules.md missing",), ())
    check = cli.before_install(lambda: tester, lambda: registry)
    with pytest.raises(StackError, match="rules.md missing"):
        check(tmp_path / "mystack")


def test_before_install_passes_an_ok_folder(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    check = cli.before_install(lambda: tester, lambda: registry)
    assert check(tmp_path / "mystack") is None
    assert "install" not in [c[0] for c in registry.calls]


def test_before_install_does_not_call_providers_until_the_check_runs(
    tmp_path: Path,
) -> None:
    def boom() -> object:
        raise AssertionError("called too early")

    check = cli.before_install(boom, boom)  # type: ignore[arg-type]
    assert callable(check)


def test_design_template_is_the_design_md_text() -> None:
    text = cli.design_template()
    assert "## Language and tools" in text
    assert "## Decisions log" in text


def test_design_template_with_the_file_missing_says_to_reinstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_DESIGN_TEMPLATE", tmp_path / "missing" / "DESIGN.md")
    with pytest.raises(BullError) as error:
        cli.design_template()
    assert "reinstall" in f"{error.value.message} {error.value.fix}"
