"""Tests for `bull.Modules.features.cycle`: start, plan, accept and abandon.

Assumed constructor (the stub has none), following status's Live classes:
`LiveFeatureCycle(app, files, git, memo, store, refs)` with `app: AppLayout`, `files: Files`
(reads and writes `.bull/backlog.json` and reads the memo file), `git: Git`,
`memo: MemoReader`, `store: StatusStore`, `refs: Refs` (the trunk name). Refusals are `BullError`s.
The cycle writes the backlog file itself (the `Backlog` protocol cannot change an item's state).
"""

from __future__ import annotations

import json
from dataclasses import replace
from dataclasses import replace as dataclass_replace
from typing import Any

import pytest

from bull.Modules.features.Contracts import FeaturePlan, ItemState
from bull.Modules.features.cycle import LiveFeatureCycle
from bull.Modules.foundation.Contracts import BullError, FileFormatError
from bull.Modules.foundation.mocks import MockFiles, sample_layout
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.memo.Contracts import Memo, ModuleEntry
from bull.Modules.memo.mocks import MockMemoReader, sample_memo
from bull.Modules.status.Contracts import (
    ActiveFeature,
    ModuleState,
    ModuleStatus,
    Status,
    Track,
    Unit,
    UnitKind,
    UnitState,
)
from bull.Modules.status.mocks import MockRefs, MockStatusStore, sample_status

LAYOUT = sample_layout()
ROOT = LAYOUT.root
BACKLOG_PATH = ".bull/backlog.json"
TIME = "2026-11-07T12:00:00Z"


def _raw(slug: str, state: str = "queued") -> dict[str, str]:
    return {
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": f"About {slug}.",
        "state": state,
        "added": TIME,
        "brief": f"docs/features/{slug}.md",
    }


def _accepted_app() -> Status:
    base = sample_status()
    checkpoints = (*base.app.checkpoints, "app-accepted")
    return replace(base, app=Track(6, checkpoints))


def _with_feature(status: Status, slug: str, stage: int, *checkpoints: str) -> Status:
    return replace(status, feature=ActiveFeature(slug, Track(stage, checkpoints), ()))


class Rig:
    def __init__(
        self,
        items: list[dict[str, str]] | None = None,
        status: Status | None = None,
    ) -> None:
        self.files = MockFiles()
        self.git = MockGit()
        self.memo = MockMemoReader()
        self.store = MockStatusStore(status if status is not None else _accepted_app())
        self.refs = MockRefs()
        self.set_backlog(
            items if items is not None else [_raw("reset-button"), _raw("dark-mode")]
        )
        self.files.texts[LAYOUT.memo_file] = "# memo\n"
        self.cycle = LiveFeatureCycle(
            LAYOUT, self.files, self.git, self.memo, self.store, self.refs
        )

    def set_backlog(self, items: list[dict[str, str]]) -> None:
        self.files.texts[LAYOUT.backlog_file] = (
            json.dumps({"format": 1, "items": items}, indent=2) + "\n"
        )

    def backlog(self) -> list[dict[str, Any]]:
        data = json.loads(self.files.texts[LAYOUT.backlog_file])
        items: list[dict[str, Any]] = data["items"]
        return items

    def states(self) -> dict[str, str]:
        return {i["slug"]: i["state"] for i in self.backlog()}

    def store_calls(self, name: str) -> list[tuple[object, ...]]:
        return [args for call, args in self.store.calls if call == name]

    def git_calls(self, name: str) -> list[tuple[object, ...]]:
        return [args for call, args in self.git.calls if call == name]

    def on_feature_branch(self, slug: str = "reset-button") -> None:
        branch = f"feature/{slug}/main"
        self.git.branches.add(branch)
        self.git.branch = branch


# --- start -------------------------------------------------------------------------------


def test_start_without_slug_takes_the_first_queued_item() -> None:
    rig = Rig()
    item = rig.cycle.start()
    assert item.slug == "reset-button"
    assert item.state is ItemState.ACTIVE
    assert rig.states() == {"reset-button": "active", "dark-mode": "queued"}


def test_start_with_slug_takes_that_queued_item() -> None:
    rig = Rig()
    item = rig.cycle.start("dark-mode")
    assert item.slug == "dark-mode"
    assert rig.states() == {"reset-button": "queued", "dark-mode": "active"}


