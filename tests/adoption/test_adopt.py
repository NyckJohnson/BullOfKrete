"""Tests for `bull.Modules.adoption.adopt`: `LiveAdoption` apply, start, finish and abandon.

`LiveAdoption(files, git, runner, stacks, ops, parts, memo, settings, store, refs)` is built with
keyword arguments; `settings`, `store` and `refs` are callables taking the app layout.
Refusals are `BullError`s raised before anything is changed.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.adoption.adopt import LiveAdoption
from bull.Modules.adoption.Contracts import DetectionReport
from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import MockFiles, MockRunner, sample_layout
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.memo.mocks import MockMemoReader
from bull.Modules.parts.mocks import MockParts, sample_part
from bull.Modules.settings.Contracts import Layer, Resolved, SettingValue
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.stacks.Contracts import Detection
from bull.Modules.stacks.mocks import MockStackOps, MockStackRegistry
from bull.Modules.status.Contracts import Status, Track
from bull.Modules.status.mocks import MockRefs, MockStatusStore

BACKLOG_ON_BRANCH = ("adopt/main", ".bull/backlog.json")
TIME = "2026-11-07T12:00:00Z"


class RecordingSettings(MockSettings):
    """Accepts any key and records each `set`."""

    def __init__(self) -> None:
        super().__init__()
        self.sets: list[tuple[str, str, Layer, str | None]] = []

    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved:
        self.calls.append(("set", (key, raw, layer, part)))
        self.sets.append((key, raw, layer, part))
        value: SettingValue = raw
        return Resolved(key, value, layer, None)


class OrderedOps(MockStackOps):
    """MockStackOps that logs `select` into a shared event list."""

    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def select(self, app: AppLayout, name: str) -> None:
        self.events.append(f"select {name}")
        super().select(app, name)


def _empty_status() -> Status:
    return Status(1, Track(0, ()), (), None, None, (), None, None, None)


def _raw(slug: str, state: str = "queued") -> dict[str, str]:
    return {
        "slug": slug,
        "title": slug.replace("-", " ").title(),
        "description": f"About {slug}.",
        "state": state,
        "added": TIME,
        "brief": f"docs/features/{slug}.md",
    }


def _backlog_text(items: list[dict[str, str]]) -> str:
    return json.dumps({"format": 1, "items": items})


class Rig:
    def __init__(self, tmp_path: Path, status: Status | None = None) -> None:
        self.layout = sample_layout(tmp_path)
        self.events: list[str] = []
        self.files = MockFiles()
        self.git = MockGit()
        self.runner = MockRunner()
        self.registry = MockStackRegistry()
        self.ops = OrderedOps(self.events)
        self.parts = MockParts()
        self.parts.parts = [sample_part(tmp_path)]
        self.memo = MockMemoReader()
        self.settings = RecordingSettings()
        self.store = MockStatusStore(status if status is not None else _empty_status())
        self.refs = MockRefs()
        self.adoption = LiveAdoption(
            files=self.files,
            git=self.git,
            runner=self.runner,
            stacks=self.registry,
            ops=self.ops,
            parts=self.parts,
            memo=self.memo,
            settings=self._settings,
            store=lambda app: self.store,
            refs=lambda app: self.refs,
        )
        (tmp_path / "src" / "fx").mkdir(parents=True)
        (tmp_path / "tests").mkdir()

    def _settings(self, app: AppLayout) -> MockSettings:
        self.events.append("settings")
        return self.settings

    def store_names(self) -> list[str]:
        return [name for name, _ in self.store.calls]

    def git_names(self) -> list[str]:
        return [name for name, _ in self.git.calls]

    def commits(self) -> list[object]:
        return [args[1] for name, args in self.git.calls if name == "commit_all"]


def _report(
    stack: str | None = "fixture",
    settings: dict[str, str] | None = None,
) -> DetectionReport:
    if stack is None:
        return DetectionReport(None, None, ())
    detection = Detection(
        0.9,
        "fixture app",
        settings
        if settings is not None
        else {"source_dir": "src/fx", "test_dir": "tests"},
        (),
    )
    return DetectionReport(stack, detection, ())


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


# --- apply ------------------------------------------------------------------------------------


def test_apply_selects_the_detected_stack(rig: Rig) -> None:
    rig.adoption.apply(rig.layout, _report("fixture"))
    assert rig.ops.calls == [("select", (rig.layout, "fixture"))]


def test_apply_writes_each_detected_setting_in_mapping_order(rig: Rig) -> None:
    report = _report("fixture", {"test_dir": "tests", "source_dir": "src/fx", "x": "1"})
    rig.adoption.apply(rig.layout, report)
    assert rig.settings.sets == [
        ("test_dir", "tests", Layer.APP, None),
        ("source_dir", "src/fx", Layer.APP, None),
        ("x", "1", Layer.APP, None),
    ]


def test_apply_reads_settings_only_after_selecting_the_stack(rig: Rig) -> None:
    rig.adoption.apply(rig.layout, _report("fixture"))
    assert rig.events.index("select fixture") < rig.events.index("settings")


def test_apply_with_a_chosen_stack_selects_that_stack(rig: Rig) -> None:
    rig.adoption.apply(rig.layout, _report("fixture"), "python_cli")
    assert rig.ops.calls == [("select", (rig.layout, "python_cli"))]


def test_apply_with_a_different_chosen_stack_skips_the_detected_settings(
    rig: Rig,
) -> None:
    rig.adoption.apply(rig.layout, _report("fixture"), "python_cli")
    assert rig.settings.sets == []


def test_apply_with_the_chosen_stack_equal_to_the_detected_one_writes_settings(
    rig: Rig,
) -> None:
    rig.adoption.apply(rig.layout, _report("fixture"), "fixture")
    assert [s[0] for s in rig.settings.sets] == ["source_dir", "test_dir"]


def test_apply_with_a_chosen_stack_and_no_detection_selects_only(rig: Rig) -> None:
    rig.adoption.apply(rig.layout, _report(None), "python_cli")
    assert rig.ops.calls == [("select", (rig.layout, "python_cli"))]
    assert rig.settings.sets == []


def test_apply_with_no_stack_at_all_is_an_error(rig: Rig) -> None:
    with pytest.raises(BullError):
        rig.adoption.apply(rig.layout, _report(None))
    assert rig.ops.calls == []
    assert rig.settings.sets == []


def test_apply_does_not_commit(rig: Rig) -> None:
    rig.adoption.apply(rig.layout, _report("fixture"))
    assert rig.git.commits == 0


# --- start ------------------------------------------------------------------------------------


def test_start_records_the_adoption(rig: Rig) -> None:
    rig.adoption.start(rig.layout)
    assert rig.store.status.adoption is not None
    assert "start_adoption" in rig.store_names()


def test_start_commits_then_creates_and_switches_to_adopt_main(rig: Rig) -> None:
    rig.adoption.start(rig.layout)
    root = rig.layout.root
    assert rig.git.calls[-2:] == [
        ("commit_all", (root, "chore: start adoption")),
        ("create_branch", (root, "adopt/main", "main", True)),
    ]
    assert rig.git.branch == "adopt/main"


def test_start_uses_the_configured_trunk(rig: Rig) -> None:
    rig.refs = MockRefs(trunk="develop")
    rig.git.branch = "develop"
    rig.git.branches = {"develop"}
    rig.adoption.start(rig.layout)
    assert ("create_branch", (rig.layout.root, "adopt/main", "develop", True)) in (
        rig.git.calls
    )


def _assert_nothing_started(rig: Rig) -> None:
    assert "start_adoption" not in rig.store_names()
    assert not {"commit_all", "create_branch"} & set(rig.git_names())


def test_start_refuses_when_not_on_the_trunk(rig: Rig) -> None:
    rig.git.branch = "feature/x/main"
    with pytest.raises(BullError):
        rig.adoption.start(rig.layout)
    _assert_nothing_started(rig)


def test_start_refuses_a_dirty_tree(rig: Rig) -> None:
    rig.git.clean = False
    with pytest.raises(BullError):
        rig.adoption.start(rig.layout)
    _assert_nothing_started(rig)


def test_start_refuses_an_app_the_pipeline_already_built(rig: Rig) -> None:
    from bull.Modules.status.mocks import sample_status

    rig.store = MockStatusStore(sample_status())
    with pytest.raises(BullError):
        rig.adoption.start(rig.layout)
    _assert_nothing_started(rig)


def test_start_off_the_trunk_names_the_problem_and_the_fix(rig: Rig) -> None:
    rig.git.branch = "feature/x/main"
    with pytest.raises(BullError) as raised:
        rig.adoption.start(rig.layout)
    assert raised.value.message == (
        "adopt start runs on the trunk main; you are on feature/x/main"
    )
    assert raised.value.fix == "git switch main"


def test_start_off_a_configured_trunk_names_that_trunk(rig: Rig) -> None:
    rig.refs = MockRefs(trunk="develop")
    rig.git.branch = "main"
    with pytest.raises(BullError) as raised:
        rig.adoption.start(rig.layout)
    assert (
        raised.value.message == "adopt start runs on the trunk develop; you are on main"
    )
    assert raised.value.fix == "git switch develop"


def test_start_with_a_dirty_tree_names_the_problem_and_the_fix(rig: Rig) -> None:
    rig.git.clean = False
    with pytest.raises(BullError) as raised:
        rig.adoption.start(rig.layout)
    assert raised.value.message == "adopt start needs a clean tree"
    assert raised.value.fix == "commit or stash your changes"


def test_start_with_modules_names_the_problem(rig: Rig) -> None:
    from bull.Modules.status.mocks import sample_status

    rig.store = MockStatusStore(sample_status())
    with pytest.raises(BullError) as raised:
        rig.adoption.start(rig.layout)
    assert raised.value.message == (
        "this app already has modules; adoption is for apps built outside bull"
    )


def test_start_checks_the_trunk_before_the_tree_and_the_modules(rig: Rig) -> None:
    from bull.Modules.status.mocks import sample_status

    rig.git.branch = "other"
    rig.git.clean = False
    rig.store = MockStatusStore(sample_status())
    with pytest.raises(BullError) as raised:
        rig.adoption.start(rig.layout)
    assert raised.value.message.startswith("adopt start runs on the trunk")


def test_start_checks_the_tree_before_the_modules(rig: Rig) -> None:
    from bull.Modules.status.mocks import sample_status

    rig.git.clean = False
    rig.store = MockStatusStore(sample_status())
    with pytest.raises(BullError) as raised:
        rig.adoption.start(rig.layout)
    assert raised.value.message == "adopt start needs a clean tree"


def test_start_accepts_a_status_with_no_modules(rig: Rig) -> None:
    rig.store = MockStatusStore(replace(_empty_status(), app=Track(2, ("setup",))))
    rig.adoption.start(rig.layout)
    assert rig.git.branch == "adopt/main"


# --- finish -----------------------------------------------------------------------------------


def _adopting(stage: int) -> Status:
    return replace(_empty_status(), adoption=Track(stage, ("outline-approved",)))


def test_finish_at_stage_six_with_nothing_left_finishes_and_commits(
    tmp_path: Path,
) -> None:
    rig = Rig(tmp_path, _adopting(6))
    rig.adoption.finish(rig.layout)
    assert "finish_adoption" in rig.store_names()
    assert rig.store.status.adoption is None
    assert rig.commits() == ["chore: adoption finished"]


@pytest.mark.parametrize("stage", [1, 2, 3, 4, 5])
def test_finish_before_stage_six_is_refused(tmp_path: Path, stage: int) -> None:
    rig = Rig(tmp_path, _adopting(stage))
    with pytest.raises(BullError) as excinfo:
        rig.adoption.finish(rig.layout)
    assert "finish needs stage 6 (verify)" in excinfo.value.message
    assert "finish_adoption" not in rig.store_names()
    assert rig.commits() == []


def test_finish_without_an_active_adoption_is_refused(tmp_path: Path) -> None:
    rig = Rig(tmp_path, _empty_status())
    with pytest.raises(BullError):
        rig.adoption.finish(rig.layout)
    assert "finish_adoption" not in rig.store_names()
    assert rig.commits() == []


def test_finish_with_legacy_files_left_lists_them(tmp_path: Path) -> None:
    rig = Rig(tmp_path, _adopting(6))
    (tmp_path / "src" / "fx" / "old.fx").write_text("x")
    with pytest.raises(BullError) as excinfo:
        rig.adoption.finish(rig.layout)
    assert "src/fx/old.fx" in excinfo.value.message
    assert "finish_adoption" not in rig.store_names()
    assert rig.commits() == []


def test_finish_with_legacy_tests_left_lists_them(tmp_path: Path) -> None:
    rig = Rig(tmp_path, _adopting(6))
    (tmp_path / "tests" / "old.test").write_text("x")
    with pytest.raises(BullError) as excinfo:
        rig.adoption.finish(rig.layout)
    assert "tests/old.test" in excinfo.value.message
    assert "finish_adoption" not in rig.store_names()


def test_finish_names_every_left_path_of_every_kind(tmp_path: Path) -> None:
    rig = Rig(tmp_path, _adopting(6))
    (tmp_path / "src" / "fx" / "a.fx").write_text("x")
    (tmp_path / "tests" / "b.test").write_text("x")
    (tmp_path / "src" / "fx" / "Modules").mkdir()
    with pytest.raises(BullError) as excinfo:
        rig.adoption.finish(rig.layout)
    message = excinfo.value.message
    assert "src/fx/a.fx" in message
    assert "tests/b.test" in message


# --- abandon ----------------------------------------------------------------------------------


def _abandonable(tmp_path: Path) -> Rig:
    rig = Rig(tmp_path, _adopting(3))
    rig.git.branches.add("adopt/main")
    return rig


def _trunk_backlog(rig: Rig) -> list[dict[str, str]]:
    text = rig.files.texts[rig.layout.backlog_file]
    data = json.loads(text)
    items: list[dict[str, str]] = data["items"]
    return items


def test_abandon_clears_the_adoption_and_commits(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.adoption.abandon(rig.layout)
    assert "abandon_adoption" in rig.store_names()
    assert rig.store.status.adoption is None
    assert rig.commits() == ["chore: abandon adoption"]


def test_abandon_keeps_the_adopt_main_branch(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.adoption.abandon(rig.layout)
    assert "adopt/main" in rig.git.branches


def test_abandon_without_an_adoption_is_refused(tmp_path: Path) -> None:
    rig = Rig(tmp_path, _empty_status())
    with pytest.raises(BullError):
        rig.adoption.abandon(rig.layout)
    assert "abandon_adoption" not in rig.store_names()
    assert rig.commits() == []


def test_abandon_off_the_trunk_is_refused(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.git.branch = "adopt/main"
    with pytest.raises(BullError):
        rig.adoption.abandon(rig.layout)
    assert "abandon_adoption" not in rig.store_names()
    assert rig.commits() == []
    assert rig.layout.backlog_file not in rig.files.texts


def test_abandon_reads_the_backlog_of_adopt_main_with_show_file(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.adoption.abandon(rig.layout)
    shown = [args for name, args in rig.git.calls if name == "show_file"]
    assert (rig.layout.root, "adopt/main", ".bull/backlog.json") in shown


def test_abandon_carries_over_items_that_exist_only_on_adopt_main(
    tmp_path: Path,
) -> None:
    rig = _abandonable(tmp_path)
    rig.files.texts[rig.layout.backlog_file] = _backlog_text([_raw("on-trunk")])
    rig.git.files_at[BACKLOG_ON_BRANCH] = _backlog_text(
        [_raw("on-trunk"), _raw("new-idea"), _raw("another")]
    )
    rig.adoption.abandon(rig.layout)
    assert [i["slug"] for i in _trunk_backlog(rig)] == [
        "on-trunk",
        "new-idea",
        "another",
    ]


def test_abandon_carries_items_in_as_queued_keeping_other_fields(
    tmp_path: Path,
) -> None:
    rig = _abandonable(tmp_path)
    rig.files.texts[rig.layout.backlog_file] = _backlog_text([_raw("on-trunk")])
    rig.git.files_at[BACKLOG_ON_BRANCH] = _backlog_text(
        [_raw("new-idea", "active"), _raw("old-idea", "dropped")]
    )
    rig.adoption.abandon(rig.layout)
    carried = _trunk_backlog(rig)[1:]
    assert carried == [
        {**_raw("new-idea"), "state": "queued"},
        {**_raw("old-idea"), "state": "queued"},
    ]


def test_abandon_leaves_items_already_on_the_trunk_as_they_are(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    on_trunk = _raw("shared", "accepted")
    rig.files.texts[rig.layout.backlog_file] = _backlog_text([on_trunk])
    rig.git.files_at[BACKLOG_ON_BRANCH] = _backlog_text(
        [_raw("shared", "queued"), _raw("extra")]
    )
    rig.adoption.abandon(rig.layout)
    assert _trunk_backlog(rig)[0] == on_trunk


def test_abandon_writes_the_backlog_in_the_backlog_format(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.files.texts[rig.layout.backlog_file] = _backlog_text([_raw("on-trunk")])
    rig.git.files_at[BACKLOG_ON_BRANCH] = _backlog_text([_raw("extra")])
    rig.adoption.abandon(rig.layout)
    data = json.loads(rig.files.texts[rig.layout.backlog_file])
    assert data["format"] == 1
    writes = [args for name, args in rig.files.calls if name == "write_json"]
    assert [path for path, _ in writes] == [rig.layout.backlog_file]


def test_abandon_without_a_trunk_backlog_carries_every_branch_item(
    tmp_path: Path,
) -> None:
    rig = _abandonable(tmp_path)
    rig.git.files_at[BACKLOG_ON_BRANCH] = _backlog_text([_raw("one"), _raw("two")])
    rig.adoption.abandon(rig.layout)
    assert [i["slug"] for i in _trunk_backlog(rig)] == ["one", "two"]


def test_abandon_writes_nothing_when_no_item_is_new(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.files.texts[rig.layout.backlog_file] = _backlog_text([_raw("same")])
    rig.git.files_at[BACKLOG_ON_BRANCH] = _backlog_text([_raw("same")])
    before = rig.files.texts[rig.layout.backlog_file]
    rig.adoption.abandon(rig.layout)
    assert not [name for name, _ in rig.files.calls if name == "write_json"]
    assert rig.files.texts[rig.layout.backlog_file] == before
    assert rig.commits() == ["chore: abandon adoption"]


def test_abandon_writes_nothing_when_adopt_main_has_no_items(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.files.texts[rig.layout.backlog_file] = _backlog_text([_raw("on-trunk")])
    rig.git.files_at[BACKLOG_ON_BRANCH] = _backlog_text([])
    rig.adoption.abandon(rig.layout)
    assert not [name for name, _ in rig.files.calls if name == "write_json"]


def test_abandon_with_no_backlog_on_adopt_main_still_abandons(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.files.texts[rig.layout.backlog_file] = _backlog_text([_raw("on-trunk")])
    rig.adoption.abandon(rig.layout)
    assert not [name for name, _ in rig.files.calls if name == "write_json"]
    assert "abandon_adoption" in rig.store_names()
    assert rig.commits() == ["chore: abandon adoption"]


def test_abandon_uses_the_configured_trunk(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.refs = MockRefs(trunk="develop")
    rig.git.branch = "develop"
    rig.git.branches.add("develop")
    rig.adoption.abandon(rig.layout)
    assert rig.store.status.adoption is None


def test_abandon_does_not_switch_branches(tmp_path: Path) -> None:
    rig = _abandonable(tmp_path)
    rig.adoption.abandon(rig.layout)
    assert rig.git.branch == "main"
    assert "switch" not in rig.git_names()
