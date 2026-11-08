"""Tests for the formats mocks other modules' tests rely on.

Knobs the mock must offer (chosen here, for the code-writer):
  - `MockFormats.found: int | None`, initially equal to `current`: the `format` every
    file reports. Setting it (to 0, to 2, to None) makes `inspect` report that for all
    files, so `check` and `migrate` behave like the live ones.
  - `check`: found newer than current -> `FormatTooNew`; older or None -> `FormatTooOld`;
    equal -> returns None.
  - `migrate`: newer -> `FormatTooNew`; equal -> `[]`; older or None -> returns a copy of
    `migrated` and afterwards `found == current`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.formats.Contracts import (
    FileFormat,
    Formats,
    FormatTooNew,
    FormatTooOld,
    Migration,
)
from bull.Modules.formats.mocks import MockFormats, MockMigration
from bull.Modules.foundation.mocks import sample_layout

APP = sample_layout(Path("/tmp/apps/tally"))


def test_mock_formats_satisfies_the_protocol() -> None:
    formats: Formats = MockFormats()
    assert formats.current() == 1


def test_mock_formats_current_is_configurable() -> None:
    assert MockFormats(current=4).current() == 4


def test_mock_formats_found_defaults_to_current() -> None:
    assert MockFormats(current=3).found == 3


def test_mock_inspect_reports_every_file_at_current_by_default() -> None:
    items = MockFormats().inspect(APP)
    assert items
    assert all(isinstance(i, FileFormat) for i in items)
    assert all(i.found == 1 and i.current == 1 for i in items)
    assert {i.path for i in items} >= {
        APP.status_file,
        APP.backlog_file,
        APP.config_file,
    }


@pytest.mark.parametrize("found", [0, 2, None])
def test_mock_inspect_reports_the_configured_found_format(found: int | None) -> None:
    mock = MockFormats()
    mock.found = found
    items = mock.inspect(APP)
    assert items
    assert all(i.found == found and i.current == 1 for i in items)


def test_mock_check_passes_when_every_file_is_current() -> None:
    assert MockFormats().check(APP) is None


def test_mock_check_raises_too_new_when_files_are_newer() -> None:
    mock = MockFormats()
    mock.found = 2
    with pytest.raises(FormatTooNew):
        mock.check(APP)


@pytest.mark.parametrize("found", [0, None])
def test_mock_check_raises_too_old_when_files_are_older_or_unversioned(
    found: int | None,
) -> None:
    mock = MockFormats()
    mock.found = found
    with pytest.raises(FormatTooOld):
        mock.check(APP)


def test_mock_migrate_returns_empty_when_every_file_is_current() -> None:
    mock = MockFormats()
    mock.migrated = [APP.status_file]
    assert mock.migrate(APP) == []


def test_mock_migrate_raises_too_new_when_files_are_newer() -> None:
    mock = MockFormats()
    mock.found = 2
    with pytest.raises(FormatTooNew):
        mock.migrate(APP)


def test_mock_migrate_returns_migrated_paths_when_files_are_older() -> None:
    mock = MockFormats()
    mock.found = 0
    mock.migrated = [APP.status_file, APP.config_file]
    assert mock.migrate(APP) == [APP.status_file, APP.config_file]


def test_mock_migrate_returns_a_copy_of_migrated() -> None:
    mock = MockFormats()
    mock.found = 0
    mock.migrated = [APP.status_file]
    mock.migrate(APP).clear()
    assert mock.migrated == [APP.status_file]


def test_mock_migrate_leaves_files_current_afterwards() -> None:
    mock = MockFormats()
    mock.found = 0
    mock.migrate(APP)
    assert mock.check(APP) is None
    assert all(i.found == 1 for i in mock.inspect(APP))


def test_mock_formats_records_calls() -> None:
    mock = MockFormats()
    mock.current()
    mock.inspect(APP)
    mock.check(APP)
    mock.migrate(APP)
    assert [name for name, _ in mock.calls] == [
        "current",
        "inspect",
        "check",
        "migrate",
    ]
    assert mock.calls[1][1] == (APP,)


def test_mock_migration_satisfies_the_protocol_and_defaults_to_source_zero() -> None:
    migration: Migration = MockMigration()
    assert migration.source == 0


def test_mock_migration_source_is_configurable() -> None:
    assert MockMigration(source=3).source == 3


def test_mock_migration_apply_reports_status_json_changed() -> None:
    assert MockMigration().apply(APP) == [APP.status_file]


def test_mock_migration_records_apply_calls() -> None:
    migration = MockMigration()
    migration.apply(APP)
    assert migration.calls == [("apply", (APP,))]
