"""Tests for `bull.Modules.formats.formats` (`LiveFormats`).

Shapes chosen here (for the code-writer):
  - `LiveFormats(git: Git, migrations: Sequence[Migration] = (), current: int = 1)`;
    `current` is an override so tests need no real migration.
  - The upgrade fix is `uv tool upgrade bullofkrete` (the distribution name, Constraints).
  - Messages: "this app's files are format N; this bull reads format C: upgrade bull" and
    "this app's files are format N; run `bull migrate`", N being the one offending format.
  - `migrate` returns the migrations' changed paths in application order and commits
    with `git.commit_all(app.root, "chore: migrate bull files to format C")` only when
    something was migrated. Printing "already format C" is the cli's job.
  - A missing migration step raises `BullError` whose message contains the step's
    source number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.formats.Contracts import (
    FileFormat,
    Formats,
    FormatTooNew,
    FormatTooOld,
)
from bull.Modules.formats.formats import LiveFormats
from bull.Modules.formats.mocks import MockMigration
from bull.Modules.foundation.Contracts import AppLayout, BullError
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.gitrepo.mocks import MockGit


def make_app(
    tmp_path: Path,
    *,
    status: int | None = 1,
    backlog: int | None = 1,
    config: int | None = 1,
    parts: dict[str, int | None] | None = None,
) -> AppLayout:
    """Write the app's files; `None` in a slot writes the file without `format`."""
    app = sample_layout(tmp_path)
    app.bull_dir.mkdir(parents=True)
    for path, value in ((app.status_file, status), (app.backlog_file, backlog)):
        path.write_text(json.dumps({} if value is None else {"format": value}))
    app.config_file.write_text("" if config is None else f"format = {config}\n")
    if parts:
        app.parts_dir.mkdir()
        for name, value in parts.items():
            text = 'stack = "x"\n' if value is None else f"format = {value}\n"
            (app.parts_dir / f"{name}.toml").write_text(text)
    return app


class FileMigration:
    """A test migration: records its order and reports one file as changed."""

    def __init__(self, source: int, order: list[int], changed: list[Path]) -> None:
        self.source = source
        self.order = order
        self.changed = changed

    def apply(self, app: AppLayout) -> list[Path]:
        self.order.append(self.source)
        return list(self.changed)


def live(
    git: MockGit | None = None,
    *migrations: FileMigration | MockMigration,
    current: int = 1,
) -> LiveFormats:
    return LiveFormats(git or MockGit(), list(migrations), current)


def commits(git: MockGit) -> list[tuple[Path, str]]:
    return [args for name, args in git.calls if name == "commit_all"]  # type: ignore[misc]


def test_live_formats_satisfies_the_protocol() -> None:
    formats: Formats = LiveFormats(MockGit())
    assert formats.current() == 1


def test_constructor_defaults_to_no_migrations_and_format_one() -> None:
    assert LiveFormats(MockGit()).current() == 1


def test_current_reports_the_injected_format() -> None:
    assert live(current=3).current() == 3


# inspect


def test_inspect_reports_status_backlog_and_config(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=1, backlog=1, config=1)
    items = live().inspect(app)
    assert {i.path: i.found for i in items} == {
        app.status_file: 1,
        app.backlog_file: 1,
        app.config_file: 1,
    }
    assert all(isinstance(i, FileFormat) and i.current == 1 for i in items)


def test_inspect_reads_json_and_toml_formats(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=2, backlog=3, config=4)
    found = {i.path: i.found for i in live().inspect(app)}
    assert found[app.status_file] == 2
    assert found[app.backlog_file] == 3
    assert found[app.config_file] == 4


def test_inspect_includes_each_part_toml(tmp_path: Path) -> None:
    app = make_app(tmp_path, parts={"web": 1, "api": 2})
    found = {i.path: i.found for i in live().inspect(app)}
    assert found[app.parts_dir / "web.toml"] == 1
    assert found[app.parts_dir / "api.toml"] == 2
    assert len(found) == 5


def test_inspect_ignores_non_toml_files_in_parts(tmp_path: Path) -> None:
    app = make_app(tmp_path, parts={"web": 1})
    (app.parts_dir / "notes.txt").write_text("format = 9\n")
    paths = {i.path for i in live().inspect(app)}
    assert app.parts_dir / "notes.txt" not in paths


def test_inspect_skips_missing_files(tmp_path: Path) -> None:
    app = sample_layout(tmp_path)
    app.bull_dir.mkdir(parents=True)
    app.config_file.write_text("format = 1\n")
    assert [i.path for i in live().inspect(app)] == [app.config_file]


def test_inspect_without_a_bull_folder_returns_nothing(tmp_path: Path) -> None:
    assert live().inspect(sample_layout(tmp_path)) == []


def test_inspect_reports_none_for_a_file_without_format(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=None, config=None, parts={"web": None})
    found = {i.path: i.found for i in live().inspect(app)}
    assert found[app.status_file] is None
    assert found[app.config_file] is None
    assert found[app.parts_dir / "web.toml"] is None
    assert found[app.backlog_file] == 1


