"""Tests for `bull.Modules.features.cli` (`bull feature ...`).

Shapes chosen here (for the code-writer), following the decisions-log `cli.py` convention:
  - `register(commands, backlog, ideas, cycle)`: three zero-argument providers
    (`Callable[[], Backlog]`, `Callable[[], IdeaReader]`, `Callable[[], FeatureCycle]`), called
    only when a command that needs them runs. Adds a `feature` parser; every leaf sets
    `run(args, out) -> int`.
  - `feature add "<Title>: <desc>" [--top]` splits at the first colon (no colon: the whole text
    is the title, empty description) and calls `backlog.add(Idea(title, desc), top)`.
  - `feature import <file> [--section <heading>] [--dry-run]` reads the file, calls
    `ideas.read(text, section)`, then `backlog.import_ideas(ideas)`; prints the added titles.
    `--dry-run` prints the ideas that would be added (not already in the backlog by slug or
    case-insensitive title) and calls neither `add` nor `import_ideas`.
  - `feature list` prints one line per item: position, slug, state, title (positions 1-based).
    `list --json` writes a list of objects with `slug`, `title`, `state` (state value string).
  - `move <slug> <pos>`, `drop <slug>` call the backlog; `start [<slug>]`, `plan`, `accept`,
    `abandon` call the cycle; each prints the slug (or plan summary) and returns 0.
  - Refusals are raised (`BullError`), never printed.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.features.Contracts import Idea
from bull.Modules.features.mocks import MockBacklog, MockFeatureCycle, MockIdeaReader
from bull.Modules.foundation.Contracts import BullError


class Rig:
    def __init__(self) -> None:
        self.backlog = MockBacklog()
        self.ideas = MockIdeaReader()
        self.cycle = MockFeatureCycle()
        self.provided: list[str] = []
        # imported here so the file collects while `cli.py` is still a stub
        from bull.Modules.features.cli import register

        self.parser = argparse.ArgumentParser(prog="bull")
        commands = self.parser.add_subparsers(dest="command")
        register(
            commands,
            lambda: self._note("backlog", self.backlog),
            lambda: self._note("ideas", self.ideas),
            lambda: self._note("cycle", self.cycle),
        )

    def _note(self, name: str, value: Any) -> Any:
        self.provided.append(name)
        return value

    def run(self, *argv: str) -> tuple[int, str]:
        args = self.parser.parse_args(["feature", *argv])
        out = io.StringIO()
        code = args.run(args, out)
        return code, out.getvalue()


@pytest.fixture
def rig() -> Rig:
    return Rig()


def names(calls: list[tuple[str, tuple[object, ...]]]) -> list[str]:
    return [name for name, _ in calls]


# --- registration ------------------------------------------------------------------------


def test_register_does_not_call_any_provider(rig: Rig) -> None:
    rig.parser.parse_args(["feature", "list"])
    rig.parser.parse_args(["feature", "add", "A: b"])
    rig.parser.parse_args(["feature", "start"])
    rig.parser.parse_args(["feature", "plan"])
    assert rig.provided == []


# --- add ---------------------------------------------------------------------------------


def test_add_splits_title_and_description_at_the_first_colon(rig: Rig) -> None:
    code, text = rig.run("add", "Sound: Beep: loudly.")
    assert code == 0
    assert rig.backlog.calls == [("add", (Idea("Sound", "Beep: loudly."), False))]
    assert "sound" in text.lower()


def test_add_without_a_colon_uses_the_whole_text_as_the_title(rig: Rig) -> None:
    rig.run("add", "Sound effects")
    assert rig.backlog.calls == [("add", (Idea("Sound effects", ""), False))]


def test_add_top_puts_the_item_first(rig: Rig) -> None:
    rig.run("add", "Sound: A beep.", "--top")
    assert rig.backlog.calls == [("add", (Idea("Sound", "A beep."), True))]
    assert rig.backlog.backlog[0].title == "Sound"


# --- import ------------------------------------------------------------------------------


def _ideas_file(tmp_path: Path) -> Path:
    path = tmp_path / "ideas.md"
    path.write_text("## Reset button\nx\n## Export\ny\n", encoding="utf-8")
    return path


def test_import_reads_the_file_and_imports_the_ideas(rig: Rig, tmp_path: Path) -> None:
    path = _ideas_file(tmp_path)
    code, text = rig.run("import", str(path))
    assert code == 0
    assert rig.ideas.calls == [("read", (path.read_text(encoding="utf-8"), None))]
    assert names(rig.backlog.calls)[0] == "import_ideas"
    assert rig.backlog.calls[0][1] == (tuple(rig.ideas.ideas),)
    assert "Export" in text


def test_import_prints_only_the_ideas_that_were_added(rig: Rig, tmp_path: Path) -> None:
    _, text = rig.run("import", str(_ideas_file(tmp_path)))
    # MockBacklog already holds "Reset button" and "Dark mode"
    assert "Export" in text
    assert "Dark mode" not in text


def test_import_section_is_passed_to_the_reader(rig: Rig, tmp_path: Path) -> None:
    path = _ideas_file(tmp_path)
    rig.run("import", str(path), "--section", "Later features")
    assert rig.ideas.calls == [
        ("read", (path.read_text(encoding="utf-8"), "Later features"))
    ]


def test_import_dry_run_lists_new_ideas_without_writing(
    rig: Rig, tmp_path: Path
) -> None:
    code, text = rig.run("import", str(_ideas_file(tmp_path)), "--dry-run")
    assert code == 0
    assert "Export" in text
    assert "Dark mode" not in text
    assert "import_ideas" not in names(rig.backlog.calls)
    assert "add" not in names(rig.backlog.calls)


def test_import_dry_run_skips_titles_already_queued_ignoring_case(
    rig: Rig, tmp_path: Path
) -> None:
    rig.ideas.ideas = [Idea("RESET BUTTON", "dup"), Idea("Sound", "new")]
    _, text = rig.run("import", str(_ideas_file(tmp_path)), "--dry-run")
    assert "Sound" in text
    assert "RESET BUTTON" not in text


def test_import_of_a_missing_file_is_refused(rig: Rig, tmp_path: Path) -> None:
    with pytest.raises(BullError):
        rig.run("import", str(tmp_path / "missing.md"))
    assert rig.backlog.calls == []


def test_import_with_nothing_found_adds_nothing(rig: Rig, tmp_path: Path) -> None:
    rig.ideas.ideas = []
    code, _ = rig.run("import", str(_ideas_file(tmp_path)))
    assert code == 0
    assert rig.backlog.backlog and len(rig.backlog.backlog) == 2


# --- list --------------------------------------------------------------------------------


def test_list_shows_position_slug_state_and_title(rig: Rig) -> None:
    code, text = rig.run("list")
    assert code == 0
    lines = [line for line in text.splitlines() if line.strip()]
    first = next(line for line in lines if "reset-button" in line)
    second = next(line for line in lines if "dark-mode" in line)
    assert "1" in first and "queued" in first and "Reset button" in first
    assert "2" in second and "queued" in second and "Dark mode" in second
    assert lines.index(first) < lines.index(second)


def test_list_json_writes_only_the_items_as_json(rig: Rig) -> None:
    code, text = rig.run("list", "--json")
    assert code == 0
    data = json.loads(text)
    assert [d["slug"] for d in data] == ["reset-button", "dark-mode"]
    assert [d["title"] for d in data] == ["Reset button", "Dark mode"]
    assert [d["state"] for d in data] == ["queued", "queued"]


def test_list_of_an_empty_backlog_succeeds(rig: Rig) -> None:
    rig.backlog.backlog = []
    code, text = rig.run("list")
    assert code == 0
    assert "reset-button" not in text
    _, as_json = rig.run("list", "--json")
    assert json.loads(as_json) == []


# --- move and drop -----------------------------------------------------------------------


def test_move_passes_slug_and_position(rig: Rig) -> None:
    code, _ = rig.run("move", "dark-mode", "1")
    assert code == 0
    assert rig.backlog.calls == [("move", ("dark-mode", 1))]


def test_move_rejects_a_non_numeric_position(rig: Rig) -> None:
    with pytest.raises(SystemExit):
        rig.run("move", "dark-mode", "first")


def test_drop_passes_the_slug(rig: Rig) -> None:
    code, _ = rig.run("drop", "dark-mode")
    assert code == 0
    assert rig.backlog.calls == [("drop", ("dark-mode",))]


def test_backlog_refusals_are_raised_not_printed(rig: Rig) -> None:
    def refuse(slug: str) -> None:
        raise BullError("No queued feature.", "Run `bull feature list`.")

    rig.backlog.drop = refuse  # type: ignore[method-assign]
    with pytest.raises(BullError):
        rig.run("drop", "nope")


# --- cycle commands ----------------------------------------------------------------------


def test_start_without_slug_starts_the_first_queued(rig: Rig) -> None:
    code, text = rig.run("start")
    assert code == 0
    assert rig.cycle.calls == [("start", (None,))]
    assert "reset-button" in text


def test_start_with_slug_passes_it_on(rig: Rig) -> None:
    rig.run("start", "dark-mode")
    assert rig.cycle.calls == [("start", ("dark-mode",))]


def test_plan_calls_the_cycle_and_reports_the_plan(rig: Rig) -> None:
    code, text = rig.run("plan")
    assert code == 0
    assert rig.cycle.calls == [("plan", ())]
    assert "Counter" in text


def test_accept_calls_the_cycle(rig: Rig) -> None:
    code, text = rig.run("accept")
    assert code == 0
    assert rig.cycle.calls == [("accept", ())]
    assert "reset-button" in text


def test_abandon_calls_the_cycle(rig: Rig) -> None:
    code, text = rig.run("abandon")
    assert code == 0
    assert rig.cycle.calls == [("abandon", ())]
    assert "reset-button" in text


def test_cycle_refusals_are_raised_not_printed(rig: Rig) -> None:
    def refuse(slug: str | None = None) -> Any:
        raise BullError("Not on a clean trunk.", "Commit or stash first.")

    rig.cycle.start = refuse  # type: ignore[method-assign]
    with pytest.raises(BullError):
        rig.run("start")
