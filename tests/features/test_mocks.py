"""Tests for the features mocks."""

from __future__ import annotations

import pytest

from bull.Modules.features.Contracts import FeaturePlan, Idea, ItemState
from bull.Modules.features.mocks import (
    MockBacklog,
    MockFeatureCycle,
    MockIdeaReader,
    sample_item,
)


def test_sample_item_is_queued_with_brief_path() -> None:
    item = sample_item("x-y", "X Y")
    assert item.slug == "x-y"
    assert item.title == "X Y"
    assert item.state is ItemState.QUEUED
    assert item.brief == "docs/features/x-y.md"


def test_backlog_starts_with_two_queued_items() -> None:
    items = MockBacklog().items()
    assert len(items) == 2
    assert all(i.state is ItemState.QUEUED for i in items)


def test_backlog_items_returns_a_copy() -> None:
    b = MockBacklog()
    b.items().clear()
    assert len(b.items()) == 2


def test_backlog_add_appends_queued_item_with_slug() -> None:
    b = MockBacklog()
    item = b.add(Idea("Export CSV!", "Write csv."))
    assert item.slug == "export-csv"
    assert item.description == "Write csv."
    assert item.state is ItemState.QUEUED
    assert b.items()[-1] == item


def test_backlog_add_top_inserts_first() -> None:
    b = MockBacklog()
    item = b.add(Idea("Urgent", "now"), top=True)
    assert b.items()[0] == item


def test_backlog_import_skips_existing_slugs() -> None:
    b = MockBacklog()
    added = b.import_ideas([Idea("Dark mode", "dup"), Idea("Export", "new")])
    assert [i.slug for i in added] == ["export"]
    assert len(b.items()) == 3


def test_backlog_import_empty_adds_nothing() -> None:
    assert MockBacklog().import_ideas([]) == []


def test_backlog_move_uses_one_based_position() -> None:
    b = MockBacklog()
    b.move("dark-mode", 1)
    assert [i.slug for i in b.items()] == ["dark-mode", "reset-button"]


def test_backlog_drop_marks_item_dropped_and_keeps_it() -> None:
    b = MockBacklog()
    b.drop("reset-button")
    states = {i.slug: i.state for i in b.items()}
    assert states == {"reset-button": ItemState.DROPPED, "dark-mode": ItemState.QUEUED}


def test_backlog_records_calls() -> None:
    b = MockBacklog()
    b.items()
    b.drop("dark-mode")
    assert [name for name, _ in b.calls] == ["items", "drop"]


def test_idea_reader_read_returns_canned_ideas_and_records_call() -> None:
    r = MockIdeaReader()
    ideas = r.read("text", "Section")
    assert ideas == r.ideas
    assert r.calls[-1] == ("read", ("text", "Section"))


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Dark Mode", "dark-mode"),
        ("  Hello,   World!! ", "hello-world"),
        ("A_b", "a-b"),
    ],
)
def test_idea_reader_slug_lowercases_and_dashes(title: str, expected: str) -> None:
    assert MockIdeaReader().slug(title, []) == expected


def test_idea_reader_slug_suffixes_when_taken() -> None:
    r = MockIdeaReader()
    assert r.slug("Dark mode", ["dark-mode"]) == "dark-mode-2"
    assert r.slug("Dark mode", ["dark-mode", "dark-mode-2"]) == "dark-mode-3"


def test_idea_reader_slug_is_at_most_40_chars() -> None:
    assert len(MockIdeaReader().slug("word " * 30, [])) <= 40


def test_cycle_start_marks_item_active() -> None:
    c = MockFeatureCycle()
    assert c.start("reset-button").state is ItemState.ACTIVE
    assert c.calls[-1] == ("start", ("reset-button",))


def test_cycle_start_without_slug_records_none() -> None:
    c = MockFeatureCycle()
    c.start()
    assert c.calls[-1] == ("start", (None,))


def test_cycle_plan_returns_configured_plan() -> None:
    c = MockFeatureCycle()
    plan = FeaturePlan({"X": (2,)}, ("Y",), (), True)
    c.feature_plan = plan
    assert c.plan() is plan


def test_cycle_accept_marks_accepted() -> None:
    assert MockFeatureCycle().accept().state is ItemState.ACCEPTED


def test_cycle_abandon_marks_abandoned() -> None:
    assert MockFeatureCycle().abandon().state is ItemState.ABANDONED
