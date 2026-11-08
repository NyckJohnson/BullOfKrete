"""Tests for `bull.Modules.stacks.registry`: finding, loading and installing stacks.

`LiveStackRegistry(builtin_roots: Sequence[Path], user_data_dir: Path)`.
"""

from __future__ import annotations

from pathlib import Path

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