def test_start_without_slug_skips_items_that_are_not_queued() -> None:
    rig = Rig([_raw("old", "dropped"), _raw("done", "accepted"), _raw("next")])
    assert rig.cycle.start().slug == "next"


def test_start_calls_status_start_feature_with_the_slug() -> None:
    rig = Rig()
    rig.cycle.start()
    assert rig.store_calls("start_feature") == [("reset-button",)]
    assert rig.store.status.feature is not None
    assert rig.store.status.feature.slug == "reset-button"


def test_start_commits_with_the_start_message() -> None:
    rig = Rig()
    rig.cycle.start()
    assert (ROOT, "chore: start feature reset-button") in rig.git_calls("commit_all")


def test_start_creates_and_switches_to_the_feature_branch_from_the_trunk() -> None:
    rig = Rig()
    rig.cycle.start()
    assert rig.git.branch == "feature/reset-button/main"
    assert "feature/reset-button/main" in rig.git.branches
    created = rig.git_calls("create_branch")
    assert len(created) == 1
    assert created[0][1] == "feature/reset-button/main"
    assert created[0][2] == "main"


def test_start_commits_before_branching_so_the_branch_holds_the_active_item() -> None:
    rig = Rig()
    rig.cycle.start()
    order = [
        name for name, _ in rig.git.calls if name in ("commit_all", "create_branch")
    ]
    assert order == ["commit_all", "create_branch"]


def _refused_cases() -> list[tuple[str, Any]]:
    def dirty(rig: Rig) -> None:
        rig.git.clean = False

    def off_trunk(rig: Rig) -> None:
        rig.git.branch = "module/Counter"

    def not_accepted(rig: Rig) -> None:
        rig.store.status = sample_status()

    def adopting(rig: Rig) -> None:
        rig.store.status = replace(rig.store.status, adoption=Track(2, ("setup",)))

    def feature_active(rig: Rig) -> None:
        rig.store.status = _with_feature(rig.store.status, "other", 3)

    def branch_exists(rig: Rig) -> None:
        rig.git.branches.add("feature/reset-button/main")

    return [
        ("branch-exists", branch_exists),
        ("dirty", dirty),
        ("off-trunk", off_trunk),
        ("not-accepted", not_accepted),
        ("adoption", adopting),
        ("feature-active", feature_active),
    ]


@pytest.mark.parametrize(
    "setup", [c[1] for c in _refused_cases()], ids=[c[0] for c in _refused_cases()]
)
def test_start_is_refused_and_changes_nothing_when_a_precondition_fails(
    setup: Any,
) -> None:
    rig = Rig()
    setup(rig)
    before = rig.files.texts[LAYOUT.backlog_file]
    with pytest.raises(BullError):
        rig.cycle.start()
    assert rig.store_calls("start_feature") == []
    assert rig.git_calls("commit_all") == []
    assert rig.git_calls("create_branch") == []
    assert rig.files.texts[LAYOUT.backlog_file] == before


def test_start_during_an_adoption_is_refused_with_a_message_about_after_it_finishes() -> (
    None
):
    rig = Rig()
    rig.store.status = replace(rig.store.status, adoption=Track(2, ("setup",)))
    with pytest.raises(BullError, match="after the adoption finishes"):
        rig.cycle.start()


def test_start_during_an_adoption_without_app_accepted_names_the_adoption_not_acceptance() -> (
    None
):
    rig = Rig(status=replace(sample_status(), adoption=Track(2, ("setup",))))
    assert "app-accepted" not in rig.store.status.app.checkpoints
    before = rig.files.texts[LAYOUT.backlog_file]
    with pytest.raises(BullError) as raised:
        rig.cycle.start()
    message = str(raised.value).lower()
    assert "adoption" in message
    assert "after the adoption finishes" in message
    assert "accepted" not in message
    assert rig.store_calls("start_feature") == []
    assert rig.git_calls("commit_all") == []
    assert rig.git_calls("create_branch") == []
    assert rig.files.texts[LAYOUT.backlog_file] == before


