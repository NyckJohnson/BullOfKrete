"""Tests for the features contract types."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from bull.Modules.features.Contracts import BacklogItem, FeaturePlan, Idea, ItemState

NOW = datetime(2026, 11, 7, tzinfo=UTC)


def _item() -> BacklogItem:
    return BacklogItem("a", "A", "desc", ItemState.QUEUED, NOW, "docs/features/a.md")


@pytest.mark.parametrize(
    ("member", "value"),
    [
        (ItemState.QUEUED, "queued"),
        (ItemState.ACTIVE, "active"),
        (ItemState.ACCEPTED, "accepted"),
        (ItemState.ABANDONED, "abandoned"),
        (ItemState.DROPPED, "dropped"),
    ],
)
def test_item_state_values_match_backlog_json(member: ItemState, value: str) -> None:
    assert member.value == value
    assert ItemState(value) is member


def test_item_state_has_exactly_five_members() -> None:
    assert len(list(ItemState)) == 5


def test_item_state_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        ItemState("done")


def test_backlog_item_holds_its_fields() -> None:
    item = _item()
    assert (item.slug, item.title, item.description) == ("a", "A", "desc")
    assert item.state is ItemState.QUEUED
    assert item.added == NOW
    assert item.brief == "docs/features/a.md"


def test_backlog_item_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _item().slug = "b"  # type: ignore[misc]


def test_backlog_item_equal_by_value() -> None:
    assert _item() == _item()


def test_idea_holds_title_and_description() -> None:
    idea = Idea("Dark mode", "A darker theme.")
    assert idea.title == "Dark mode"
    assert idea.description == "A darker theme."


def test_idea_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Idea("a", "b").title = "c"  # type: ignore[misc]


def test_feature_plan_holds_its_fields() -> None:
    plan = FeaturePlan({"Counter": (1, 2)}, ("New",), ("Counter",), True)
    assert plan.reopened == {"Counter": (1, 2)}
    assert plan.new_modules == ("New",)
    assert plan.contract_changes == ("Counter",)
    assert plan.skeleton_needed is True


def test_feature_plan_is_frozen() -> None:
    plan = FeaturePlan({}, (), (), False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.skeleton_needed = True  # type: ignore[misc]