def test_inspect_current_field_uses_the_injected_current(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    assert all(i.current == 5 for i in live(current=5).inspect(app))


# check


def test_check_passes_when_every_file_is_current(tmp_path: Path) -> None:
    assert live().check(make_app(tmp_path, parts={"web": 1})) is None


def test_check_passes_for_an_app_with_no_files(tmp_path: Path) -> None:
    assert live().check(sample_layout(tmp_path)) is None


def test_check_raises_too_new_with_the_exact_message_and_fix(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=2)
    with pytest.raises(FormatTooNew) as info:
        live().check(app)
    assert info.value.message == (
        "this app's files are format 2; this bull reads format 1: upgrade bull"
    )
    assert info.value.fix == "uv tool upgrade bullofkrete"


def test_check_too_new_in_a_part_file(tmp_path: Path) -> None:
    app = make_app(tmp_path, parts={"web": 7})
    with pytest.raises(FormatTooNew) as info:
        live().check(app)
    assert "format 7" in info.value.message


def test_check_too_new_wins_over_older_files(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=2, backlog=0, config=None)
    with pytest.raises(FormatTooNew):
        live().check(app)


def test_check_raises_too_old_with_the_exact_message(tmp_path: Path) -> None:
    app = make_app(tmp_path, config=0)
    with pytest.raises(FormatTooOld) as info:
        live().check(app)
    assert info.value.message == "this app's files are format 0; run `bull migrate`"
    assert str(info.value) == info.value.message


def test_check_raises_too_old_for_a_file_without_format(tmp_path: Path) -> None:
    app = make_app(tmp_path, backlog=None)
    with pytest.raises(FormatTooOld):
        live().check(app)


def test_check_too_old_in_a_part_file(tmp_path: Path) -> None:
    app = make_app(tmp_path, parts={"web": 0})
    with pytest.raises(FormatTooOld):
        live().check(app)


def test_check_uses_the_injected_current(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    with pytest.raises(FormatTooOld) as info:
        live(current=2).check(app)
    assert info.value.message == "this app's files are format 1; run `bull migrate`"


def test_check_too_new_message_names_the_injected_current(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=5)
    with pytest.raises(FormatTooNew) as info:
        live(current=3).check(app)
    assert info.value.message == (
        "this app's files are format 5; this bull reads format 3: upgrade bull"
    )


# migrate


def test_migrate_returns_empty_when_all_files_are_current(tmp_path: Path) -> None:
    git = MockGit()
    assert live(git).migrate(make_app(tmp_path)) == []
    assert commits(git) == []


def test_migrate_does_not_run_migrations_when_all_current(tmp_path: Path) -> None:
    order: list[int] = []
    formats = live(None, FileMigration(0, order, []), current=1)
    formats.migrate(make_app(tmp_path))
    assert order == []


def test_migrate_raises_too_new_without_committing(tmp_path: Path) -> None:
    git = MockGit()
    app = make_app(tmp_path, status=2)
    with pytest.raises(FormatTooNew):
        live(git).migrate(app)
    assert commits(git) == []


def test_migrate_applies_a_migration_and_commits(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=0, backlog=0, config=0)
    git = MockGit()
    order: list[int] = []
    step = FileMigration(0, order, [app.status_file])
    result = live(git, step, current=1).migrate(app)
    assert order == [0]
    assert result == [app.status_file]
    assert commits(git) == [(app.root, "chore: migrate bull files to format 1")]


def test_migrate_applies_steps_in_order_up_to_current(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=0)
    order: list[int] = []
    steps = [
        FileMigration(2, order, [app.config_file]),
        FileMigration(0, order, [app.status_file]),
        FileMigration(1, order, [app.backlog_file]),
    ]
    git = MockGit()
    result = live(git, *steps, current=3).migrate(app)
    assert order == [0, 1, 2]
    assert result == [app.status_file, app.backlog_file, app.config_file]
    assert commits(git) == [(app.root, "chore: migrate bull files to format 3")]


def test_migrate_starts_from_the_oldest_found_format(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=2, backlog=1, config=2)
    order: list[int] = []
    steps = [FileMigration(s, order, [app.status_file]) for s in (0, 1, 2)]
    live(None, *steps, current=3).migrate(app)
    assert order == [1, 2]


def test_migrate_considers_part_files_for_the_oldest_format(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=2, backlog=2, config=2, parts={"web": 1})
    order: list[int] = []
    steps = [FileMigration(s, order, [app.status_file]) for s in (1, 2)]
    live(None, *steps, current=3).migrate(app)
    assert order == [1, 2]


def test_migrate_does_not_run_steps_at_or_above_current(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=0)
    order: list[int] = []
    steps = [FileMigration(s, order, [app.status_file]) for s in (0, 1, 2)]
    live(None, *steps, current=2).migrate(app)
    assert order == [0, 1]


def test_migrate_passes_the_app_to_each_migration(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=0)
    migration = MockMigration(source=0)
    live(None, migration, current=1).migrate(app)
    assert migration.calls == [("apply", (app,))]


def test_migrate_returns_the_paths_the_migrations_report(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=0)
    result = live(None, MockMigration(source=0), current=1).migrate(app)
    assert result == [app.status_file]


def test_migrate_a_missing_step_raises_bull_error_naming_it(tmp_path: Path) -> None:
    app = make_app(tmp_path, status=0)
    order: list[int] = []
    formats = live(None, FileMigration(0, order, [app.status_file]), current=2)
    with pytest.raises(BullError) as info:
        formats.migrate(app)
    assert "1" in info.value.message


def test_migrate_with_no_migrations_registered_raises_for_older_files(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path, status=0)
    git = MockGit()
    with pytest.raises(BullError) as info:
        live(git, current=1).migrate(app)
    assert not isinstance(info.value, (FormatTooNew, FormatTooOld))
    assert "0" in info.value.message
    assert commits(git) == []