def test_start_with_slug_is_refused_when_that_feature_branch_exists() -> None:
    rig = Rig()
    rig.git.branches.add("feature/dark-mode/main")
    with pytest.raises(BullError):
        rig.cycle.start("dark-mode")
    assert rig.states() == {"reset-button": "queued", "dark-mode": "queued"}
    assert rig.store_calls("start_feature") == []
    assert rig.git_calls("commit_all") == []
    assert rig.git_calls("create_branch") == []


def test_start_is_refused_when_nothing_is_queued() -> None:
    rig = Rig([_raw("old", "dropped")])
    with pytest.raises(BullError):
        rig.cycle.start()
    assert rig.store_calls("start_feature") == []


def test_start_is_refused_for_an_unknown_slug() -> None:
    rig = Rig()
    with pytest.raises(BullError):
        rig.cycle.start("no-such-feature")
    assert rig.store_calls("start_feature") == []


def test_start_is_refused_for_a_slug_that_is_not_queued() -> None:
    rig = Rig([_raw("old", "dropped"), _raw("next")])
    with pytest.raises(BullError):
        rig.cycle.start("old")
    assert rig.states() == {"old": "dropped", "next": "queued"}


# --- plan --------------------------------------------------------------------------------


class ReplacingStore(MockStatusStore):
    """`init_modules(replace=True)` as the spec describes: unchanged units keep their progress,
    changed or new units start pending, modules not yet in status are appended."""

    def __init__(self, status: Status) -> None:
        super().__init__(status)
        self.refuse = False

    def init_modules(self, memo: Memo, replace: bool = False) -> Status:
        self.calls.append(("init_modules", (memo, replace)))
        if self.refuse:
            raise BullError("The memo has problems.", "Fix them first.")
        modules = list(self.status.modules)
        for entry in memo.modules:
            known = next((m for m in modules if m.name == entry.name), None)
            old = known.units if known is not None else ()
            units = tuple(
                old[n - 1]
                if n <= len(old) and old[n - 1].files == files
                else Unit(n, files, UnitKind.CODE, UnitState.PENDING, 1)
                for n, files in enumerate(entry.units, start=1)
            )
            if known is None:
                modules.append(
                    ModuleStatus(
                        entry.name,
                        entry.part or "app",
                        entry.depends,
                        ModuleState.PENDING,
                        units,
                        False,
                        None,
                    )
                )
            else:
                modules[modules.index(known)] = dataclass_replace(known, units=units)
        self.status = dataclass_replace(self.status, modules=tuple(modules))
        return self.status


def _entry(name: str, **fields: Any) -> ModuleEntry:
    base = sample_memo().modules[1]
    return replace(base, name=name, **fields)


def _planning_rig(*entries: ModuleEntry) -> Rig:
    rig = Rig(
        [_raw("reset-button", "active"), _raw("dark-mode")],
        _with_feature(_accepted_app(), "reset-button", 2),
    )
    rig.store = ReplacingStore(rig.store.status)
    rig.cycle = LiveFeatureCycle(
        LAYOUT, rig.files, rig.git, rig.memo, rig.store, rig.refs
    )
    rig.on_feature_branch()
    base = sample_memo()
    rig.memo.memo = replace(base, modules=(base.modules[0], *entries))
    return rig


def test_plan_reopens_a_module_with_changes_for_the_slug() -> None:
    counter = _entry(
        "Counter", changes={"reset-button": ("counter.fx",)}, units=(("counter.fx",),)
    )
    rig = _planning_rig(counter)
    plan = rig.cycle.plan()
    assert rig.store_calls("reopen") == [("Counter", ("counter.fx",))]
    assert plan.reopened == {"Counter": (1,)}


def test_plan_reports_the_reopened_unit_numbers_of_the_changed_files() -> None:
    # In the status, Counter's unit 1 holds counter.fx and unit 2 holds cli.fx.
    counter = _entry("Counter", changes={"reset-button": ("cli.fx",)})
    rig = _planning_rig(counter)
    plan = rig.cycle.plan()
    assert rig.store_calls("reopen") == [("Counter", ("cli.fx",))]
    assert plan.reopened == {"Counter": (2,)}


def test_plan_ignores_changes_marked_for_another_slug() -> None:
    counter = _entry("Counter", changes={"dark-mode": ("counter.fx",)})
    rig = _planning_rig(counter)
    plan = rig.cycle.plan()
    assert rig.store_calls("reopen") == []
    assert plan.reopened == {}
    assert plan.skeleton_needed is False


