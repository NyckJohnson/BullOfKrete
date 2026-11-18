"""Tests for the python_cli stack's interface check (`readers.interface_check`, json-schema).

Choices where the spec is open: the contract file is read at
`<part_root>/<source_dir>/Modules/<module>/Contracts/__init__.py`, `source_dir` coming from the
settings; a failing item names the role by its lowercase name (`provider` / `consumer`) and the
field in the item text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.stack_python_cli.python_cli import readers
from bull.Modules.stacks.Contracts import CheckItem, Role

_SETTINGS = {"source_dir": "src/app"}

_SCHEMA: dict[str, Any] = {
    "title": "Tally",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer"},
        "ratio": {"type": "number"},
        "done": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "note": {"type": "string"},
    },
    "required": ["name", "count", "ratio", "done", "tags"],
}

_GOOD_FIELDS = [
    "name: str",
    "count: int",
    "ratio: float",
    "done: bool",
    "tags: list[str]",
    "note: str | None = None",
]


def _contract(fields: list[str], title: str = "Tally") -> str:
    body = "".join(f"    {f}\n" for f in fields) or "    pass\n"
    return (
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n\n\n"
        f"@dataclass\nclass {title}:\n{body}"
    )


def _setup(
    tmp_path: Path,
    contract_text: str | None,
    schema: dict[str, Any] | str | None = None,
    source_dir: str = "src/app",
) -> Path:
    if contract_text is not None:
        contracts = tmp_path / source_dir / "Modules" / "m" / "Contracts"
        contracts.mkdir(parents=True)
        (contracts / "__init__.py").write_text(contract_text)
    path = tmp_path / "tally.json"
    if schema is None:
        schema = _SCHEMA
    path.write_text(schema if isinstance(schema, str) else json.dumps(schema))
    return path


def _check(
    tmp_path: Path,
    schema_path: Path,
    role: Role = Role.PROVIDER,
    fmt: str = "json-schema",
    settings: dict[str, str] | None = None,
) -> list[CheckItem]:
    return readers.interface_check(
        tmp_path, settings or _SETTINGS, schema_path, fmt, role, "m"
    )


def _failing(items: list[CheckItem]) -> list[CheckItem]:
    return [i for i in items if not i.ok]


@pytest.mark.parametrize("role", [Role.PROVIDER, Role.CONSUMER])
def test_matching_dataclass_passes_for_both_roles(tmp_path: Path, role: Role) -> None:
    schema = _setup(tmp_path, _contract(_GOOD_FIELDS))
    assert _failing(_check(tmp_path, schema, role)) == []


def test_source_dir_setting_locates_the_contract(tmp_path: Path) -> None:
    schema = _setup(tmp_path, _contract(_GOOD_FIELDS), source_dir="lib/pkg")
    items = _check(tmp_path, schema, settings={"source_dir": "lib/pkg"})
    assert _failing(items) == []


@pytest.mark.parametrize("role", [Role.PROVIDER, Role.CONSUMER])
def test_missing_field_is_reported_naming_field_and_role(
    tmp_path: Path, role: Role
) -> None:
    fields = [f for f in _GOOD_FIELDS if not f.startswith("done")]
    schema = _setup(tmp_path, _contract(fields))
    failing = _failing(_check(tmp_path, schema, role))
    assert failing
    assert any(
        "done" in i.item and role.name.lower() in i.item.lower() for i in failing
    )


@pytest.mark.parametrize("role", [Role.PROVIDER, Role.CONSUMER])
def test_extra_field_is_reported_naming_field_and_role(
    tmp_path: Path, role: Role
) -> None:
    schema = _setup(
        tmp_path, _contract([*_GOOD_FIELDS[:-1], "extra: str", _GOOD_FIELDS[-1]])
    )
    failing = _failing(_check(tmp_path, schema, role))
    assert failing
    assert any(
        "extra" in i.item and role.name.lower() in i.item.lower() for i in failing
    )


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("name", "name: int"),
        ("count", "count: str"),
        ("ratio", "ratio: int"),
        ("done", "done: str"),
        ("tags", "tags: str"),
    ],
)
def test_wrong_field_type_is_reported_naming_the_field(
    tmp_path: Path, field: str, wrong: str
) -> None:
    fields = [wrong if f.startswith(f"{field}:") else f for f in _GOOD_FIELDS]
    schema = _setup(tmp_path, _contract(fields))
    failing = _failing(_check(tmp_path, schema))
    assert any(field in i.item for i in failing)


def test_required_property_declared_optional_is_reported(tmp_path: Path) -> None:
    fields = [
        "name: str | None = None" if f.startswith("name:") else f for f in _GOOD_FIELDS
    ]
    schema = _setup(tmp_path, _contract(fields))
    failing = _failing(_check(tmp_path, schema))
    assert any("name" in i.item for i in failing)


def test_non_required_property_declared_required_is_reported(tmp_path: Path) -> None:
    fields = ["note: str" if f.startswith("note:") else f for f in _GOOD_FIELDS]
    schema = _setup(tmp_path, _contract(fields))
    failing = _failing(_check(tmp_path, schema))
    assert any("note" in i.item for i in failing)


def test_all_properties_optional_when_schema_has_no_required_list(
    tmp_path: Path,
) -> None:
    schema_dict = {
        "title": "Tally",
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    schema = _setup(tmp_path, _contract(["name: str | None = None"]), schema_dict)
    assert _failing(_check(tmp_path, schema)) == []


def test_array_of_integers_matches_list_of_int(tmp_path: Path) -> None:
    schema_dict = {
        "title": "Tally",
        "type": "object",
        "properties": {"ids": {"type": "array", "items": {"type": "integer"}}},
        "required": ["ids"],
    }
    schema = _setup(tmp_path, _contract(["ids: list[int]"]), schema_dict)
    assert _failing(_check(tmp_path, schema)) == []


def test_dataclass_named_after_title_missing_is_reported(tmp_path: Path) -> None:
    schema = _setup(tmp_path, _contract(_GOOD_FIELDS, title="Other"))
    failing = _failing(_check(tmp_path, schema))
    assert failing
    assert any("Tally" in i.item for i in failing)


def test_class_that_is_not_a_dataclass_does_not_satisfy_the_check(
    tmp_path: Path,
) -> None:
    text = "class Tally:\n    name: str\n"
    schema = _setup(tmp_path, text)
    assert _failing(_check(tmp_path, schema))


def test_missing_contracts_file_gives_a_failing_item(tmp_path: Path) -> None:
    schema = _setup(tmp_path, None)
    assert _failing(_check(tmp_path, schema))


def test_empty_schema_properties_with_empty_dataclass_passes(tmp_path: Path) -> None:
    schema_dict = {"title": "Tally", "type": "object", "properties": {}}
    schema = _setup(tmp_path, _contract([]), schema_dict)
    assert _failing(_check(tmp_path, schema)) == []


def test_unsupported_format_gives_a_failing_item(tmp_path: Path) -> None:
    schema = _setup(tmp_path, _contract(_GOOD_FIELDS))
    assert _failing(_check(tmp_path, schema, fmt="protobuf"))


def test_unreadable_schema_file_gives_a_failing_item(tmp_path: Path) -> None:
    _setup(tmp_path, _contract(_GOOD_FIELDS))
    assert _failing(_check(tmp_path, tmp_path / "missing.json"))


@pytest.mark.parametrize("text", ["not json {", "[1, 2, 3]", '"just a string"', ""])
def test_invalid_schema_content_gives_a_failing_item(tmp_path: Path, text: str) -> None:
    schema = _setup(tmp_path, _contract(_GOOD_FIELDS), text)
    assert _failing(_check(tmp_path, schema))


def test_schema_without_title_gives_a_failing_item(tmp_path: Path) -> None:
    schema_dict = {"type": "object", "properties": {"name": {"type": "string"}}}
    schema = _setup(tmp_path, _contract(["name: str"]), schema_dict)
    assert _failing(_check(tmp_path, schema))


def test_contract_file_with_syntax_error_gives_a_failing_item(tmp_path: Path) -> None:
    schema = _setup(tmp_path, "class Tally(:\n")
    assert _failing(_check(tmp_path, schema))


def test_every_returned_item_has_text_and_fix_for_failures(tmp_path: Path) -> None:
    schema = _setup(tmp_path, _contract(["name: int"]))
    for item in _failing(_check(tmp_path, schema)):
        assert item.item


# --- coverage triage: unsupported types, decorators, annotation shapes --------------------


def _one(
    tmp_path: Path,
    props: dict[str, Any],
    required: list[str],
    fields: list[str],
    decorator: str = "@dataclass",
    imports: str = "from dataclasses import dataclass\nimport dataclasses\n"
    "from typing import ClassVar, Optional, Union\n",
) -> list[CheckItem]:
    body = "".join(f"    {f}\n" for f in fields) or "    pass\n"
    text = f"from __future__ import annotations\n{imports}\n\n{decorator}\nclass T:\n{body}"
    schema = _setup(
        tmp_path,
        text,
        {"title": "T", "type": "object", "properties": props, "required": required},
    )
    return _check(tmp_path, schema)


@pytest.mark.parametrize(
    ("spec", "shown"),
    [
        ({"type": "object"}, "object"),
        ({"type": "null"}, "null"),
        (5, "no type"),
    ],
)
def test_unsupported_property_type_is_reported_naming_the_field(
    tmp_path: Path, spec: Any, shown: str
) -> None:
    items = _one(tmp_path, {"a": spec}, ["a"], ["a: int"])
    failing = _failing(items)
    assert len(failing) == 1
    assert "`a`" in failing[0].item
    assert f"unsupported type ({shown})" in failing[0].item


def test_property_without_a_type_is_reported_as_no_type(tmp_path: Path) -> None:
    failing = _failing(_one(tmp_path, {"a": {}}, ["a"], ["a: int"]))
    assert any("a" in i.item and "no type" in i.item for i in failing)


def test_array_of_an_unsupported_item_type_is_unsupported(tmp_path: Path) -> None:
    failing = _failing(
        _one(
            tmp_path,
            {"a": {"type": "array", "items": {"type": "object"}}},
            ["a"],
            ["a: list"],
        )
    )
    assert any("unsupported type" in i.item and "`a`" in i.item for i in failing)


def test_array_without_items_matches_a_plain_list_field(tmp_path: Path) -> None:
    items = _one(tmp_path, {"a": {"type": "array"}}, ["a"], ["a: list"])
    assert _failing(items) == []


def test_properties_that_is_not_an_object_is_a_bad_input_item(tmp_path: Path) -> None:
    schema = _setup(
        tmp_path,
        _contract([]),
        '{"title": "Tally", "properties": [1, 2]}',
    )
    items = _check(tmp_path, schema)
    assert len(items) == 1
    assert items[0].ok is False
    assert "properties" in items[0].item


@pytest.mark.parametrize(
    "decorator",
    ["@dataclass(frozen=True)", "@dataclasses.dataclass", "@dataclasses.dataclass()"],
)
def test_dataclass_decorator_forms_are_recognised(
    tmp_path: Path, decorator: str
) -> None:
    items = _one(tmp_path, {"a": {"type": "integer"}}, ["a"], ["a: int"], decorator)
    assert _failing(items) == []


def test_a_class_without_a_dataclass_decorator_fails(tmp_path: Path) -> None:
    items = _one(
        tmp_path, {"a": {"type": "integer"}}, ["a"], ["a: int"], "@something_else"
    )
    assert _failing(items)
    assert any("dataclass" in i.item for i in _failing(items))


def test_a_string_annotation_is_read_as_its_type(tmp_path: Path) -> None:
    assert (
        _failing(_one(tmp_path, {"a": {"type": "integer"}}, ["a"], ['a: "int"'])) == []
    )


def test_an_unparsable_string_annotation_is_a_mismatch_naming_the_field(
    tmp_path: Path,
) -> None:
    failing = _failing(_one(tmp_path, {"a": {"type": "integer"}}, ["a"], ['a: "in t"']))
    assert len(failing) == 1
    assert "`a`" in failing[0].item


@pytest.mark.parametrize(
    "annotation", ["Union[int, None]", "Optional[int]", "Union[None, int]"]
)
def test_union_and_optional_forms_are_accepted_for_a_non_required_field(
    tmp_path: Path,
    annotation: str,
) -> None:
    items = _one(tmp_path, {"a": {"type": "integer"}}, [], [f"a: {annotation} = None"])
    assert _failing(items) == []


def test_optional_annotation_on_a_required_field_is_a_mismatch(tmp_path: Path) -> None:
    failing = _failing(
        _one(tmp_path, {"a": {"type": "integer"}}, ["a"], ["a: Optional[int]"])
    )
    assert len(failing) == 1
    assert "`a`" in failing[0].item


@pytest.mark.parametrize(
    "annotation", ["dict[str, int]", "int | str", "Union[int, str]"]
)
def test_an_annotation_the_schema_cannot_express_is_a_mismatch(
    tmp_path: Path,
    annotation: str,
) -> None:
    failing = _failing(
        _one(tmp_path, {"a": {"type": "integer"}}, ["a"], [f"a: {annotation}"])
    )
    assert len(failing) == 1
    assert "`a`" in failing[0].item


def test_classvar_fields_are_ignored(tmp_path: Path) -> None:
    items = _one(
        tmp_path,
        {"a": {"type": "integer"}},
        ["a"],
        ["a: int", "kind: ClassVar[str] = 'x'", "other: ClassVar = 1"],
    )
    assert _failing(items) == []
