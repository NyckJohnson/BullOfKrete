"""Tests for `bull.Modules.features.backlog`: the queue in `.bull/backlog.json`.

Assumed constructor (the stub has none): `LiveBacklog(app, files, clock, ideas)` with
`app: AppLayout`, `files: Files`, `clock: Clock`, `ideas: IdeaReader` (used for slugs).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from bull.Modules.features.backlog import LiveBacklog
from bull.Modules.features.Contracts import BacklogItem, Idea, ItemState
from bull.Modules.features.mocks import MockIdeaReader
from bull.Modules.foundation.mocks import (
    SAMPLE_TIME,
    MockClock,
    MockFiles,
    sample_layout,
)

LAYOUT = sample_layout()


def _make(
    existing: Sequence[dict[str, Any]] | None = None,
) -> tuple[LiveBacklog, MockFiles, MockClock]:
    files = MockFiles()
    clock = MockClock()
    if existing is not None:
        files.texts[LAYOUT.backlog_file] = (
            json.dumps({"format": 1, "items": list(existing)}, indent=2) + "\n"
        )
    return LiveBacklog(LAYOUT, files, clock, MockIdeaReader()), files, clock


def _raw(slug: str, state: str = "queued", title: str | None = None) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title or slug.replace("-", " ").capitalize(),
        "description": f"about {slug}",
        "state": state,
        "added": "2026-11-07T12:00:00Z",
        "brief": f"docs/features/{slug}.md",
    }


def _saved(files: MockFiles) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(files.texts[LAYOUT.backlog_file])
    return data


def _slugs(backlog: LiveBacklog) -> list[str]:
    return [i.slug for i in backlog.items()]


def _queued(backlog: LiveBacklog) -> list[str]:
    return [i.slug for i in backlog.items() if i.state is ItemState.QUEUED]


# items / file format


def test_items_is_empty_when_no_backlog_file_exists() -> None:
    backlog, _, _ = _make()
    assert backlog.items() == []


def test_items_reads_backlog_json_in_queue_order() -> None:
    backlog, _, _ = _make([_raw("b"), _raw("a", "accepted")])
    items = backlog.items()
    assert [i.slug for i in items] == ["b", "a"]
    assert items[0] == BacklogItem(
        slug="b",
        title="B",
        description="about b",
        state=ItemState.QUEUED,
        added=SAMPLE_TIME,
        brief="docs/features/b.md",
    )
    assert items[1].state is ItemState.ACCEPTED


def test_items_parses_every_state_value() -> None:
    states = ["queued", "active", "accepted", "abandoned", "dropped"]
    backlog, _, _ = _make([_raw(f"s{n}", s) for n, s in enumerate(states)])
    assert [i.state for i in backlog.items()] == [
        ItemState.QUEUED,
        ItemState.ACTIVE,
        ItemState.ACCEPTED,
        ItemState.ABANDONED,
        ItemState.DROPPED,
    ]


def test_add_writes_backlog_json_with_format_and_item_fields() -> None:
    backlog, files, _ = _make()
    backlog.add(Idea("Reset button", "Sets the counter to zero."))
    assert _saved(files) == {
        "format": 1,
        "items": [
            {
                "slug": "reset-button",
                "title": "Reset button",
                "description": "Sets the counter to zero.",
                "state": "queued",
                "added": "2026-11-07T12:00:00Z",
                "brief": "docs/features/reset-button.md",
            }
        ],
    }


def test_backlog_file_is_indented_sorted_and_ends_with_newline() -> None:
    backlog, files, _ = _make()
    backlog.add(Idea("Reset button", "zero"))
    text = files.texts[LAYOUT.backlog_file]
    assert text.endswith("\n")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_added_items_survive_a_round_trip_through_the_file() -> None:
    backlog, files, clock = _make()
    added = backlog.add(Idea("Reset button", "zero"))
    other = LiveBacklog(LAYOUT, files, clock, MockIdeaReader())
    assert other.items() == [added]


# add


def test_add_returns_queued_item_stamped_with_clock_time() -> None:
    backlog, _, _ = _make()
    item = backlog.add(Idea("Reset button", "Sets the counter to zero."))
    assert item == BacklogItem(
        slug="reset-button",
        title="Reset button",
        description="Sets the counter to zero.",
        state=ItemState.QUEUED,
        added=SAMPLE_TIME,
        brief="docs/features/reset-button.md",
    )


def test_add_appends_at_the_end_by_default() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("b")])
    backlog.add(Idea("Cee", ""))
    assert _slugs(backlog) == ["a", "b", "cee"]


def test_add_with_top_queues_first() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("b")])
    backlog.add(Idea("Cee", ""), top=True)
    assert _slugs(backlog) == ["cee", "a", "b"]


def test_add_with_taken_slug_gets_numeric_suffix() -> None:
    backlog, _, _ = _make([_raw("export")])
    first = backlog.add(Idea("Export", "csv"))
    second = backlog.add(Idea("Export", "json"))
    assert first.slug == "export-2"
    assert second.slug == "export-3"


def test_add_counts_dropped_items_as_taken_slugs() -> None:
    backlog, _, _ = _make([_raw("export", "dropped")])
    assert backlog.add(Idea("Export", "")).slug == "export-2"


def test_add_writes_the_brief_file() -> None:
    backlog, files, _ = _make()
    backlog.add(Idea("Reset button", "zero"))
    text = files.texts[LAYOUT.features_dir / "reset-button.md"]
    assert text.startswith("# Reset button")
    for heading in ("## Idea", "## Discussion notes", "## Agreed scope"):
        assert heading in text


# import_ideas


def test_import_adds_all_new_ideas_in_order_and_returns_them() -> None:
    backlog, _, _ = _make([_raw("a")])
    added = backlog.import_ideas([Idea("Bee", "b"), Idea("Cee", "c")])
    assert [i.slug for i in added] == ["bee", "cee"]
    assert _slugs(backlog) == ["a", "bee", "cee"]
    assert all(i.state is ItemState.QUEUED for i in added)


def test_import_skips_idea_whose_slug_is_already_in_backlog() -> None:
    backlog, _, _ = _make([_raw("reset-button", title="Reset button")])
    added = backlog.import_ideas([Idea("Reset-Button!", "x"), Idea("Dark mode", "y")])
    assert [i.slug for i in added] == ["dark-mode"]
    assert _slugs(backlog) == ["reset-button", "dark-mode"]


def test_import_skips_idea_whose_title_matches_case_insensitively() -> None:
    backlog, _, _ = _make([_raw("rb", title="Reset Button")])
    added = backlog.import_ideas([Idea("reset button", "again")])
    assert added == []
    assert _slugs(backlog) == ["rb"]


def test_import_skips_ideas_matching_dropped_or_accepted_items() -> None:
    backlog, _, _ = _make([_raw("old-one", "dropped"), _raw("done-one", "accepted")])
    assert backlog.import_ideas([Idea("Old one", ""), Idea("Done one", "")]) == []


def test_import_of_nothing_returns_empty_and_changes_nothing() -> None:
    backlog, _, _ = _make([_raw("a")])
    assert backlog.import_ideas([]) == []
    assert _slugs(backlog) == ["a"]


def test_import_writes_a_brief_for_each_added_idea_only() -> None:
    backlog, files, _ = _make([_raw("a")])
    backlog.import_ideas([Idea("A", ""), Idea("Bee", "b")])
    assert (LAYOUT.features_dir / "bee.md") in files.texts
    assert (LAYOUT.features_dir / "a.md") not in files.texts


# move


def test_move_to_position_1_puts_item_first() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("b"), _raw("c")])
    backlog.move("c", 1)
    assert _queued(backlog) == ["c", "a", "b"]


def test_move_to_last_position_puts_item_last() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("b"), _raw("c")])
    backlog.move("a", 3)
    assert _queued(backlog) == ["b", "c", "a"]


def test_move_to_middle_position() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("b"), _raw("c")])
    backlog.move("a", 2)
    assert _queued(backlog) == ["b", "a", "c"]


def test_move_positions_count_only_queued_items() -> None:
    backlog, _, _ = _make(
        [_raw("a"), _raw("x", "accepted"), _raw("b"), _raw("y", "dropped"), _raw("c")]
    )
    backlog.move("c", 2)
    assert _queued(backlog) == ["a", "c", "b"]


def test_move_leaves_non_queued_items_in_the_file() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("x", "accepted"), _raw("b")])
    backlog.move("b", 1)
    assert sorted(_slugs(backlog)) == ["a", "b", "x"]
    assert {i.slug: i.state for i in backlog.items()}["x"] is ItemState.ACCEPTED


def test_move_is_saved_to_the_file() -> None:
    backlog, files, _ = _make([_raw("a"), _raw("b")])
    backlog.move("b", 1)
    assert [i["slug"] for i in _saved(files)["items"] if i["state"] == "queued"] == [
        "b",
        "a",
    ]


# drop


def test_drop_marks_queued_item_dropped() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("b")])
    backlog.drop("a")
    states = {i.slug: i.state for i in backlog.items()}
    assert states == {"a": ItemState.DROPPED, "b": ItemState.QUEUED}


def test_drop_keeps_the_item_in_the_file_and_its_other_fields() -> None:
    backlog, files, _ = _make([_raw("a")])
    backlog.drop("a")
    saved = _saved(files)["items"]
    assert saved == [{**_raw("a"), "state": "dropped"}]


def test_drop_removes_item_from_the_queue() -> None:
    backlog, _, _ = _make([_raw("a"), _raw("b")])
    backlog.drop("a")
    assert _queued(backlog) == ["b"]
