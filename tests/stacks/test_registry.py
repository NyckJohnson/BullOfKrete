"""Tests for `bull.Modules.stacks.registry`: finding, loading and installing stacks.

`LiveStackRegistry(builtin_roots: Sequence[Path], user_data_dir: Path)`.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.stacks.Contracts import Maturity, StackError
from bull.Modules.stacks.registry import LiveStackRegistry

from .stack_builder import REQUIRED_READERS, manifest_text, write_stack


def _registry(tmp_path: Path, *roots: Path) -> LiveStackRegistry:
    return LiveStackRegistry(list(roots), tmp_path / "userdata")


def _installed_root(tmp_path: Path) -> Path:
    return tmp_path / "userdata" / "stacks"


def _make(root: Path, name: str, maturity: str = "experimental") -> Path:
    text = manifest_text(
        name, replace={'maturity = "experimental"': f'maturity = "{maturity}"'}
    )
    return write_stack(root, name, manifest=text)


def test_all_lists_builtin_stacks_sorted_by_name(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    for name in ("rg_zeta", "rg_alpha", "rg_mid"):
        _make(root, name)
    names = [s.manifest.name for s in _registry(tmp_path, root).all()]
    assert names == ["rg_alpha", "rg_mid", "rg_zeta"]


def test_builtin_stacks_are_flagged_builtin_with_their_home(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_one")
    stack = _registry(tmp_path, root).get("rg_one")
    assert stack.builtin is True
    assert stack.home == root / "rg_one"


def test_all_merges_several_builtin_roots(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _make(a, "rg_from_a")
    _make(b, "rg_from_b")
    names = [s.manifest.name for s in _registry(tmp_path, a, b).all()]
    assert names == ["rg_from_a", "rg_from_b"]


def test_all_includes_installed_stacks_merged_and_sorted(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_b_builtin")
    _make(_installed_root(tmp_path), "rg_a_installed")
    _make(_installed_root(tmp_path), "rg_c_installed")
    stacks = _registry(tmp_path, root).all()
    assert [s.manifest.name for s in stacks] == [
        "rg_a_installed",
        "rg_b_builtin",
        "rg_c_installed",
    ]
    assert [s.builtin for s in stacks] == [False, True, False]


def test_folders_without_stack_toml_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_real")
    (root / "not_a_stack").mkdir()
    (root / "not_a_stack" / "notes.txt").write_text("x", encoding="utf-8")
    names = [s.manifest.name for s in _registry(tmp_path, root).all()]
    assert names == ["rg_real"]


def test_all_with_no_stacks_and_missing_user_dir_is_empty(tmp_path: Path) -> None:
    assert _registry(tmp_path, tmp_path / "nothing").all() == []


def test_test_maturity_is_hidden_by_default(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_visible")
    _make(root, "rg_hidden", maturity="test")
    names = [s.manifest.name for s in _registry(tmp_path, root).all()]
    assert names == ["rg_visible"]


def test_test_maturity_is_listed_with_include_test(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_visible")
    _make(root, "rg_hidden", maturity="test")
    stacks = _registry(tmp_path, root).all(include_test=True)
    assert [s.manifest.name for s in stacks] == ["rg_hidden", "rg_visible"]
    assert stacks[0].manifest.maturity is Maturity.TEST


def test_get_returns_the_named_stack_with_readers(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_get")
    stack = _registry(tmp_path, root).get("rg_get")
    assert stack.manifest.name == "rg_get"
    assert stack.readers.contract_declarations(tmp_path) == ["decl"]


def test_get_finds_test_maturity_stacks(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_hidden", maturity="test")
    assert _registry(tmp_path, root).get("rg_hidden").manifest.name == "rg_hidden"


def test_get_unknown_raises_stack_error_listing_known_names(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_known_a")
    _make(root, "rg_known_b")
    with pytest.raises(StackError) as info:
        _registry(tmp_path, root).get("rg_missing")
    assert "rg_known_a" in info.value.message
    assert "rg_known_b" in info.value.message


def test_load_path_loads_a_stack_from_any_folder(tmp_path: Path) -> None:
    folder = _make(tmp_path / "elsewhere", "rg_path")
    stack = _registry(tmp_path).load_path(folder)
    assert stack.manifest.name == "rg_path"
    assert stack.home == folder


def test_load_path_invalid_manifest_raises_stack_error(tmp_path: Path) -> None:
    folder = write_stack(
        tmp_path / "elsewhere",
        "rg_bad",
        manifest=manifest_text("rg_bad", replace={'kind = "tool"': 'kind = "x"'}),
    )
    with pytest.raises(StackError):
        _registry(tmp_path).load_path(folder)


def test_detect_reader_without_surveyor_agent_raises_stack_error(
    tmp_path: Path,
) -> None:
    readers = REQUIRED_READERS + "\n\ndef detect(path):\n    return None\n"
    folder = write_stack(tmp_path / "elsewhere", "rg_detect", readers=readers)
    with pytest.raises(StackError) as info:
        _registry(tmp_path).load_path(folder)
    assert "surveyor" in info.value.message


def test_detect_reader_with_surveyor_agent_loads(tmp_path: Path) -> None:
    readers = REQUIRED_READERS + "\n\ndef detect(path):\n    return None\n"
    text = manifest_text(
        "rg_detect_ok",
        replace={'"coverage-analyst"]': '"coverage-analyst", "surveyor"]'},
    )
    folder = write_stack(
        tmp_path / "elsewhere", "rg_detect_ok", manifest=text, readers=readers
    )
    stack = _registry(tmp_path).load_path(folder)
    assert stack.optional.detect is not None


def test_install_copies_the_folder_into_user_data_stacks(tmp_path: Path) -> None:
    src = write_stack(
        tmp_path / "src", "rg_inst", extra_files={"rules.md": "## common\nhi\n"}
    )
    stack = _registry(tmp_path).install(src)
    target = _installed_root(tmp_path) / "rg_inst"
    assert (target / "stack.toml").is_file()
    assert (target / "readers.py").is_file()
    assert (target / "rules.md").read_text(encoding="utf-8") == "## common\nhi\n"
    assert stack.home == target


def test_install_returns_the_loaded_non_builtin_stack(tmp_path: Path) -> None:
    src = _make(tmp_path / "src", "rg_ret")
    stack = _registry(tmp_path).install(src)
    assert stack.manifest.name == "rg_ret"
    assert stack.builtin is False


def test_installed_stack_is_found_by_a_registry_afterwards(tmp_path: Path) -> None:
    src = _make(tmp_path / "src", "rg_after")
    registry = _registry(tmp_path)
    registry.install(src)
    assert registry.get("rg_after").manifest.name == "rg_after"
    assert [s.manifest.name for s in registry.all()] == ["rg_after"]


def test_install_replaces_an_earlier_install_of_the_same_name(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    first = write_stack(tmp_path / "v1", "rg_repl", extra_files={"old_only.txt": "old"})
    registry.install(first)
    second = write_stack(
        tmp_path / "v2", "rg_repl", extra_files={"new_only.txt": "new"}
    )
    registry.install(second)
    target = _installed_root(tmp_path) / "rg_repl"
    assert (target / "new_only.txt").is_file()
    assert not (target / "old_only.txt").exists()


def test_install_refuses_the_name_of_a_builtin_stack(tmp_path: Path) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_taken")
    src = _make(tmp_path / "src", "rg_taken")
    with pytest.raises(StackError) as info:
        _registry(tmp_path, root).install(src)
    assert "rg_taken" in info.value.message
    assert not (_installed_root(tmp_path) / "rg_taken").exists()


def test_install_of_an_invalid_stack_raises_and_copies_nothing(
    tmp_path: Path,
) -> None:
    src = write_stack(
        tmp_path / "src",
        "rg_invalid",
        manifest=manifest_text("rg_invalid", replace={'kind = "tool"': 'kind = "x"'}),
    )
    with pytest.raises(StackError):
        _registry(tmp_path).install(src)
    assert not (_installed_root(tmp_path) / "rg_invalid").exists()


def _readers_returning(value: str, helper: bool = False) -> str:
    if helper:
        return REQUIRED_READERS.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nfrom .helper import VALUE\n",
        ).replace('return ["decl"]', "return [VALUE]")
    return REQUIRED_READERS.replace('"decl"', repr(value))


def test_failed_copy_raises_stack_error_and_leaves_no_staging_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = write_stack(tmp_path / "src", "rg_cpfail")

    def failing_copytree(source: Any, dest: Any, *args: Any, **kwargs: Any) -> None:
        Path(dest).mkdir(parents=True)
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", failing_copytree)
    with pytest.raises(StackError):
        _registry(tmp_path).install(src)
    leftovers = list(_installed_root(tmp_path).iterdir())
    assert leftovers == []


def test_failed_reinstall_keeps_the_earlier_install_intact_and_loadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry(tmp_path)
    v1 = write_stack(
        tmp_path / "v1", "rg_keep", readers=_readers_returning("version-one")
    )
    registry.install(v1)
    v2 = write_stack(
        tmp_path / "v2", "rg_keep", readers=_readers_returning("version-two")
    )

    def failing_copytree(source: Any, dest: Any, *args: Any, **kwargs: Any) -> None:
        Path(dest).mkdir(parents=True)
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", failing_copytree)
    with pytest.raises(StackError):
        registry.install(v2)
    assert [p.name for p in _installed_root(tmp_path).iterdir()] == ["rg_keep"]
    stack = registry.get("rg_keep")
    assert stack.readers.contract_declarations(tmp_path) == ["version-one"]


def test_successful_install_leaves_only_the_target_and_copies_no_pycache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    src = write_stack(
        tmp_path / "src",
        "rg_clean",
        extra_files={"notes.txt": "hello"},
    )
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "readers.cpython-311.pyc").write_bytes(b"junk")
    _registry(tmp_path).install(src)
    assert [p.name for p in _installed_root(tmp_path).iterdir()] == ["rg_clean"]
    installed = _installed_root(tmp_path) / "rg_clean"
    assert (installed / "notes.txt").read_text() == "hello"
    assert list(installed.rglob("__pycache__")) == []


@pytest.mark.parametrize("folder_name", ["_template", ".hidden"])
def test_template_and_hidden_folders_are_skipped_in_builtin_roots(
    tmp_path: Path, folder_name: str
) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_visible")
    write_stack(root, folder_name, manifest=manifest_text("rg_hidden_x"))
    registry = _registry(tmp_path, root)
    names = [s.manifest.name for s in registry.all(include_test=True)]
    assert names == ["rg_visible"]
    with pytest.raises(StackError):
        registry.get(folder_name)


@pytest.mark.parametrize("folder_name", ["_template", ".hidden"])
def test_template_and_hidden_folders_are_skipped_in_the_installed_dir(
    tmp_path: Path, folder_name: str
) -> None:
    _make(_installed_root(tmp_path), "rg_inst_visible")
    write_stack(
        _installed_root(tmp_path), folder_name, manifest=manifest_text("rg_hidden_y")
    )
    registry = _registry(tmp_path)
    names = [s.manifest.name for s in registry.all(include_test=True)]
    assert names == ["rg_inst_visible"]
    with pytest.raises(StackError):
        registry.get(folder_name)


def test_builtin_wins_over_a_hand_placed_installed_stack_of_the_same_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_dupe")
    _make(_installed_root(tmp_path), "rg_dupe")
    registry = _registry(tmp_path, root)
    assert registry.get("rg_dupe").builtin is True
    assert registry.get("rg_dupe").home == root / "rg_dupe"
    assert [s.manifest.name for s in registry.all()] == ["rg_dupe"]


def test_refused_install_of_a_builtin_name_leaves_the_builtin_loaded_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    root = tmp_path / "builtin"
    builtin_folder = write_stack(
        root,
        "rg_shadow",
        readers=_readers_returning("", helper=True),
        extra_files={"helper.py": "VALUE = 'builtin'\n"},
    )
    registry = _registry(tmp_path, root)
    assert registry.get("rg_shadow").readers.contract_declarations(tmp_path) == [
        "builtin"
    ]
    imposter = write_stack(
        tmp_path / "imposter",
        "rg_shadow",
        readers=_readers_returning("", helper=True),
        extra_files={"helper.py": "VALUE = 'imposter'\n"},
    )
    with pytest.raises(StackError):
        registry.install(imposter)

    helper = sys.modules["bull_stack_rg_shadow.helper"]
    assert Path(helper.__file__ or "").parent == builtin_folder
    assert helper.VALUE == "builtin"
    stack = registry.get("rg_shadow")
    assert stack.builtin is True
    assert stack.readers.contract_declarations(tmp_path) == ["builtin"]


# ------------------------------------------------ coverage triage: install edges


def test_install_succeeds_over_stale_staging_and_backup_folders(
    tmp_path: Path,
) -> None:
    root = _installed_root(tmp_path)
    for stale in (".rg_stale.installing", ".rg_stale.previous"):
        (root / stale).mkdir(parents=True)
        (root / stale / "junk.txt").write_text("junk", encoding="utf-8")
    src = write_stack(tmp_path / "src", "rg_stale")
    _registry(tmp_path).install(src)
    assert [p.name for p in root.iterdir()] == ["rg_stale"]


def test_install_succeeds_over_stale_folders_when_reinstalling(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.install(write_stack(tmp_path / "v1", "rg_stale2"))
    root = _installed_root(tmp_path)
    for stale in (".rg_stale2.installing", ".rg_stale2.previous"):
        (root / stale).mkdir()
    registry.install(
        write_stack(tmp_path / "v2", "rg_stale2", extra_files={"new.txt": "n"})
    )
    assert [p.name for p in root.iterdir()] == ["rg_stale2"]
    assert (root / "rg_stale2" / "new.txt").is_file()


def test_failed_final_move_on_reinstall_raises_and_keeps_the_earlier_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry(tmp_path)
    registry.install(
        write_stack(
            tmp_path / "v1", "rg_move", readers=_readers_returning("version-one")
        )
    )
    v2 = write_stack(
        tmp_path / "v2", "rg_move", readers=_readers_returning("version-two")
    )
    real_rename = Path.rename

    def rename(self: Path, target: Any) -> Path:
        if self.name == ".rg_move.installing":
            raise OSError("cannot move into place")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(StackError):
        registry.install(v2)
    monkeypatch.undo()
    assert [p.name for p in _installed_root(tmp_path).iterdir()] == ["rg_move"]
    stack = registry.get("rg_move")
    assert stack.readers.contract_declarations(tmp_path) == ["version-one"]


# ------------------------------------------------ relative stack paths


def test_load_path_dot_inside_a_stack_folder_loads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _make(tmp_path / "elsewhere", "rg_dot")
    monkeypatch.chdir(folder)
    stack = _registry(tmp_path).load_path(Path("."))
    assert stack.manifest.name == "rg_dot"


def test_load_path_relative_folder_name_from_its_parent_loads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make(tmp_path / "elsewhere", "rg_rel")
    monkeypatch.chdir(tmp_path / "elsewhere")
    stack = _registry(tmp_path).load_path(Path("rg_rel"))
    assert stack.manifest.name == "rg_rel"


def test_install_dot_inside_a_stack_folder_installs_under_the_stack_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _make(tmp_path / "src", "rg_inst_dot")
    monkeypatch.chdir(folder)
    stack = _registry(tmp_path).install(Path("."))
    assert stack.manifest.name == "rg_inst_dot"
    assert (_installed_root(tmp_path) / "rg_inst_dot" / "stack.toml").is_file()


def test_load_path_dot_still_refuses_a_name_that_does_not_match_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = write_stack(
        tmp_path / "elsewhere", "rg_folder", manifest=manifest_text("rg_other")
    )
    monkeypatch.chdir(folder)
    with pytest.raises(StackError):
        _registry(tmp_path).load_path(Path("."))


# ------------------------------------------------ BULL_EXTRA_STACKS


def test_extra_stack_folder_appears_in_all_and_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = _make(tmp_path / "extra", "rg_extra")
    monkeypatch.setenv("BULL_EXTRA_STACKS", str(extra))
    registry = _registry(tmp_path)
    assert [s.manifest.name for s in registry.all()] == ["rg_extra"]
    assert registry.get("rg_extra").home == extra


def test_several_extra_stack_folders_separated_by_pathsep_all_appear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one = _make(tmp_path / "extra", "rg_extra_one")
    two = _make(tmp_path / "extra", "rg_extra_two")
    monkeypatch.setenv("BULL_EXTRA_STACKS", os.pathsep.join([str(one), str(two)]))
    registry = _registry(tmp_path)
    assert [s.manifest.name for s in registry.all()] == [
        "rg_extra_one",
        "rg_extra_two",
    ]
    assert registry.get("rg_extra_two").home == two


def test_extra_stack_wins_over_an_installed_stack_of_the_same_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make(_installed_root(tmp_path), "rg_both")
    extra = _make(tmp_path / "extra", "rg_both")
    monkeypatch.setenv("BULL_EXTRA_STACKS", str(extra))
    registry = _registry(tmp_path)
    assert registry.get("rg_both").home == extra
    assert [s.manifest.name for s in registry.all()] == ["rg_both"]


@pytest.mark.parametrize("value", [None, ""])
def test_unset_or_empty_extra_stacks_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    root = tmp_path / "builtin"
    _make(root, "rg_only")
    if value is None:
        monkeypatch.delenv("BULL_EXTRA_STACKS", raising=False)
    else:
        monkeypatch.setenv("BULL_EXTRA_STACKS", value)
    assert [s.manifest.name for s in _registry(tmp_path, root).all()] == ["rg_only"]


def test_extra_entry_that_is_not_a_stack_folder_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = _make(tmp_path / "extra", "rg_extra_ok")
    plain = tmp_path / "plain"
    plain.mkdir()
    entries = [str(plain), str(tmp_path / "missing"), str(extra)]
    monkeypatch.setenv("BULL_EXTRA_STACKS", os.pathsep.join(entries))
    names = [s.manifest.name for s in _registry(tmp_path).all()]
    assert names == ["rg_extra_ok"]


def test_builtin_stack_wins_over_an_extra_stack_of_the_same_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builtin = _make(tmp_path / "builtin", "rg_dup")
    extra = _make(tmp_path / "extra", "rg_dup")
    monkeypatch.setenv("BULL_EXTRA_STACKS", str(extra))
    registry = _registry(tmp_path, tmp_path / "builtin")
    assert registry.get("rg_dup").home == builtin
    assert registry.get("rg_dup").builtin is True
    assert [s.manifest.name for s in registry.all()] == ["rg_dup"]


def test_extra_test_maturity_stack_is_hidden_unless_include_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = _make(tmp_path / "extra", "rg_extra_test", maturity="test")
    monkeypatch.setenv("BULL_EXTRA_STACKS", str(extra))
    registry = _registry(tmp_path)
    assert registry.all() == []
    assert [s.manifest.name for s in registry.all(include_test=True)] == [
        "rg_extra_test"
    ]


def test_extra_stacks_variable_is_read_when_all_is_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one = _make(tmp_path / "extra", "rg_late_one")
    two = _make(tmp_path / "extra", "rg_late_two")
    monkeypatch.delenv("BULL_EXTRA_STACKS", raising=False)
    registry = _registry(tmp_path)
    assert registry.all() == []
    monkeypatch.setenv("BULL_EXTRA_STACKS", str(one))
    assert [s.manifest.name for s in registry.all()] == ["rg_late_one"]
    monkeypatch.setenv("BULL_EXTRA_STACKS", str(two))
    assert [s.manifest.name for s in registry.all()] == ["rg_late_two"]
    monkeypatch.delenv("BULL_EXTRA_STACKS")
    assert registry.all() == []