def test_plan_runs_init_modules_with_replace_on_the_parsed_memo() -> None:
    rig = _planning_rig(_entry("Counter"))
    rig.cycle.plan()
    assert rig.store_calls("init_modules") == [(rig.memo.memo, True)]


def test_plan_does_not_use_add_modules_directly() -> None:
    rig = _planning_rig(_entry("Export", depends=("Store",), units=(("export.fx",),)))
    rig.cycle.plan()
    assert rig.store_calls("add_modules") == []


def test_plan_initialises_modules_before_reopening() -> None:
    counter = _entry("Counter", changes={"reset-button": ("counter.fx",)})
    rig = _planning_rig(counter)
    rig.cycle.plan()
    order = [n for n, _ in rig.store.calls if n in ("init_modules", "reopen")]
    assert order == ["init_modules", "reopen"]


def test_plan_adds_modules_not_yet_in_status() -> None:
    export = _entry("Export", depends=("Store",), units=(("export.fx",),))
    rig = _planning_rig(export)
    plan = rig.cycle.plan()
    assert plan.new_modules == ("Export",)
    assert "Export" in {m.name for m in rig.store.status.modules}


def test_plan_does_not_add_modules_already_in_status() -> None:
    counter = _entry("Counter", changes={"reset-button": ("counter.fx",)})
    rig = _planning_rig(counter)
    before = [m.name for m in rig.store.status.modules]
    plan = rig.cycle.plan()
    assert plan.new_modules == ()
    assert [m.name for m in rig.store.status.modules] == before


def test_plan_reopens_a_file_new_to_an_existing_module_placed_in_an_existing_group() -> (
    None
):
    # The memo puts new.fx in Counter's second group (unit 2), next to cli.fx.
    counter = _entry(
        "Counter",
        units=(("Contracts/counter.fx", "counter.fx"), ("cli.fx", "new.fx")),
        changes={"reset-button": ("new.fx",)},
    )
    rig = _planning_rig(counter)
    plan = rig.cycle.plan()
    assert rig.store_calls("reopen") == [("Counter", ("new.fx",))]
    assert plan.reopened == {"Counter": (2,)}
    units = {
        u.number: u
        for u in next(m for m in rig.store.status.modules if m.name == "Counter").units
    }
    assert units[1].state is UnitState.TESTS  # unchanged unit keeps its progress
    assert units[2].files == ("cli.fx", "new.fx")
    assert units[2].state is UnitState.PENDING
    assert plan.new_modules == ()


def test_plan_reopens_a_file_new_to_an_existing_module_placed_in_a_new_group() -> None:
    counter = _entry(
        "Counter",
        units=(
            ("Contracts/counter.fx", "counter.fx"),
            ("cli.fx",),
            ("new.fx",),
        ),
        changes={"reset-button": ("new.fx",)},
    )
    rig = _planning_rig(counter)
    plan = rig.cycle.plan()
    assert rig.store_calls("reopen") == [("Counter", ("new.fx",))]
    assert plan.reopened == {"Counter": (3,)}
    module = next(m for m in rig.store.status.modules if m.name == "Counter")
    assert [u.files for u in module.units][-1] == ("new.fx",)
    assert module.units[0].state is UnitState.TESTS


def test_plan_memo_problems_refused_by_init_modules_reopen_nothing() -> None:
    counter = _entry("Counter", changes={"reset-button": ("counter.fx",)})
    rig = _planning_rig(counter)
    assert isinstance(rig.store, ReplacingStore)
    rig.store.refuse = True
    before = rig.store.status
    with pytest.raises(BullError):
        rig.cycle.plan()
    assert rig.store_calls("reopen") == []
    assert rig.store.status == before


def test_plan_lists_modules_with_contract_changes_for_the_slug() -> None:
    counter = _entry(
        "Counter",
        changes={"reset-button": ("counter.fx",)},
        contract_changes={"reset-button": "add reset()"},
    )
    rig = _planning_rig(counter)
    plan = rig.cycle.plan()
    assert plan.contract_changes == ("Counter",)


