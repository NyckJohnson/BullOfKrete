"""Tests for `bull.Modules.features.ideas`: reading ideas from Markdown and making slugs."""

from __future__ import annotations

import pytest

from bull.Modules.features.Contracts import Idea
from bull.Modules.features.ideas import LiveIdeaReader

READER = LiveIdeaReader()


def test_each_h2_section_is_one_idea_with_trimmed_body_as_description() -> None:
    text = "# Ideas\n\n## Reset button\n\n  Sets the counter to zero.  \n\n## Dark mode\nA darker theme.\n"
    assert READER.read(text) == [
        Idea("Reset button", "Sets the counter to zero."),
        Idea("Dark mode", "A darker theme."),
    ]


def test_sections_take_precedence_over_list_items() -> None:
    text = "## Export\nWrite a CSV.\n- Ignored: not used when sections exist\n"
    ideas = READER.read(text)
    assert [i.title for i in ideas] == ["Export"]


def test_top_level_list_items_split_title_and_description_at_the_colon() -> None:
    text = "- Reset button: sets the counter to zero\n- Dark mode: a darker theme\n"
    assert READER.read(text) == [
        Idea("Reset button", "sets the counter to zero"),
        Idea("Dark mode", "a darker theme"),
    ]


def test_list_item_without_colon_is_title_only() -> None:
    assert READER.read("- Just a title\n") == [Idea("Just a title", "")]


def test_list_item_splits_at_first_colon_only() -> None:
    assert READER.read("- Clock: shows 12:30 in UTC\n") == [
        Idea("Clock", "shows 12:30 in UTC")
    ]


def test_nested_list_items_are_not_ideas() -> None:
    text = "- Parent: top level\n  - Child: nested\n    - Grandchild: deeper\n"
    assert [i.title for i in READER.read(text)] == ["Parent"]


def test_section_filter_reads_only_items_under_that_heading() -> None:
    text = (
        "## Now\n- Reset button: zero it\n- Dark mode: darker\n"
        "## Later\n- Export: csv\n"
    )
    assert READER.read(text, section="Later") == [Idea("Export", "csv")]
    assert [i.title for i in READER.read(text, section="Now")] == [
        "Reset button",
        "Dark mode",
    ]


def test_section_filter_ignores_items_before_the_first_heading() -> None:
    text = "- Outside: not in a section\n## Ideas\n- Inside: yes\n"
    assert READER.read(text, section="Ideas") == [Idea("Inside", "yes")]


def test_section_filter_with_missing_heading_returns_empty() -> None:
    assert READER.read("## Now\n- A: b\n", section="Later") == []


def test_indented_continuation_line_is_joined_to_the_description_with_a_newline() -> (
    None
):
    text = "- Reset button: sets the counter\n  back to zero\n- Dark mode: darker\n"
    assert READER.read(text) == [
        Idea("Reset button", "sets the counter\nback to zero"),
        Idea("Dark mode", "darker"),
    ]


def test_checked_checkbox_items_are_skipped() -> None:
    text = "- [x] Done thing: already shipped\n- [ ] Open thing: still to do\n"
    assert [i.title for i in READER.read(text)] == ["Open thing"]


def test_unchecked_checkbox_item_is_read_as_a_plain_item() -> None:
    assert READER.read("- [ ] B\n") == [Idea("B", "")]
    assert READER.read("- [ ] B: the description\n") == [Idea("B", "the description")]


def test_section_filter_matches_the_heading_case_insensitively() -> None:
    text = "## Now\n- A: a\n## Later Ideas\n- B: b\n"
    assert READER.read(text, section="later ideas") == [Idea("B", "b")]
    assert READER.read(text, section="NOW") == [Idea("A", "a")]


@pytest.mark.parametrize(
    "text", ["", "\n\n", "Just a paragraph.\n\nAnother one.\n", "# Only a title\n"]
)
def test_text_without_ideas_returns_empty_list(text: str) -> None:
    assert READER.read(text) == []


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Reset Button", "reset-button"),
        ("Dark   mode!!", "dark-mode"),
        ("  --Export (CSV)--  ", "export-csv"),
        ("v2.0 Release", "v2-0-release"),
        ("a", "a"),
    ],
)
def test_slug_lowercases_and_collapses_non_alphanumerics_to_dashes(
    title: str, expected: str
) -> None:
    assert READER.slug(title, set()) == expected


def test_slug_longer_than_40_characters_is_cut_at_a_dash() -> None:
    slug = READER.slug("Add a really long feature title that goes on forever", set())
    assert slug == "add-a-really-long-feature-title-that"
    assert len(slug) <= 40


def test_slug_that_fits_in_40_characters_is_unchanged() -> None:
    title = "a" * 9 + " " + "b" * 9 + " " + "c" * 9 + " " + "d" * 9  # 39 chars
    assert READER.slug(title, set()) == "-".join(["a" * 9, "b" * 9, "c" * 9, "d" * 9])


def test_taken_slug_gets_suffix_2() -> None:
    assert READER.slug("Reset button", {"reset-button"}) == "reset-button-2"


def test_taken_slug_and_suffix_2_gets_suffix_3() -> None:
    taken = ["reset-button", "reset-button-2"]
    assert READER.slug("Reset button", taken) == "reset-button-3"


def test_slug_not_taken_has_no_suffix_even_when_others_are_taken() -> None:
    assert READER.slug("Dark mode", {"reset-button"}) == "dark-mode"
