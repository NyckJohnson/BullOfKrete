"""Tests for the parts contract: the Part model and the Parts protocol."""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from bull.Modules.parts.Contracts import Part, Parts


def _part() -> Part:
    return Part(
        name="app",
        stack="fixture",
        dir=".",
        root=Path("/x"),
        source_dir=Path("src"),
        test_dir=Path("tests"),
    )


def test_part_fields_are_in_the_memo_order() -> None:
    names = [f.name for f in dataclasses.fields(Part)]
    assert names == ["name", "stack", "dir", "root", "source_dir", "test_dir"]


def test_part_keeps_the_values_it_was_built_with() -> None:
    part = _part()
    assert part.name == "app"
    assert part.stack == "fixture"
    assert part.dir == "."
    assert part.root == Path("/x")
    assert part.source_dir == Path("src")
    assert part.test_dir == Path("tests")


def test_part_is_frozen() -> None:
    part = _part()
    with pytest.raises(dataclasses.FrozenInstanceError):
        part.name = "other"  # type: ignore[misc]


def test_equal_parts_compare_equal_and_hash_alike() -> None:
    assert _part() == _part()
    assert hash(_part()) == hash(_part())


def test_parts_protocol_has_the_memo_methods() -> None:
    methods = {
        n for n, v in vars(Parts).items() if callable(v) and not n.startswith("_")
    }
    assert methods == {
        "all",
        "get",
        "add",
        "check",
        "module_src",
        "module_tests",
        "is_test_path",
    }


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("all", ["self", "app"]),
        ("get", ["self", "app", "name"]),
        ("add", ["self", "app", "name", "stack", "dir"]),
        ("check", ["self", "app"]),
        ("module_src", ["self", "part", "module"]),
        ("module_tests", ["self", "part", "module"]),
        ("is_test_path", ["self", "app", "path"]),
    ],
)
def test_parts_method_parameters_match_the_memo(method: str, params: list[str]) -> None:
    sig = inspect.signature(getattr(Parts, method))
    assert list(sig.parameters) == params


def test_get_name_defaults_to_none() -> None:
    sig = inspect.signature(Parts.get)
    assert sig.parameters["name"].default is None


def test_add_dir_defaults_to_none() -> None:
    sig = inspect.signature(Parts.add)
    assert sig.parameters["dir"].default is None
    assert sig.parameters["name"].default is inspect.Parameter.empty
    assert sig.parameters["stack"].default is inspect.Parameter.empty