def test_plan_skeleton_is_needed_when_a_contract_changes() -> None:
    counter = _entry(
        "Counter",
        changes={"reset-button": ("counter.fx",)},
        contract_changes={"reset-button": "add reset()"},
    )
    assert _planning_rig(counter).cycle.plan().skeleton_needed is True


def test_plan_skeleton_is_needed_when_a_module_is_new() -> None:
    export = _entry("Export", units=(("export.fx",),))
    assert _planning_rig(export).cycle.plan().skeleton_needed is True


def test_plan_skeleton_is_not_needed_for_changes_without_contract_or_new_modules() -> (
    None
):
    counter = _entry("Counter", changes={"reset-button": ("counter.fx",)})
    plan = _planning_rig(counter).cycle.plan()
    assert plan == FeaturePlan(
        reopened={"Counter": (1,)},
        new_modules=(),
        contract_changes=(),
        skeleton_needed=False,
    )


def test_plan_parses_the_memo_file_text() -> None:
    rig = _planning_rig(_entry("Counter"))
    rig.files.texts[LAYOUT.memo_file] = "# the memo text\n"
    rig.cycle.plan()
    assert ("parse", ("# the memo text\n",)) in rig.memo.calls


def test_plan_is_refused_off_the_feature_branch() -> None:
    rig = _planning_rig(_entry("Counter", changes={"reset-button": ("cli.fx",)}))
    rig.git.branch = "main"
    with pytest.raises(BullError):
        rig.cycle.plan()
    assert rig.store_calls("reopen") == []
    assert rig.store_calls("init_modules") == []


def test_plan_is_refused_when_no_feature_is_active() -> None:
    rig = _planning_rig(_entry("Counter"))
    rig.store.status = _accepted_app()
    with pytest.raises(BullError):
        rig.cycle.plan()


# --- accept ------------------------------------------------------------------------------


def _accepting_rig(stage: int = 6, *checkpoints: str) -> Rig:
    rig = Rig(
        [_raw("reset-button", "active"), _raw("dark-mode")],
        _with_feature(_accepted_app(), "reset-button", stage, *checkpoints),
    )
    rig.on_feature_branch()
    return rig


def test_accept_marks_the_item_accepted_and_ends_the_feature() -> None:
    rig = _accepting_rig(6, "outline-approved", "accepted")
    item = rig.cycle.accept()
    assert item.slug == "reset-button"
    assert item.state is ItemState.ACCEPTED
    assert rig.states() == {"reset-button": "accepted", "dark-mode": "queued"}
    assert rig.store_calls("end_feature") == [()]
    assert rig.store.status.feature is None


@pytest.mark.parametrize(
    ("stage", "checkpoints"),
    [
        (5, ("accepted",)),
        (6, ("outline-approved",)),
        (6, ()),
        (2, ()),
    ],
)
def test_accept_is_refused_unless_stage_6_with_accepted_recorded(
    stage: int, checkpoints: tuple[str, ...]
) -> None:
    rig = _accepting_rig(stage, *checkpoints)
    with pytest.raises(BullError):
        rig.cycle.accept()
    assert rig.states()["reset-button"] == "active"
    assert rig.store_calls("end_feature") == []


def test_accept_is_refused_when_no_feature_is_active() -> None:
    rig = _accepting_rig(6, "accepted")
    rig.store.status = _accepted_app()
    with pytest.raises(BullError):
        rig.cycle.accept()


def test_accept_changes_only_the_backlog_and_status() -> None:
    rig = _accepting_rig(6, "accepted")
    rig.cycle.accept()
    written = [args[0] for name, args in rig.files.calls if name.startswith("write")]
    assert set(written) <= {LAYOUT.backlog_file}
    assert rig.git_calls("commit_all") == []
    assert rig.git_calls("switch") == []
    assert rig.git_calls("tag") == []


# --- abandon -----------------------------------------------------------------------------


def _abandoning_rig(branch_items: list[dict[str, str]] | None = None) -> Rig:
    rig = Rig(
        [_raw("reset-button", "active"), _raw("dark-mode")],
        _with_feature(_accepted_app(), "reset-button", 3),
    )
    rig.git.branches.add("feature/reset-button/main")
    rig.git.branch = "main"
    if branch_items is not None:
        rig.git.files_at[("feature/reset-button/main", BACKLOG_PATH)] = json.dumps(
            {"format": 1, "items": branch_items}
        )
    return rig


