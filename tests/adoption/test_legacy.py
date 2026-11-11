"""Tests for `bull.Modules.adoption.legacy`, reached through `LiveAdoption.legacy`.

The app's one part has root `tmp_path`, source folder `src/fx` and test folder `tests`. Memo
`App shell`, `App shell tests`, `Legacy files` and `Legacy tests` entries are paths relative to
the app root; results are sorted POSIX paths relative to the app root.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.adoption.adopt import LiveAdoption
from bull.Modules.adoption.Contracts import LegacyLeft
from bull.Modules.foundation.mocks import MockFiles, MockRunner, sample_layout
from bull.Modules.gitrepo.mocks import MockGit
from bull.Modules.memo.Contracts import LegacySection, ModuleEntry
from bull.Modules.memo.mocks import MockMemoReader, sample_memo
from bull.Modules.parts.mocks import MockParts, sample_part
from bull.Modules.settings.mocks import MockSettings
from bull.Modules.stacks.mocks import MockStackOps, MockStackRegistry
from bull.Modules.status.mocks import MockRefs, MockStatusStore


def _touch(root: Path, *relative: str) -> None:
    for rel in relative:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.layout = sample_layout(tmp_path)
        self.files = MockFiles()
        self.files.texts[self.layout.memo_file] = "# memo\n"
        self.registry = MockStackRegistry()
        self.parts = MockParts()
        self.parts.parts = [sample_part(tmp_path)]
        self.memo = MockMemoReader()
        self.memo.memo = replace(sample_memo(), legacy=None)
        store = MockStatusStore()
        self.adoption = LiveAdoption(
            files=self.files,
            git=MockGit(),
            runner=MockRunner(),
            stacks=self.registry,
            ops=MockStackOps(),
            parts=self.parts,
            memo=self.memo,
            settings=lambda app: MockSettings(),
            store=lambda app: store,
            refs=lambda app: MockRefs(),
        )

    def shell(self, files: tuple[str, ...] = (), tests: tuple[str, ...] = ()) -> None:
        self.memo.memo = replace(
            self.memo.memo,
            legacy=LegacySection(
                app_shell=files, app_shell_tests=tests, legacy_folders=(), renames={}
            ),
        )

    def module(
        self,
        name: str,
        legacy_files: tuple[str, ...] = (),
        legacy_tests: tuple[str, ...] = (),
    ) -> None:
        entries = tuple(m for m in self.memo.memo.modules if m.name != name)
        base: ModuleEntry = next(m for m in sample_memo().modules if m.name == name)
        entry = replace(base, legacy_files=legacy_files, legacy_tests=legacy_tests)
        self.memo.memo = replace(self.memo.memo, modules=(*entries, entry))

    def declarations(self, reader: Callable[[Path], list[str]] | None) -> None:
        stack = self.registry.stacks["fixture"]
        self.registry.stacks["fixture"] = replace(
            stack, optional=replace(stack.optional, legacy_declarations=reader)
        )

    def legacy(self) -> LegacyLeft:
        return self.adoption.legacy(self.layout)


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


# --- files ------------------------------------------------------------------------------------


def test_legacy_lists_source_files_outside_modules(rig: Rig) -> None:
    _touch(
        rig.root,
        "src/fx/main.fx",
        "src/fx/util/helper.fx",
        "src/fx/Modules/Counter/c.fx",
    )
    assert rig.legacy().files == ("src/fx/main.fx", "src/fx/util/helper.fx")


def test_legacy_excludes_files_named_in_the_app_shell(rig: Rig) -> None:
    _touch(rig.root, "src/fx/main.fx", "src/fx/app.fx", "src/fx/old.fx")
    rig.shell(files=("src/fx/main.fx", "src/fx/app.fx"))
    assert rig.legacy().files == ("src/fx/old.fx",)


def test_legacy_app_shell_tests_do_not_exclude_source_files(rig: Rig) -> None:
    _touch(rig.root, "src/fx/main.fx")
    rig.shell(tests=("src/fx/main.fx",))
    assert rig.legacy().files == ("src/fx/main.fx",)


def test_legacy_files_are_sorted_relative_posix_paths(rig: Rig) -> None:
    _touch(rig.root, "src/fx/z.fx", "src/fx/b/c.fx", "src/fx/a.fx", "src/fx/b/a.fx")
    files = rig.legacy().files
    assert files == ("src/fx/a.fx", "src/fx/b/a.fx", "src/fx/b/c.fx", "src/fx/z.fx")
    assert all(not Path(f).is_absolute() and "\\" not in f for f in files)


def test_legacy_ignores_pycache_folders_and_dotfiles(rig: Rig) -> None:
    _touch(
        rig.root,
        "src/fx/real.fx",
        "src/fx/__pycache__/real.cache",
        "src/fx/sub/__pycache__/x.cache",
        "src/fx/.hidden",
        "src/fx/.DS_Store",
        "tests/.DS_Store",
        "tests/__pycache__/t.cache",
    )
    left = rig.legacy()
    assert left.files == ("src/fx/real.fx",)
    assert left.tests == ()


def test_legacy_with_nothing_left_is_empty(rig: Rig) -> None:
    (rig.root / "src" / "fx").mkdir(parents=True)
    (rig.root / "tests").mkdir()
    left = rig.legacy()
    assert left == LegacyLeft((), (), (), ())
    assert left.empty


def test_legacy_with_files_left_is_not_empty(rig: Rig) -> None:
    _touch(rig.root, "src/fx/main.fx")
    assert not rig.legacy().empty


def test_legacy_ignores_files_outside_the_source_and_test_folders(rig: Rig) -> None:
    _touch(rig.root, "docs/notes.fx", "README.fx", "other/x.fx")
    left = rig.legacy()
    assert left.files == ()
    assert left.tests == ()


def test_legacy_app_shell_folder_entry_excludes_everything_under_it(rig: Rig) -> None:
    _touch(
        rig.root,
        "src/fx/shell/app.fx",
        "src/fx/shell/deep/more.fx",
        "src/fx/shellfish.fx",
        "src/fx/old.fx",
    )
    rig.shell(files=("src/fx/shell/",))
    assert rig.legacy().files == ("src/fx/old.fx", "src/fx/shellfish.fx")


def test_legacy_app_shell_folder_entry_does_not_exclude_tests(rig: Rig) -> None:
    _touch(rig.root, "tests/shell/a.test")
    rig.shell(files=("tests/shell/",))
    assert rig.legacy().tests == ("tests/shell/a.test",)


def test_legacy_app_shell_folder_entry_can_cover_the_whole_source_folder(
    rig: Rig,
) -> None:
    _touch(rig.root, "src/fx/a.fx", "src/fx/b/c.fx")
    rig.shell(files=("src/fx/",))
    assert rig.legacy().files == ()


def test_legacy_ignores_dotfiles_even_under_other_folders(rig: Rig) -> None:
    _touch(rig.root, "src/fx/sub/.keep", "src/fx/sub/real.fx", "tests/sub/.keep")
    left = rig.legacy()
    assert left.files == ("src/fx/sub/real.fx",)
    assert left.tests == ()


# --- declarations -----------------------------------------------------------------------------


def test_legacy_declarations_keep_only_names_starting_with_legacy(rig: Rig) -> None:
    rig.declarations(lambda root: ["LegacyZ", "Counter", "LegacyA", "NotLegacy"])
    assert rig.legacy().declarations == ("LegacyA", "LegacyZ")


def test_legacy_declarations_are_read_from_the_part_root(rig: Rig) -> None:
    seen: list[Path] = []

    def reader(root: Path) -> list[str]:
        seen.append(root)
        return []

    rig.declarations(reader)
    rig.legacy()
    assert seen == [rig.root]


def test_legacy_declarations_have_no_duplicates(rig: Rig) -> None:
    rig.declarations(lambda root: ["LegacyA", "LegacyB", "LegacyA"])
    assert rig.legacy().declarations == ("LegacyA", "LegacyB")


def test_legacy_declarations_are_empty_when_the_stack_has_no_reader(rig: Rig) -> None:
    rig.declarations(None)
    assert rig.legacy().declarations == ()


def test_legacy_declarations_make_the_result_not_empty(rig: Rig) -> None:
    rig.declarations(lambda root: ["LegacyThing"])
    assert not rig.legacy().empty


# --- tests ------------------------------------------------------------------------------------


def test_legacy_lists_test_files_outside_module_test_folders(rig: Rig) -> None:
    _touch(rig.root, "tests/old.test", "tests/Counter/new.test", "tests/Store/new.test")
    assert rig.legacy().tests == ("tests/old.test",)


def test_legacy_lists_nested_test_files_outside_module_folders(rig: Rig) -> None:
    _touch(rig.root, "tests/legacy/deep/a.test", "tests/Counter/deep/b.test")
    assert rig.legacy().tests == ("tests/legacy/deep/a.test",)


def test_legacy_excludes_tests_named_in_app_shell_tests(rig: Rig) -> None:
    _touch(rig.root, "tests/conftest.test", "tests/old.test")
    rig.shell(tests=("tests/conftest.test",))
    assert rig.legacy().tests == ("tests/old.test",)


def test_legacy_app_shell_tests_folder_entry_excludes_everything_under_it(
    rig: Rig,
) -> None:
    _touch(
        rig.root,
        "tests/support/helper.test",
        "tests/support/deep/more.test",
        "tests/supports.test",
        "tests/old.test",
    )
    rig.shell(tests=("tests/support/",))
    assert rig.legacy().tests == ("tests/old.test", "tests/supports.test")


def test_legacy_app_shell_tests_folder_entry_does_not_exclude_source_files(
    rig: Rig,
) -> None:
    _touch(rig.root, "src/fx/shell/a.fx")
    rig.shell(tests=("src/fx/shell/",))
    assert rig.legacy().files == ("src/fx/shell/a.fx",)


def test_legacy_app_shell_does_not_exclude_tests(rig: Rig) -> None:
    _touch(rig.root, "tests/old.test")
    rig.shell(files=("tests/old.test",))
    assert rig.legacy().tests == ("tests/old.test",)


def test_legacy_tests_are_sorted_relative_posix_paths(rig: Rig) -> None:
    _touch(rig.root, "tests/z.test", "tests/a/b.test", "tests/a.test")
    assert rig.legacy().tests == ("tests/a.test", "tests/a/b.test", "tests/z.test")


def test_legacy_a_folder_of_an_unlisted_module_still_counts_as_legacy(rig: Rig) -> None:
    _touch(rig.root, "tests/Unknown/x.test")
    assert rig.legacy().tests == ("tests/Unknown/x.test",)


# --- memo_files -------------------------------------------------------------------------------


def test_legacy_memo_files_list_existing_legacy_files_and_tests(rig: Rig) -> None:
    _touch(rig.root, "old/a.fx", "old/a.test")
    rig.module("Store", legacy_files=("old/a.fx",), legacy_tests=("old/a.test",))
    assert rig.legacy().memo_files == ("old/a.fx", "old/a.test")


def test_legacy_memo_files_skip_entries_that_no_longer_exist(rig: Rig) -> None:
    _touch(rig.root, "old/kept.fx")
    rig.module("Store", legacy_files=("old/kept.fx", "old/gone.fx"))
    assert rig.legacy().memo_files == ("old/kept.fx",)


def test_legacy_memo_files_gather_entries_from_every_module(rig: Rig) -> None:
    _touch(rig.root, "old/s.fx", "old/c.fx")
    rig.module("Store", legacy_files=("old/s.fx",))
    rig.module("Counter", legacy_files=("old/c.fx",))
    assert rig.legacy().memo_files == ("old/c.fx", "old/s.fx")


def test_legacy_memo_files_are_sorted_and_without_duplicates(rig: Rig) -> None:
    _touch(rig.root, "old/b.fx", "old/a.fx")
    rig.module("Store", legacy_files=("old/b.fx", "old/a.fx"))
    rig.module("Counter", legacy_files=("old/a.fx",))
    assert rig.legacy().memo_files == ("old/a.fx", "old/b.fx")


def test_legacy_memo_files_make_the_result_not_empty(rig: Rig) -> None:
    _touch(rig.root, "old/a.fx")
    rig.module("Store", legacy_files=("old/a.fx",))
    left = rig.legacy()
    assert not left.empty
    assert left.files == ()


# --- no memo ----------------------------------------------------------------------------------


def test_legacy_without_a_memo_file_has_no_app_shell_exclusions(rig: Rig) -> None:
    del rig.files.texts[rig.layout.memo_file]
    rig.shell(files=("src/fx/main.fx",), tests=("tests/conftest.test",))
    _touch(rig.root, "src/fx/main.fx", "tests/conftest.test")
    left = rig.legacy()
    assert left.files == ("src/fx/main.fx",)
    assert left.tests == ("tests/conftest.test",)


def test_legacy_without_a_memo_file_has_no_memo_files(rig: Rig) -> None:
    del rig.files.texts[rig.layout.memo_file]
    _touch(rig.root, "old/a.fx")
    rig.module("Store", legacy_files=("old/a.fx",))
    assert rig.legacy().memo_files == ()


def test_legacy_without_a_memo_file_still_lists_declarations(rig: Rig) -> None:
    del rig.files.texts[rig.layout.memo_file]
    rig.declarations(lambda root: ["LegacyX"])
    assert rig.legacy().declarations == ("LegacyX",)


def test_legacy_without_a_memo_legacy_section_has_no_app_shell(rig: Rig) -> None:
    _touch(rig.root, "src/fx/main.fx", "tests/old.test")
    left = rig.legacy()
    assert left.files == ("src/fx/main.fx",)
    assert left.tests == ("tests/old.test",)


def test_legacy_changes_nothing_on_disk(rig: Rig) -> None:
    _touch(rig.root, "src/fx/main.fx")
    rig.legacy()
    assert (rig.root / "src/fx/main.fx").read_text() == "x"
    assert [n for n, _ in rig.files.calls if n.startswith("write")] == []
