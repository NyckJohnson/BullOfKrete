"""Tests for `bull.Modules.settings.toml_edit` (line-preserving settings edits).

Module-internal API under test (defined by these tests):
    set_key(text: str, key: str, value: SettingValue) -> str
    find_line(text: str, key: str) -> int       # 1-based; 0 when not found
    create_if_missing(path: Path) -> None       # writes "format = 1\\n" when absent
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from bull.Modules.settings.toml_edit import create_if_missing, find_line, set_key


def _parse(text: str) -> dict[str, object]:
    return tomllib.loads(text)


def test_set_key_replaces_an_existing_top_level_dotted_line() -> None:
    text = "format = 1\nusage.pause_5h = 80\nmax_attempts = 3\n"
    out = set_key(text, "usage.pause_5h", 90)
    assert out == "format = 1\nusage.pause_5h = 90\nmax_attempts = 3\n"


def test_set_key_replaces_a_plain_top_level_line() -> None:
    out = set_key("format = 1\nmax_attempts = 3\n", "max_attempts", 7)
    assert out == "format = 1\nmax_attempts = 7\n"


def test_set_key_replaces_the_key_inside_its_table() -> None:
    text = "format = 1\n[usage]\npause_5h = 80\npause_weekly = 90\n"
    out = set_key(text, "usage.pause_5h", 70)
    assert out == "format = 1\n[usage]\npause_5h = 70\npause_weekly = 90\n"
    assert _parse(out)["usage"] == {"pause_5h": 70, "pause_weekly": 90}


def test_set_key_does_not_touch_same_named_key_in_another_table() -> None:
    text = "format = 1\n[other]\npause_5h = 1\n[usage]\npause_5h = 80\n"
    out = set_key(text, "usage.pause_5h", 60)
    assert _parse(out) == {
        "format": 1,
        "other": {"pause_5h": 1},
        "usage": {"pause_5h": 60},
    }


def test_set_key_appends_a_dotted_key_when_absent() -> None:
    out = set_key("format = 1\n", "usage.pause_5h", 90)
    assert out == "format = 1\nusage.pause_5h = 90\n"


def test_set_key_appends_a_plain_key_when_absent() -> None:
    out = set_key("format = 1\n", "max_attempts", 5)
    assert out == "format = 1\nmax_attempts = 5\n"


def test_set_key_appends_a_newline_when_the_file_lacks_one() -> None:
    out = set_key("format = 1", "max_attempts", 5)
    assert out == "format = 1\nmax_attempts = 5\n"


def test_set_key_on_empty_text_writes_just_the_key() -> None:
    assert set_key("", "max_attempts", 5) == "max_attempts = 5\n"


def test_set_key_keeps_comments_blank_lines_and_other_keys() -> None:
    text = '# my config\nformat = 1\n\n# attempts\nmax_attempts = 3  # old\n\nreview_mode = "split"\n'
    out = set_key(text, "max_attempts", 4)
    lines = out.splitlines()
    assert lines[0] == "# my config"
    assert lines[1] == "format = 1"
    assert lines[2] == ""
    assert lines[3] == "# attempts"
    assert lines[4].startswith("max_attempts = 4")
    assert lines[5] == ""
    assert lines[6] == 'review_mode = "split"'
    assert len(lines) == 7


def test_set_key_appended_key_stays_top_level_when_file_ends_in_a_table() -> None:
    text = 'format = 1\n[models]\nreviewer = "opus"\n'
    out = set_key(text, "max_attempts", 5)
    parsed = _parse(out)
    assert parsed["max_attempts"] == 5
    assert parsed["models"] == {"reviewer": "opus"}


def test_set_key_into_an_existing_table_stays_valid_toml() -> None:
    text = "format = 1\n[usage]\npause_weekly = 90\n"
    out = set_key(text, "usage.pause_5h", 70)
    assert _parse(out)["usage"] == {"pause_weekly": 90, "pause_5h": 70}


def test_set_key_preserves_other_lines_around_a_table_insert() -> None:
    text = 'format = 1\n# keep me\n[usage]\npause_weekly = 90\n[models]\nreviewer = "opus"\n'
    out = set_key(text, "usage.pause_5h", 70)
    assert "# keep me\n" in out
    assert 'reviewer = "opus"' in out
    assert _parse(out) == {
        "format": 1,
        "usage": {"pause_weekly": 90, "pause_5h": 70},
        "models": {"reviewer": "opus"},
    }


def test_set_key_twice_replaces_rather_than_duplicates() -> None:
    once = set_key("format = 1\n", "max_attempts", 5)
    twice = set_key(once, "max_attempts", 6)
    assert twice == "format = 1\nmax_attempts = 6\n"


@pytest.mark.parametrize(
    ("value", "expected_line"),
    [
        (5, "k = 5"),
        (True, "k = true"),
        (False, "k = false"),
        ("main", 'k = "main"'),
        (("a", "b"), 'k = ["a", "b"]'),
        ((), "k = []"),
    ],
)
def test_set_key_renders_values_as_toml(value: object, expected_line: str) -> None:
    out = set_key("", "k", value)  # type: ignore[arg-type]
    assert out == expected_line + "\n"


@pytest.mark.parametrize(
    "value",
    ['say "hi"', "back\\slash", 'both \\" mixed', "plain", "", "hash # not comment"],
)
def test_set_key_string_round_trips_through_tomllib(value: str) -> None:
    out = set_key("format = 1\n", "base_branch", value)
    assert _parse(out)["base_branch"] == value


def test_set_key_list_round_trips_with_awkward_items() -> None:
    items = ('a"b', "c\\d", "*/mocks/*", "x, y")
    out = set_key("format = 1\n", "coverage.exclude", items)
    assert _parse(out)["coverage"] == {"exclude": list(items)}


def test_set_key_dotted_values_round_trip_to_nested_tables() -> None:
    out = set_key("format = 1\n", "models.reviewer", "opus")
    assert _parse(out) == {"format": 1, "models": {"reviewer": "opus"}}


# ---- find_line ----

SAMPLE = (
    "# header\n"  # 1
    "format = 1\n"  # 2
    "max_attempts = 3\n"  # 3
    "usage.pause_5h = 80\n"  # 4
    "\n"  # 5
    "[models]\n"  # 6
    'reviewer = "opus"\n'  # 7
    "[coverage]\n"  # 8
    "exclude = []\n"  # 9
)


@pytest.mark.parametrize(
    ("key", "line"),
    [
        ("format", 2),
        ("max_attempts", 3),
        ("usage.pause_5h", 4),
        ("models.reviewer", 7),
        ("coverage.exclude", 9),
    ],
)
def test_find_line_returns_the_assignment_line(key: str, line: int) -> None:
    assert find_line(SAMPLE, key) == line


def test_find_line_falls_back_to_the_table_line_for_a_missing_key_in_it() -> None:
    assert find_line(SAMPLE, "models.nonexistent") == 6


@pytest.mark.parametrize("key", ["nope", "nope.deeper", "usage.pause_weekly"])
def test_find_line_returns_zero_when_not_found(key: str) -> None:
    assert find_line(SAMPLE, key) == 0


def test_find_line_returns_zero_for_empty_text() -> None:
    assert find_line("", "max_attempts") == 0


def test_find_line_ignores_commented_out_assignments() -> None:
    assert find_line("format = 1\n# max_attempts = 3\n", "max_attempts") == 0


def test_find_line_matches_the_key_in_the_right_table_only() -> None:
    text = "[other]\npause_5h = 1\n[usage]\npause_5h = 80\n"
    assert find_line(text, "usage.pause_5h") == 4


# ---- create_if_missing ----


def test_create_if_missing_writes_a_format_one_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    create_if_missing(path)
    assert _parse(path.read_text()) == {"format": 1}


def test_create_if_missing_makes_parent_folders(tmp_path: Path) -> None:
    path = tmp_path / "parts" / "api.toml"
    create_if_missing(path)
    assert _parse(path.read_text()) == {"format": 1}


def test_create_if_missing_leaves_an_existing_file_untouched(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("format = 1\n# mine\nmax_attempts = 9\n")
    create_if_missing(path)
    assert path.read_text() == "format = 1\n# mine\nmax_attempts = 9\n"
