"""Tests for `bull.Modules.stacks.loader`: importing a stack folder's `readers.py`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bull.Modules.stacks.Contracts import StackError
from bull.Modules.stacks.loader import load_readers

from .stack_builder import REQUIRED_READERS, write_stack

REQUIRED = ("contract_declarations", "test_results", "uncovered", "check")


def test_required_readers_load_and_are_callable(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "ld_basic")
    readers, _ = load_readers(folder, "ld_basic")
    assert readers.contract_declarations(tmp_path) == ["decl"]
    assert readers.test_results(tmp_path) is None
    assert readers.check(tmp_path, {}, False) == []


def test_optional_readers_are_none_when_absent(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "ld_noopt")
    _, optional = load_readers(folder, "ld_noopt")
    assert optional.detect is None
    assert optional.inventory is None
    assert optional.legacy_declarations is None
    assert optional.interface_check is None


def test_optional_readers_are_picked_up_when_defined(tmp_path: Path) -> None:
    text = REQUIRED_READERS + (
        "\n\ndef detect(path):\n    return 'detected'\n"
        "\n\ndef inventory(root, settings):\n    return 'inv'\n"
        "\n\ndef legacy_declarations(path):\n    return ['legacy']\n"
        "\n\ndef interface_check(a, b, c, d, e, f):\n    return []\n"
    )
    folder = write_stack(tmp_path, "ld_allopt", readers=text)
    _, optional = load_readers(folder, "ld_allopt")
    assert optional.detect is not None
    assert optional.detect(tmp_path) == "detected"
    assert optional.inventory is not None
    assert optional.inventory(tmp_path, {}) == "inv"
    assert optional.legacy_declarations is not None
    assert optional.legacy_declarations(tmp_path) == ["legacy"]
    assert optional.interface_check is not None


def test_only_the_defined_optional_readers_are_set(tmp_path: Path) -> None:
    text = REQUIRED_READERS + "\n\ndef inventory(root, settings):\n    return 'x'\n"
    folder = write_stack(tmp_path, "ld_oneopt", readers=text)
    _, optional = load_readers(folder, "ld_oneopt")
    assert optional.inventory is not None
    assert optional.detect is None
    assert optional.legacy_declarations is None


def test_readers_import_as_package_with_sibling_import(tmp_path: Path) -> None:
    text = (
        "from __future__ import annotations\n"
        "from .helper import VALUE\n"
        "\n"
        "def contract_declarations(path):\n    return [VALUE, __name__]\n"
        "def test_results(results):\n    return None\n"
        "def uncovered(part_root, sources, results):\n    return None\n"
        "def check(part_root, settings, adopting):\n    return []\n"
    )
    folder = write_stack(
        tmp_path,
        "ld_pkg",
        readers=text,
        extra_files={"helper.py": "VALUE = 'from-sibling'\n"},
    )
    readers, _ = load_readers(folder, "ld_pkg")
    value, module_name = readers.contract_declarations(tmp_path)
    assert value == "from-sibling"
    assert module_name.startswith("bull_stack_ld_pkg")


def test_readers_package_is_registered_as_bull_stack_name(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "ld_sysmod")
    load_readers(folder, "ld_sysmod")
    assert "bull_stack_ld_sysmod" in sys.modules


@pytest.mark.parametrize("missing", REQUIRED)
def test_missing_required_function_raises_stack_error_naming_it(
    tmp_path: Path, missing: str
) -> None:
    kept: list[str] = []
    skip = False
    for line in REQUIRED_READERS.splitlines(keepends=True):
        if line.startswith("def "):
            skip = line.startswith(f"def {missing}(")
        if not skip:
            kept.append(line)
    name = f"ld_miss_{missing}"
    folder = write_stack(tmp_path, name, readers="".join(kept))
    with pytest.raises(StackError) as info:
        load_readers(folder, name)
    assert missing in info.value.message


def test_missing_readers_file_raises_stack_error(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "ld_nofile", readers=None)
    with pytest.raises(StackError):
        load_readers(folder, "ld_nofile")


def test_readers_that_fail_to_import_raise_stack_error(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "ld_broken", readers="raise RuntimeError('boom')\n")
    with pytest.raises(StackError):
        load_readers(folder, "ld_broken")
