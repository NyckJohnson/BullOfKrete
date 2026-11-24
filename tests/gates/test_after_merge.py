"""Tests for `bull.Modules.gates.after_merge` and LiveGates' AFTER_MERGE mode."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bull.Modules.coverage.Contracts import CoverageReport
from bull.Modules.foundation.Contracts import BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.gates import after_merge as after_merge_module
from bull.Modules.gates.Contracts import (
    GateMode,
    GateRequest,
    GateRun,
    PassRecord,
    Verdict,
)
from bull.Modules.gitrepo.mocks import MockGit

from .rig import BRANCH_SHA, HEAD_SHA, FakePasses, Rig, make_rig, shape

ROOT = Path("/tmp/apps/tally")
APP = sample_layout(ROOT)
BOOKKEEPING = (".bull/", "docs/")
RECORD = PassRecord(
    sha=BRANCH_SHA,
    branch="module/Counter",
    command="gates Counter",
    time=datetime(2026, 11, 10, tzinfo=UTC),
    parts=("app",),
)


def setup(changed: list[str]) -> tuple[MockGit, FakePasses]:
    git = MockGit()
    git.heads = {"HEAD": HEAD_SHA, "module/Counter": BRANCH_SHA}
    git.changed = changed
    passes = FakePasses()
    passes.records[BRANCH_SHA] = RECORD
    return git, passes


# --- after_merge_skip ---------------------------------------------------


def test_skip_returns_the_branch_heads_record_when_only_bookkeeping_changed() -> None:
    git, passes = setup(["docs/api/Counter.md", ".bull/status.json"])
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
        == RECORD
    )


def test_skip_compares_the_branch_head_with_head() -> None:
    git, passes = setup([])
    after_merge_module.after_merge_skip(APP, "module/Counter", git, passes, BOOKKEEPING)
    assert ("head", (ROOT, "module/Counter")) in git.calls
    assert ("changed_paths", (ROOT, BRANCH_SHA, "HEAD")) in git.calls


def test_skip_with_no_changed_paths_returns_the_record() -> None:
    git, passes = setup([])
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
        == RECORD
    )


def test_skip_is_none_when_the_branch_head_has_no_record() -> None:
    git, passes = setup(["docs/x.md"])
    passes.records.clear()
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
        is None
    )


def test_skip_is_none_when_any_changed_path_is_code() -> None:
    git, passes = setup(["docs/x.md", "src/other.py"])
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
        is None
    )


def test_skip_for_a_missing_branch_is_refused() -> None:
    git, passes = setup([])
    with pytest.raises(BullError) as exc:
        after_merge_module.after_merge_skip(APP, "no/such", git, passes, BOOKKEEPING)
    assert exc.value.message == "no branch no/such"


def test_skip_refuses_a_name_that_is_both_a_branch_and_a_tag() -> None:
    git, passes = setup([])
    git.branches.add("module/Counter")
    git.tag_names.append("module/Counter")
    with pytest.raises(BullError) as exc:
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
    assert exc.value.message == "module/Counter names both a branch and a tag"
    assert exc.value.fix == "use `refs/heads/module/Counter`"


def test_skip_refusal_for_a_shared_name_reads_nothing_more() -> None:
    git, passes = setup([])
    git.branches.add("module/Counter")
    git.tag_names.append("module/Counter")
    with pytest.raises(BullError):
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
    assert not [c for c in git.calls if c[0] == "changed_paths"]
    assert passes.recorded == []


def test_skip_accepts_a_branch_whose_name_is_only_a_tag_prefix() -> None:
    git, passes = setup([])
    git.branches.add("module/Counter")
    git.tag_names.append("module/Counter-v2")
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
        == RECORD
    )


def test_skip_accepts_a_branch_with_no_tag_of_that_name() -> None:
    git, passes = setup([])
    git.branches.add("module/Counter")
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, BOOKKEEPING
        )
        == RECORD
    )


def test_skip_accepts_refs_heads_even_when_the_name_is_also_a_tag() -> None:
    git, passes = setup([])
    git.heads["refs/heads/module/Counter"] = BRANCH_SHA
    git.branches.add("module/Counter")
    git.tag_names.append("module/Counter")
    assert (
        after_merge_module.after_merge_skip(
            APP, "refs/heads/module/Counter", git, passes, BOOKKEEPING
        )
        == RECORD
    )
    assert ("head", (ROOT, "refs/heads/module/Counter")) in git.calls


@pytest.mark.parametrize(
    ("entry", "path", "matches"),
    [
        ("docs/", "docs/a.md", True),
        ("docs/", "docs/deep/a.md", True),
        ("docs/", "docs2/a.md", False),
        ("docs/", "src/docs/a.md", False),
        ("NOTES.md", "NOTES.md", True),
        ("NOTES.md", "NOTES.md.bak", False),
        ("NOTES.md", "sub/NOTES.md", False),
        ("docs", "docs", True),
        ("docs", "docs/a.md", True),
        ("docs", "docs2/a.md", False),
        ("docs", "docsy", False),
    ],
)
def test_bookkeeping_entries_match_exact_paths_or_folders(
    entry: str, path: str, matches: bool
) -> None:
    git, passes = setup([path])
    result = after_merge_module.after_merge_skip(
        APP, "module/Counter", git, passes, [entry]
    )
    assert (result == RECORD) is matches


def test_every_changed_path_must_match_some_entry() -> None:
    git, passes = setup(["docs/a.md", "NOTES.md", "src/x.py"])
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git, passes, ["docs/", "NOTES.md"]
        )
        is None
    )
    git2, passes2 = setup(["docs/a.md", "NOTES.md"])
    assert (
        after_merge_module.after_merge_skip(
            APP, "module/Counter", git2, passes2, ["docs/", "NOTES.md"]
        )
        == RECORD
    )


def test_no_bookkeeping_entries_means_any_change_is_code() -> None:
    git, passes = setup(["docs/a.md"])
    assert (
        after_merge_module.after_merge_skip(APP, "module/Counter", git, passes, [])
        is None
    )


# --- LiveGates AFTER_MERGE ----------------------------------------------


def merged_rig(tmp_path: Path, changed: list[str], *, record: bool = True) -> Rig:
    rig = make_rig(tmp_path)
    rig.git.heads["feature/x"] = BRANCH_SHA
    rig.git.changed = changed
    rig.git.branch = "main"
    if record:
        rig.passes.records[BRANCH_SHA] = RECORD
    rig.triage.result = CoverageReport("Counter", {}, (), (), ())
    return rig


def after_merge(rig: Rig) -> GateRun:
    return rig.run(GateMode.AFTER_MERGE, branch="feature/x")


def test_after_merge_with_a_gated_branch_skips_the_run(tmp_path: Path) -> None:
    rig = merged_rig(tmp_path, ["docs/api/Counter.md"])
    run = after_merge(rig)
    assert run.verdict is Verdict.PASS
    assert run.steps == ()
    assert run.tests_run == 0
    assert run.recorded is True
    assert run.note == "merge holds the gated code"
    assert run.request == GateRequest(GateMode.AFTER_MERGE, branch="feature/x")
    assert rig.runner.calls == []
    assert rig.journeys.calls == []


def test_after_merge_skip_records_a_pass_for_head(tmp_path: Path) -> None:
    rig = merged_rig(tmp_path, ["docs/api/Counter.md"])
    after_merge(rig)
    assert len(rig.passes.recorded) == 1
    sha, _branch, command, parts = rig.passes.recorded[0]
    assert sha == HEAD_SHA
    assert command == "gates --after-merge feature/x"
    assert parts == RECORD.parts


def test_after_merge_skip_reads_bookkeeping_paths_from_settings(
    tmp_path: Path,
) -> None:
    rig = merged_rig(tmp_path, ["CHANGELOG.md"])
    rig.settings.values["bookkeeping_paths"] = ("CHANGELOG.md",)
    run = after_merge(rig)
    assert run.steps == ()
    assert run.note == "merge holds the gated code"


def test_after_merge_without_a_record_runs_everything(tmp_path: Path) -> None:
    rig = merged_rig(tmp_path, ["docs/x.md"], record=False)
    run = after_merge(rig)
    assert shape(run)[:4] == ["preflight:app", "setup:app", "build:app", "tests:app"]
    assert "lint:app:Counter" in shape(run)
    assert rig.runner.steps()[0] == "preflight"
    assert run.request == GateRequest(GateMode.AFTER_MERGE, branch="feature/x")


def test_after_merge_with_changed_code_runs_everything(tmp_path: Path) -> None:
    rig = merged_rig(tmp_path, ["docs/x.md", "src/bull/other.py"])
    run = after_merge(rig)
    assert run.steps != ()
    assert run.note != "merge holds the gated code"
    assert rig.runner.steps()[0] == "preflight"


def test_after_merge_full_run_records_with_the_after_merge_command(
    tmp_path: Path,
) -> None:
    rig = merged_rig(tmp_path, ["src/bull/other.py"], record=False)
    run = after_merge(rig)
    assert run.verdict is Verdict.PASS
    assert run.recorded is True
    assert rig.passes.recorded == [
        (HEAD_SHA, "main", "gates --after-merge feature/x", ("app",))
    ]


def test_after_merge_full_run_is_not_recorded_when_it_fails(tmp_path: Path) -> None:
    rig = merged_rig(tmp_path, ["src/bull/other.py"], record=False)
    rig.runner.set("lint", code=1)
    run = after_merge(rig)
    assert run.verdict is Verdict.FAIL
    assert run.recorded is False
    assert rig.passes.recorded == []


def test_after_merge_with_a_missing_branch_is_refused(tmp_path: Path) -> None:
    rig = merged_rig(tmp_path, [])
    with pytest.raises(BullError):
        rig.run(GateMode.AFTER_MERGE, branch="no/such")
    assert rig.runner.calls == []


def test_after_merge_refuses_a_name_that_is_both_a_branch_and_a_tag(
    tmp_path: Path,
) -> None:
    rig = merged_rig(tmp_path, [])
    rig.git.branches.add("feature/x")
    rig.git.tag_names.append("feature/x")
    with pytest.raises(BullError) as exc:
        after_merge(rig)
    assert exc.value.message == "feature/x names both a branch and a tag"
    assert exc.value.fix == "use `refs/heads/feature/x`"
    assert rig.runner.calls == []
    assert rig.passes.recorded == []


def test_after_merge_accepts_refs_heads_for_a_shared_name(tmp_path: Path) -> None:
    rig = merged_rig(tmp_path, ["docs/api/Counter.md"])
    rig.git.heads["refs/heads/feature/x"] = BRANCH_SHA
    rig.git.branches.add("feature/x")
    rig.git.tag_names.append("feature/x")
    run = rig.run(GateMode.AFTER_MERGE, branch="refs/heads/feature/x")
    assert run.verdict is Verdict.PASS
    assert run.note == "merge holds the gated code"
    assert rig.runner.calls == []
