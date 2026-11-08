"""Tests for `bull.Modules.status.summary` (`LiveProgress`).

Shapes chosen here: `LiveProgress(app=, store=, refs=, git=)`; output wording is free, so tests
look for the facts the spec lists (stage, checkpoints, units done/total, module states, ...).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.status.Contracts import (
    ActiveFeature,
    Mode,
    Plan,
    PlanItem,
    Track,
    Waiting,
)
from bull.Modules.status.mocks import SAMPLE_TIME, MockRefs, MockStatusStore
from bull.Modules.status.model import status_to_json
from bull.Modules.status.summary import LiveProgress

APP = sample_layout(Path("/tmp/apps/tally"))


class Rig:
    def __init__(self) -> None:
        self.store = MockStatusStore()
        self.refs = MockRefs()
        self.git = MockGit()
        self.progress = LiveProgress(
            app=APP, store=self.store, refs=self.refs, git=self.git
        )


@pytest.fixture
def rig() -> Rig:
    return Rig()


# --- next_step ---------------------------------------------------------------------------


def test_next_step_reads_the_current_branch_of_the_app_root(rig: Rig) -> None:
    rig.git.branch = "module/Counter"
    step = rig.progress.next_step()
    assert ("current_branch", (APP.root,)) in rig.git.calls
    assert step.mode is Mode.APP
    assert "Counter" in step.text
    assert not step.text.startswith("switch to")


def test_next_step_on_an_unrelated_branch_says_to_switch(rig: Rig) -> None:
    rig.git.branch = "scratch"
    assert rig.progress.next_step().text.startswith("switch to")


def test_next_step_with_unknown_branch_does_not_ask_to_switch(rig: Rig) -> None:
    rig.git.branch = None
    step = rig.progress.next_step()
    assert not step.text.startswith("switch to")
    assert "Counter" in step.text


def test_next_step_mode_follows_the_store(rig: Rig) -> None:
    feature = ActiveFeature("dark-mode", Track(5, ()), ())
    rig.store.status = replace(rig.store.status, feature=feature)
    step = rig.progress.next_step()
    assert step.mode is Mode.FEATURE
    assert "dark-mode" in step.text


# --- summary -----------------------------------------------------------------------------


def test_summary_shows_stage_and_mode(rig: Rig) -> None:
    text = rig.progress.summary().lower()
    assert "stage 5" in text
    assert "app" in text


def test_summary_shows_the_active_features_stage_and_mode() -> None:
    rig = Rig()
    feature = ActiveFeature("dark-mode", Track(2, ("outline-approved",)), ())
    rig.store.status = replace(rig.store.status, feature=feature)
    text = rig.progress.summary().lower()
    assert "stage 2" in text
    assert "feature" in text
    assert "dark-mode" in text


def test_summary_lists_the_checkpoints(rig: Rig) -> None:
    text = rig.progress.summary()
    for name in ("outline-approved", "setup", "skeleton", "ui-approved"):
        assert name in text


def test_summary_shows_units_done_over_total(rig: Rig) -> None:
    assert "1/3" in rig.progress.summary()


def test_summary_shows_each_module_with_state_and_units(rig: Rig) -> None:
    lines = rig.progress.summary().splitlines()
    store_line = next(line for line in lines if "Store" in line)
    counter_lines = " ".join(line for line in lines if "Counter" in line)
    assert "done" in store_line
    assert "in_progress" in counter_lines
    assert "tests" in counter_lines
    assert "pending" in counter_lines


def test_summary_shows_pause_reason(rig: Rig) -> None:
    rig.store.pause("5-hour usage 90%")
    assert "5-hour usage 90%" in rig.progress.summary()


def test_summary_shows_the_wait(rig: Rig) -> None:
    waiting = Waiting("Counter", "contract change to Counter", SAMPLE_TIME)
    rig.store.status = replace(rig.store.status, waiting=waiting)
    text = rig.progress.summary()
    assert "Counter" in text
    assert "contract change to Counter" in text


def test_summary_shows_the_plan_label_and_items(rig: Rig) -> None:
    plan = Plan("verify", (PlanItem("login", True), PlanItem("export", False)))
    rig.store.status = replace(rig.store.status, plan=plan)
    text = rig.progress.summary()
    assert "verify" in text
    assert "login" in text
    assert "export" in text


def test_summary_without_pause_wait_or_plan_omits_them(rig: Rig) -> None:
    text = rig.progress.summary().lower()
    assert "paused" not in text
    assert "waiting" not in text


def test_summary_ends_with_the_next_step(rig: Rig) -> None:
    rig.git.branch = "main"
    expected = rig.progress.next_step().text
    assert expected in rig.progress.summary()


# --- as_json -----------------------------------------------------------------------------


def test_as_json_adds_mode_next_and_unit_counts(rig: Rig) -> None:
    data = rig.progress.as_json()
    assert data["mode"] == "app"
    assert data["next"] == rig.progress.next_step().text
    assert data["units_done"] == 1
    assert data["units_total"] == 3


def test_as_json_contains_the_status_file_content(rig: Rig) -> None:
    data = rig.progress.as_json()
    for key, value in status_to_json(rig.store.status).items():
        assert data[key] == value


def test_as_json_mode_is_feature_during_a_feature() -> None:
    rig = Rig()
    feature = ActiveFeature("dark-mode", Track(5, ()), ())
    rig.store.status = replace(rig.store.status, feature=feature)
    assert rig.progress.as_json()["mode"] == "feature"


def test_as_json_counts_zero_units_for_an_empty_status() -> None:
    rig = Rig()
    rig.store.create()
    data = rig.progress.as_json()
    assert data["units_done"] == 0
    assert data["units_total"] == 0


# --- tags --------------------------------------------------------------------------------


def test_tags_keeps_only_the_pipelines_names_sorted(rig: Rig) -> None:
    rig.git.tag_names = [
        "v1.0",
        "module/Store",
        "skeleton",
        "release-2",
        "feature/dark-mode/outline-approved",
        "adopt/baseline",
        "adopted",
        "app-accepted",
        "outline-approved",
        "setup",
        "ui-approved",
        "module/Counter",
        "wip",
    ]
    assert rig.progress.tags() == sorted(
        [
            "adopt/baseline",
            "adopted",
            "app-accepted",
            "feature/dark-mode/outline-approved",
            "module/Counter",
            "module/Store",
            "outline-approved",
            "setup",
            "skeleton",
            "ui-approved",
        ]
    )


def test_tags_asks_git_in_the_app_root(rig: Rig) -> None:
    rig.progress.tags()
    assert any(name == "tags" and args[0] == APP.root for name, args in rig.git.calls)


def test_tags_is_empty_when_the_repo_has_none_of_them(rig: Rig) -> None:
    rig.git.tag_names = ["v1.0", "release"]
    assert rig.progress.tags() == []


def test_tags_has_no_duplicates(rig: Rig) -> None:
    rig.git.tag_names = ["setup", "module/Store"]
    result = rig.progress.tags()
    assert result == sorted(set(result))
