"""Tests for `bull.Modules.stackflow.workflow`: init, load, stages, checkpoints, passes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.stackflow.Contracts import StackStage

from .workflow_support import (
    at_stage,
    commit,
    git,
    git_identity,
    head,
    make_workflow,
    new_repo,
    report,
)


@pytest.fixture(autouse=True)
def _git(monkeypatch: pytest.MonkeyPatch) -> None:
    git_identity(monkeypatch)


def fails(error: pytest.ExceptionInfo[BullError]) -> str:
    return f"{error.value.message} {error.value.fix}"


# --- init


def test_init_creates_a_stack_repo_named_after_the_folder(tmp_path: Path) -> None:
    path = tmp_path / "my_stack"
    status = make_workflow().init(path)
    assert path.is_dir()
    assert git(path, "rev-parse", "--is-inside-work-tree").strip() == "true"
    assert status.name == "my_stack"
    assert status.stage is StackStage.DISCUSS
    assert status.format == 1
    assert status.checkpoints == ()
    assert status.static_pass is None
    assert status.test_pass is None


def test_init_writes_the_status_file(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    data = json.loads((path / ".bull" / "status.json").read_text())
    assert data["format"] == 1
    assert data["kind"] == "stack"
    assert data["name"] == "my_stack"
    assert data["stage"] == 1
    assert data["checkpoints"] == []


def test_init_writes_stack_toml_with_the_name_filled_and_todo_placeholders(
    tmp_path: Path,
) -> None:
    import tomllib

    path = new_repo(tmp_path)
    text = (path / "stack.toml").read_text()
    assert tomllib.loads(text)["stack"]["name"] == "my_stack"
    assert "TODO" in text


def test_init_writes_design_md_with_the_template_sections(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    text = (path / "DESIGN.md").read_text()
    assert "## Language and tools" in text
    assert "## Decisions log" in text


def test_init_writes_a_gitignore(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    assert (path / ".gitignore").is_file()


def test_init_makes_one_commit_with_the_init_message(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    assert git(path, "log", "--format=%s").splitlines() == ["chore: bull init --stack"]


def test_init_leaves_a_clean_tree(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    assert git(path, "status", "--porcelain").strip() == ""


def test_init_writes_no_provider_files(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    assert not (path / "CLAUDE.md").exists()
    assert not (path / ".claude").exists()


def test_init_accepts_an_existing_empty_folder(tmp_path: Path) -> None:
    path = tmp_path / "my_stack"
    path.mkdir()
    assert make_workflow().init(path).name == "my_stack"


@pytest.mark.parametrize("name", ["Bad-Name", "1abc", "has space", "UPPER", "a.b"])
def test_init_refuses_an_invalid_name_and_creates_nothing(
    tmp_path: Path, name: str
) -> None:
    path = tmp_path / name
    with pytest.raises(BullError):
        make_workflow().init(path)
    assert not path.exists()


def test_init_refuses_the_reserved_template_name_and_creates_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "_template"
    with pytest.raises(BullError):
        make_workflow().init(path)
    assert not path.exists()


@pytest.mark.parametrize("name", ["python_cli", "fixture"])
def test_init_refuses_a_built_in_stack_name_and_creates_nothing(
    tmp_path: Path, name: str
) -> None:
    path = tmp_path / name
    with pytest.raises(BullError):
        make_workflow().init(path)
    assert not path.exists()


def test_init_refuses_a_non_empty_folder_and_leaves_it_untouched(
    tmp_path: Path,
) -> None:
    path = tmp_path / "my_stack"
    path.mkdir()
    (path / "notes.txt").write_text("keep me")
    with pytest.raises(BullError):
        make_workflow().init(path)
    assert sorted(p.name for p in path.iterdir()) == ["notes.txt"]


def test_init_refuses_inside_a_bull_app_and_creates_nothing(tmp_path: Path) -> None:
    app = tmp_path / "app"
    (app / ".bull").mkdir(parents=True)
    (app / ".bull" / "config.toml").write_text("format = 1\n")
    (app / ".bull" / "status.json").write_text('{"format": 1, "kind": "app"}\n')
    path = app / "my_stack"
    with pytest.raises(BullError):
        make_workflow().init(path)
    assert not path.exists()


# --- load


def test_load_returns_the_state_init_wrote(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status = make_workflow().load(path)
    assert status.name == "my_stack"
    assert status.stage is StackStage.DISCUSS
    assert status.checkpoints == ()


def test_load_refuses_a_folder_that_is_not_a_stack_repo(tmp_path: Path) -> None:
    with pytest.raises(BullError):
        make_workflow().load(tmp_path)


def test_load_refuses_an_app_status_file(tmp_path: Path) -> None:
    (tmp_path / ".bull").mkdir()
    (tmp_path / ".bull" / "status.json").write_text(
        '{"format": 1, "kind": "app", "stage": 1, "checkpoints": []}\n'
    )
    with pytest.raises(BullError):
        make_workflow().load(tmp_path)


# --- set_stage


def test_set_stage_two_is_refused_without_design_approved(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    with pytest.raises(BullError) as error:
        make_workflow().set_stage(path, 2)
    assert "design-approved" in fails(error)
    assert make_workflow().load(path).stage is StackStage.DISCUSS


def test_set_stage_two_moves_on_after_design_approved(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    workflow = make_workflow()
    workflow.checkpoint(path, "design-approved")
    assert workflow.set_stage(path, 2).stage is StackStage.SCAFFOLD
    assert workflow.load(path).stage is StackStage.SCAFFOLD


def test_set_stage_three_follows_stage_two(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    assert at_stage(path, 3).stage is StackStage.FIXTURE


def test_set_stage_four_is_refused_without_a_static_pass(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 3)
    commit(path)
    with pytest.raises(BullError) as error:
        make_workflow().set_stage(path, 4)
    assert "static" in fails(error)
    assert make_workflow().load(path).stage is StackStage.FIXTURE


def test_set_stage_four_is_refused_when_the_static_pass_is_for_an_older_head(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 3)
    commit(path)
    make_workflow().record_test(path, report(static=True))
    (path / "more.txt").write_text("new work")
    commit(path)
    with pytest.raises(BullError):
        make_workflow().set_stage(path, 4)


def test_set_stage_four_is_refused_when_only_a_full_pass_exists(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 3)
    commit(path)
    make_workflow().record_test(path, report(static=False))
    with pytest.raises(BullError):
        make_workflow().set_stage(path, 4)


def test_set_stage_four_moves_on_with_a_static_pass_at_head(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    assert at_stage(path, 4).stage is StackStage.GATE_CODE


def test_set_stage_five_is_refused_without_a_full_test_pass(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 4)
    commit(path)
    with pytest.raises(BullError) as error:
        make_workflow().set_stage(path, 5)
    assert "test" in fails(error)
    assert make_workflow().load(path).stage is StackStage.GATE_CODE


def test_set_stage_five_moves_on_with_a_full_test_pass(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status = at_stage(path, 5)
    assert status.stage is StackStage.REVIEW
    assert make_workflow().load(path).stage is StackStage.REVIEW


# --- checkpoint


def test_checkpoint_design_approved_is_recorded(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status = make_workflow().checkpoint(path, "design-approved")
    assert status.checkpoints == ("design-approved",)
    assert make_workflow().load(path).checkpoints == ("design-approved",)


def test_checkpoint_unknown_name_is_refused_and_not_recorded(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    with pytest.raises(BullError):
        make_workflow().checkpoint(path, "outline-approved")
    assert make_workflow().load(path).checkpoints == ()


def test_checkpoint_rules_approved_is_refused_before_stage_five(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 4)
    with pytest.raises(BullError) as error:
        make_workflow().checkpoint(path, "rules-approved")
    assert "rules-approved" not in make_workflow().load(path).checkpoints
    assert "5" in fails(error) or "review" in fails(error)


def test_checkpoint_rules_approved_is_recorded_at_stage_five(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 5)
    status = make_workflow().checkpoint(path, "rules-approved")
    assert "rules-approved" in status.checkpoints


def _ready_to_accept(path: Path) -> None:
    """Stage 5 with rules-approved, committed, and a full pass at the final HEAD."""
    at_stage(path, 5)
    make_workflow().checkpoint(path, "rules-approved")
    commit(path)
    make_workflow().record_test(path, report(static=False))


def test_checkpoint_accepted_is_recorded_with_rules_approved_and_a_full_pass(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    _ready_to_accept(path)
    status = make_workflow().checkpoint(path, "accepted")
    assert "accepted" in status.checkpoints


def test_checkpoint_accepted_is_refused_without_rules_approved(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 5)
    commit(path)
    make_workflow().record_test(path, report(static=False))
    with pytest.raises(BullError) as error:
        make_workflow().checkpoint(path, "accepted")
    assert "rules-approved" in fails(error)


def test_checkpoint_accepted_is_refused_when_the_full_pass_is_for_an_older_head(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    _ready_to_accept(path)
    (path / "later.txt").write_text("later")
    commit(path)
    with pytest.raises(BullError):
        make_workflow().checkpoint(path, "accepted")


def test_checkpoint_accepted_is_refused_on_a_dirty_tree(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    _ready_to_accept(path)
    (path / "scratch.txt").write_text("uncommitted")
    with pytest.raises(BullError):
        make_workflow().checkpoint(path, "accepted")
    assert "accepted" not in make_workflow().load(path).checkpoints


# --- record_test


def test_record_test_stores_head_as_the_static_pass(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status = make_workflow().record_test(path, report(static=True))
    assert status.static_pass == head(path)
    assert status.test_pass is None
    assert make_workflow().load(path).static_pass == head(path)


def test_record_test_stores_head_as_the_full_test_pass(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status = make_workflow().record_test(path, report(static=False))
    assert status.test_pass == head(path)
    assert status.static_pass is None
    assert make_workflow().load(path).test_pass == head(path)


def test_record_test_ignores_a_report_that_is_not_ok(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status = make_workflow().record_test(path, report(ok=False, static=False))
    assert status.test_pass is None
    assert make_workflow().load(path).test_pass is None


def test_record_test_ignores_a_not_ok_static_report(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status = make_workflow().record_test(path, report(ok=False, static=True))
    assert status.static_pass is None


def test_record_test_ignores_a_pass_on_a_dirty_tree(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    (path / "scratch.txt").write_text("uncommitted")
    status = make_workflow().record_test(path, report(static=False))
    assert status.test_pass is None
    assert make_workflow().load(path).test_pass is None


def test_record_test_keeps_an_earlier_pass_when_a_later_report_fails(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    first = head(path)
    make_workflow().record_test(path, report(static=False))
    (path / "more.txt").write_text("more")
    commit(path)
    status = make_workflow().record_test(path, report(ok=False, static=False))
    assert status.test_pass == first


def test_record_test_replaces_the_pass_with_the_new_head(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    make_workflow().record_test(path, report(static=False))
    (path / "more.txt").write_text("more")
    second = commit(path)
    status = make_workflow().record_test(path, report(static=False))
    assert status.test_pass == second


# --- next_step


def test_next_step_at_stage_one_says_to_discuss_and_approve_the_design(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    text = make_workflow().next_step(path)
    assert "DESIGN.md" in text
    assert "design-approved" in text


def test_next_step_at_the_fixture_stage_points_at_the_static_self_test(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 3)
    text = make_workflow().next_step(path)
    assert "cases.json" in text
    assert "--static" in text


def test_next_step_gives_a_different_instruction_for_each_stage(
    tmp_path: Path,
) -> None:
    steps = []
    for stage in range(1, 6):
        path = new_repo(tmp_path, f"stack_{stage}")
        at_stage(path, stage)
        steps.append(make_workflow().next_step(path))
    assert all(step.strip() for step in steps)
    assert len(set(steps)) == 5


# --- ref


@pytest.mark.parametrize(
    "checkpoint", ["design-approved", "rules-approved", "accepted"]
)
def test_ref_tags_a_checkpoint_under_stack(checkpoint: str) -> None:
    assert make_workflow().ref("tag", checkpoint) == f"stack/{checkpoint}"


@pytest.mark.parametrize("stage", ["scaffold", "fixture", "gate-code", "review"])
def test_ref_branches_a_stage_under_stack(stage: str) -> None:
    assert make_workflow().ref("branch", stage) == f"stack/{stage}"
