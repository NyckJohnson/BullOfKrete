"""Tests for `bull.Modules.stackflow.workflow`: init, load, stages, checkpoints, passes."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import BullError, FileFormatError
from bull.Modules.foundation.files import LiveFiles
from bull.Modules.foundation.layout import LiveLayouts
from bull.Modules.foundation.runner import LiveRunner
from bull.Modules.gitrepo.git import LiveGit
from bull.Modules.stackflow import workflow as wf
from bull.Modules.stackflow.Contracts import StackStage
from bull.Modules.stackflow.workflow import LiveStackWorkflow
from bull.Modules.stacks.mocks import MockStackRegistry

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


def test_status_file_holds_only_format_kind_name_stage_and_checkpoints(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    data = json.loads((path / ".bull" / "status.json").read_text())
    assert set(data) == {"format", "kind", "name", "stage", "checkpoints"}


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


def test_init_titles_design_md_with_the_stack_name(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    first = (path / "DESIGN.md").read_text().splitlines()[0]
    assert first == "# my_stack stack: design"


def test_init_design_md_title_uses_the_folder_name(tmp_path: Path) -> None:
    path = new_repo(tmp_path, "other_stack")
    first = (path / "DESIGN.md").read_text().splitlines()[0]
    assert first == "# other_stack stack: design"


def test_init_design_md_keeps_every_template_section(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    text = (path / "DESIGN.md").read_text()
    for section in [
        "Language and tools",
        "Contracts",
        "Modules",
        "Kind",
        "Human setup",
        "Adoption support",
        "Interfaces and running",
        "Decisions log",
    ]:
        assert f"## {section}" in text


def test_init_writes_cases_json_equal_to_the_template(tmp_path: Path) -> None:
    import bull.Modules.stackflow as stackflow_package

    template = Path(stackflow_package.__file__).parent / "template" / "cases.json"
    path = new_repo(tmp_path)
    written = json.loads((path / "cases.json").read_text())
    assert written == json.loads(template.read_text())


def test_init_commits_cases_json_in_the_init_commit(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    files = git(path, "show", "--name-only", "--format=", "HEAD").split()
    assert "cases.json" in files
    assert git(path, "ls-files", "cases.json").strip() == "cases.json"


def test_init_keeps_the_experimental_maturity_in_stack_toml(tmp_path: Path) -> None:
    import tomllib

    path = new_repo(tmp_path)
    data = tomllib.loads((path / "stack.toml").read_text())
    assert data["stack"]["maturity"] == "experimental"


def test_init_writes_a_gitignore(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    assert (path / ".gitignore").is_file()


def test_init_git_ignores_the_passes_file(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".bull/passes/stack.json"],
        cwd=path,
        capture_output=True,
        check=False,
    )
    assert ignored.returncode == 0


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


def test_init_succeeds_inside_another_stack_repo(tmp_path: Path) -> None:
    outer = new_repo(tmp_path, "outer")
    inner = outer / "inner"
    status = make_workflow().init(inner)
    assert status.name == "inner"
    assert Path(git(inner, "rev-parse", "--show-toplevel").strip()).resolve() == (
        inner.resolve()
    )


def test_init_refuses_a_missing_parent_folder_and_creates_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nope" / "my_stack"
    with pytest.raises(BullError):
        make_workflow().init(path)
    assert not (tmp_path / "nope").exists()


class _FailingCommitGit(LiveGit):
    """A real git whose commit always fails, to make `init` fail part way."""

    def commit_all(self, root: Path, message: str) -> str | None:
        raise BullError("commit failed")


def _failing_workflow() -> LiveStackWorkflow:
    return LiveStackWorkflow(
        LiveFiles(),
        LiveLayouts(),
        _FailingCommitGit(LiveRunner()),
        MockStackRegistry(),
    )


def test_init_failure_removes_the_folder_it_created(tmp_path: Path) -> None:
    path = tmp_path / "my_stack"
    with pytest.raises(BullError):
        _failing_workflow().init(path)
    assert not path.exists()


def test_init_failure_leaves_a_pre_existing_empty_folder_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "my_stack"
    path.mkdir()
    with pytest.raises(BullError):
        _failing_workflow().init(path)
    assert path.is_dir()
    assert list(path.iterdir()) == []


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


def _edit_status(path: Path, **changes: object) -> None:
    file = path / ".bull" / "status.json"
    data = json.loads(file.read_text())
    data.update(changes)
    file.write_text(json.dumps(data))


@pytest.mark.parametrize(
    "changes",
    [
        {"format": 2},
        {"format": "1"},
        {"stage": 0},
        {"stage": 7},
        {"stage": "one"},
        {"checkpoints": "design-approved"},
        {"checkpoints": [1, 2]},
        {"checkpoints": ["nonsense"]},
    ],
)
def test_load_raises_a_file_format_error_for_bad_status_values(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    path = new_repo(tmp_path)
    _edit_status(path, **changes)
    with pytest.raises(FileFormatError):
        make_workflow().load(path)


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


def test_set_stage_five_needs_a_full_pass_but_not_one_at_head(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 4)
    commit(path)
    make_workflow().record_test(path, report(static=False))
    (path / "more.txt").write_text("later work")
    commit(path)
    assert make_workflow().set_stage(path, 5).stage is StackStage.REVIEW


def test_set_stage_refuses_to_skip_a_stage(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    workflow = make_workflow()
    workflow.checkpoint(path, "design-approved")
    with pytest.raises(BullError):
        workflow.set_stage(path, 3)
    assert workflow.load(path).stage is StackStage.DISCUSS


@pytest.mark.parametrize("stage", [0, 7, -1])
def test_set_stage_refuses_a_stage_outside_one_to_six(
    tmp_path: Path, stage: int
) -> None:
    path = new_repo(tmp_path)
    with pytest.raises(BullError):
        make_workflow().set_stage(path, stage)
    assert make_workflow().load(path).stage is StackStage.DISCUSS


def test_set_stage_allows_going_back_a_stage(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 3)
    assert make_workflow().set_stage(path, 2).stage is StackStage.SCAFFOLD
    assert make_workflow().load(path).stage is StackStage.SCAFFOLD


def test_set_stage_six_is_refused_without_accepted(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    _ready_to_accept(path)
    with pytest.raises(BullError) as error:
        make_workflow().set_stage(path, 6)
    assert "accepted" in fails(error)
    assert make_workflow().load(path).stage is StackStage.REVIEW


def test_set_stage_six_moves_on_once_accepted(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    _ready_to_accept(path)
    make_workflow().checkpoint(path, "accepted")
    assert make_workflow().set_stage(path, 6).stage is StackStage.ACCEPTED
    assert make_workflow().load(path).stage is StackStage.ACCEPTED


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


def test_checkpoint_repeated_is_a_no_op(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    make_workflow().checkpoint(path, "design-approved")
    status = make_workflow().checkpoint(path, "design-approved")
    assert status.checkpoints == ("design-approved",)
    assert make_workflow().load(path).checkpoints == ("design-approved",)


def test_checkpoint_repeated_rules_approved_is_a_no_op_even_after_going_back(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 5)
    make_workflow().checkpoint(path, "rules-approved")
    make_workflow().set_stage(path, 4)
    status = make_workflow().checkpoint(path, "rules-approved")
    assert status.checkpoints.count("rules-approved") == 1


def test_checkpoint_repeated_accepted_is_a_no_op_after_head_moved(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    _ready_to_accept(path)
    make_workflow().checkpoint(path, "accepted")
    commit(path)
    status = make_workflow().checkpoint(path, "accepted")
    assert status.checkpoints.count("accepted") == 1


def test_checkpoint_repeated_accepted_is_a_no_op_on_a_dirty_tree(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    _ready_to_accept(path)
    make_workflow().checkpoint(path, "accepted")
    (path / "scratch.txt").write_text("uncommitted")
    status = make_workflow().checkpoint(path, "accepted")
    assert status.checkpoints.count("accepted") == 1


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


def _passes(path: Path) -> Path:
    return path / ".bull" / "passes" / "stack.json"


def _write_passes(path: Path, text: str) -> None:
    _passes(path).parent.mkdir(parents=True, exist_ok=True)
    _passes(path).write_text(text)


def test_record_test_leaves_git_status_clean(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    make_workflow().record_test(path, report(static=True))
    make_workflow().record_test(path, report(static=False))
    assert git(path, "status", "--porcelain").strip() == ""


def test_record_test_keeps_passes_out_of_the_status_file(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    make_workflow().record_test(path, report(static=True))
    make_workflow().record_test(path, report(static=False))
    data = json.loads((path / ".bull" / "status.json").read_text())
    assert set(data) == {"format", "kind", "name", "stage", "checkpoints"}
    assert head(path) in _passes(path).read_text()


def test_load_without_a_passes_file_means_no_pass(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    make_workflow().record_test(path, report(static=False))
    _passes(path).unlink(missing_ok=True)
    status = make_workflow().load(path)
    assert status.static_pass is None
    assert status.test_pass is None


@pytest.mark.parametrize(
    "text", ["not json at all", "[1, 2]", '"x"', '{"test_pass": 5}']
)
def test_load_with_a_malformed_passes_file_means_no_pass(
    tmp_path: Path, text: str
) -> None:
    path = new_repo(tmp_path)
    make_workflow().record_test(path, report(static=False))
    _write_passes(path, text)
    status = make_workflow().load(path)
    assert status.static_pass is None
    assert status.test_pass is None


def test_a_malformed_passes_file_blocks_the_stage_that_needs_a_pass(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    at_stage(path, 3)
    commit(path)
    make_workflow().record_test(path, report(static=True))
    _write_passes(path, "garbage")
    with pytest.raises(BullError):
        make_workflow().set_stage(path, 4)


def test_record_test_recovers_from_a_malformed_passes_file(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    _write_passes(path, "garbage")
    status = make_workflow().record_test(path, report(static=False))
    assert status.test_pass == head(path)


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


def test_ref_refuses_an_unknown_kind() -> None:
    with pytest.raises(BullError):
        make_workflow().ref("bogus", "accepted")


@pytest.mark.parametrize("name", ["bogus", "scaffold", ""])
def test_ref_refuses_an_unknown_checkpoint_for_a_tag(name: str) -> None:
    with pytest.raises(BullError):
        make_workflow().ref("tag", name)


@pytest.mark.parametrize("name", ["bogus", "design-approved", ""])
def test_ref_refuses_an_unknown_stage_name_for_a_branch(name: str) -> None:
    with pytest.raises(BullError):
        make_workflow().ref("branch", name)


# --- coverage triage: malformed status files, no-ops, broken templates


def _status_path(path: Path) -> Path:
    return path / ".bull" / "status.json"


def test_load_refuses_a_status_file_that_is_not_a_json_object(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    _status_path(path).write_text("[]")
    with pytest.raises(FileFormatError):
        make_workflow().load(path)


@pytest.mark.parametrize(
    "text", ['{"format": 1, "kind": "app"}', '{"format": 1, "name": "x"}']
)
def test_load_of_a_json_object_that_is_not_a_stack_status_is_a_plain_bull_error(
    tmp_path: Path, text: str
) -> None:
    path = new_repo(tmp_path)
    _status_path(path).write_text(text)
    with pytest.raises(BullError) as error:
        make_workflow().load(path)
    assert not isinstance(error.value, FileFormatError)
    assert "not a stack repo" in fails(error)  # type: ignore[arg-type]


def test_load_refuses_a_status_file_whose_name_is_not_a_string(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    data = json.loads(_status_path(path).read_text())
    data["name"] = 5
    _status_path(path).write_text(json.dumps(data))
    with pytest.raises(FileFormatError) as error:
        make_workflow().load(path)
    assert "name" in fails(error)  # type: ignore[arg-type]


def test_init_refuses_a_path_that_is_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "my_stack"
    target.write_text("keep me")
    with pytest.raises(BullError):
        make_workflow().init(target)
    assert target.is_file()
    assert target.read_text() == "keep me"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["my_stack"]


def test_set_stage_to_the_current_stage_writes_nothing(tmp_path: Path) -> None:
    path = new_repo(tmp_path)
    status_file = _status_path(path)
    before = status_file.stat()
    content = status_file.read_text()
    status = make_workflow().set_stage(path, 1)
    after = status_file.stat()
    assert status.stage is StackStage.DISCUSS
    assert status_file.read_text() == content
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_record_test_in_a_repo_with_no_commits_records_nothing(
    tmp_path: Path,
) -> None:
    path = new_repo(tmp_path)
    shutil.rmtree(path / ".git")
    git(path, "init", "-q")
    (path / ".git" / "info" / "exclude").write_text("*\n")
    workflow = make_workflow()
    before = workflow.load(path)
    after = workflow.record_test(path, report())
    assert after == before
    assert after.test_pass is None
    assert workflow.load(path).test_pass is None


def _broken_templates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    template = tmp_path / "templates" / "template"
    shutil.copytree(wf._TEMPLATE_DIR, template)
    monkeypatch.setattr(wf, "_TEMPLATE_DIR", template)
    return template


def test_init_with_a_missing_design_template_says_to_reinstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (_broken_templates(tmp_path, monkeypatch) / "DESIGN.md").unlink()
    target = tmp_path / "my_stack"
    with pytest.raises(BullError) as error:
        make_workflow().init(target)
    assert "reinstall" in fails(error)
    assert not target.exists()


def test_init_with_a_stack_toml_template_without_a_name_line_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (_broken_templates(tmp_path, monkeypatch) / "stack.toml").write_text(
        "[stack]\nversion = 1\n"
    )
    target = tmp_path / "my_stack"
    with pytest.raises(BullError) as error:
        make_workflow().init(target)
    assert "name" in fails(error)
    assert not target.exists()


def test_init_with_a_design_template_without_a_title_line_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (_broken_templates(tmp_path, monkeypatch) / "DESIGN.md").write_text(
        "no heading here\n"
    )
    target = tmp_path / "my_stack"
    with pytest.raises(BullError) as error:
        make_workflow().init(target)
    assert "title" in fails(error)
    assert not target.exists()