def test_abandon_marks_the_item_abandoned_and_ends_the_feature() -> None:
    rig = _abandoning_rig()
    item = rig.cycle.abandon()
    assert item.slug == "reset-button"
    assert item.state is ItemState.ABANDONED
    assert rig.states() == {"reset-button": "abandoned", "dark-mode": "queued"}
    assert rig.store_calls("end_feature") == [()]


def test_abandon_adds_branch_items_missing_on_the_trunk_as_queued() -> None:
    branch = [
        _raw("reset-button", "active"),
        _raw("dark-mode"),
        _raw("export-csv"),
        _raw("sound", "queued"),
    ]
    rig = _abandoning_rig(branch)
    rig.cycle.abandon()
    assert rig.states() == {
        "reset-button": "abandoned",
        "dark-mode": "queued",
        "export-csv": "queued",
        "sound": "queued",
    }


def test_abandon_reads_the_branch_backlog_with_git_show() -> None:
    rig = _abandoning_rig([_raw("export-csv")])
    rig.cycle.abandon()
    assert (ROOT, "feature/reset-button/main", BACKLOG_PATH) in rig.git_calls(
        "show_file"
    )


def test_abandon_keeps_trunk_items_already_present_without_duplicating() -> None:
    rig = _abandoning_rig([_raw("reset-button", "active"), _raw("dark-mode")])
    rig.cycle.abandon()
    slugs = [i["slug"] for i in rig.backlog()]
    assert sorted(slugs) == ["dark-mode", "reset-button"]


def test_abandon_works_when_the_branch_has_no_backlog_file() -> None:
    rig = _abandoning_rig(None)
    rig.cycle.abandon()
    assert rig.states() == {"reset-button": "abandoned", "dark-mode": "queued"}


def test_abandon_leaves_the_branch_itself_alone() -> None:
    rig = _abandoning_rig([_raw("export-csv")])
    rig.cycle.abandon()
    assert "feature/reset-button/main" in rig.git.branches
    assert rig.git.branch == "main"


def test_abandon_is_refused_off_the_trunk() -> None:
    rig = _abandoning_rig([_raw("export-csv")])
    rig.on_feature_branch()
    with pytest.raises(BullError):
        rig.cycle.abandon()
    assert rig.states()["reset-button"] == "active"
    assert rig.store_calls("end_feature") == []


def test_abandon_is_refused_when_no_feature_is_active() -> None:
    rig = _abandoning_rig()
    rig.store.status = _accepted_app()
    with pytest.raises(BullError):
        rig.cycle.abandon()


# --- guards (coverage triage) -------------------------------------------------------------


def test_plan_without_a_memo_file_is_refused_and_changes_nothing() -> None:
    rig = _planning_rig(_entry("Counter", changes={"reset-button": ("cli.fx",)}))
    del rig.files.texts[LAYOUT.memo_file]
    with pytest.raises(BullError) as caught:
        rig.cycle.plan()
    assert (
        "write the memo first" in f"{caught.value.message} {caught.value.fix}".lower()
    )
    assert rig.store_calls("init_modules") == []
    assert rig.store_calls("reopen") == []


def test_accept_is_refused_when_the_active_slug_is_not_in_the_backlog() -> None:
    rig = _accepting_rig(6, "accepted")
    rig.set_backlog([_raw("dark-mode")])
    with pytest.raises(BullError):
        rig.cycle.accept()
    assert rig.store_calls("end_feature") == []


def test_abandon_is_refused_when_the_active_slug_is_not_in_the_backlog() -> None:
    rig = _abandoning_rig()
    rig.set_backlog([_raw("dark-mode")])
    with pytest.raises(BullError):
        rig.cycle.abandon()
    assert rig.store_calls("end_feature") == []


def test_abandon_with_invalid_json_on_the_feature_branch_names_branch_and_path() -> (
    None
):
    rig = _abandoning_rig()
    rig.git.files_at[("feature/reset-button/main", BACKLOG_PATH)] = "{not json"
    with pytest.raises(
        FileFormatError, match=f"feature/reset-button/main:{BACKLOG_PATH}"
    ):
        rig.cycle.abandon()
    assert rig.store_calls("end_feature") == []
