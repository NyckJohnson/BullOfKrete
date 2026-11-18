"""Error-handling and edge-case tests for `bull.Modules.stack_fixture.fixture.readers`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.stack_fixture.fixture import readers
from bull.Modules.stacks.Contracts import Role

# --- test_results ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        "",
        "[1, 2]",
        '"string"',
        "42",
        "null",
        '{"count": "3", "failed": []}',
        '{"count": 3, "failed": "x"}',
        '{"count": 3}',
        '{"failed": []}',
        "{}",
    ],
)
def test_test_results_unusable_file_gives_none(tmp_path: Path, text: str) -> None:
    (tmp_path / "tests.json").write_text(text)
    assert readers.test_results(tmp_path) is None


def test_test_results_stringifies_failed_entries(tmp_path: Path) -> None:
    (tmp_path / "tests.json").write_text(json.dumps({"count": 2, "failed": ["a", 7]}))
    run = readers.test_results(tmp_path)
    assert run is not None
    assert run.count == 2
    assert run.failed == ("a", "7")


# --- uncovered ---------------------------------------------------------------------------


def _source(root: Path, rel: str = "a.fx") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# c\npub A\n\npub B\n")  # code lines 2 and 4
    return path


def test_uncovered_without_coverage_json_every_code_line_is_uncovered(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    src = _source(tmp_path)
    data = readers.uncovered(tmp_path, [src], results)
    assert data.uncovered == {src: (2, 4)}


@pytest.mark.parametrize("text", ["not json", "", "[1, 2]", '"x"', "7"])
def test_uncovered_with_unusable_coverage_json_every_code_line_is_uncovered(
    tmp_path: Path, text: str
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "coverage.json").write_text(text)
    src = _source(tmp_path)
    data = readers.uncovered(tmp_path, [src], results)
    assert data.uncovered == {src: (2, 4)}


def test_uncovered_ignores_malformed_coverage_entries(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "coverage.json").write_text(
        json.dumps({"a.fx": [2, "x", None], "b.fx": "nope"})
    )
    src = _source(tmp_path)
    data = readers.uncovered(tmp_path, [src], results)
    assert data.uncovered == {src: (4,)}


def test_uncovered_source_outside_part_root_is_keyed_by_absolute_posix_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "elsewhere"
    results = tmp_path / "results"
    results.mkdir()
    src = _source(outside, "o.fx")
    (results / "coverage.json").write_text(json.dumps({src.as_posix(): [2, 4]}))
    data = readers.uncovered(root, [src], results)
    assert data.uncovered == {}
    assert data.no_data == ()


def test_uncovered_source_outside_part_root_not_in_coverage_is_uncovered(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    results = tmp_path / "results"
    results.mkdir()
    src = _source(tmp_path / "elsewhere", "o.fx")
    data = readers.uncovered(root, [src], results)
    assert data.uncovered == {src: (2, 4)}


# --- check -------------------------------------------------------------------------------


def test_check_invalid_toml_gives_failing_valid_toml_item(tmp_path: Path) -> None:
    (tmp_path / "fixture.toml").write_text("this = = broken [\n")
    items = readers.check(tmp_path, {}, False)
    failing = [i for i in items if not i.ok]
    assert [i.item for i in failing] == ["fixture.toml is valid TOML"]
    assert failing[0].fix
    assert any(i.ok and i.item.startswith("fixture.toml present") for i in items)


# --- interface_check ---------------------------------------------------------------------


def _schema(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "s.json"
    path.write_text(text)
    return path


def _contracts(tmp_path: Path, body: str, name: str = "t.fx") -> None:
    folder = tmp_path / "src" / "Modules" / "m" / "Contracts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(body)


def _check(tmp_path: Path, schema: Path, fmt: str = "json-schema") -> list[str]:
    items = readers.interface_check(tmp_path, {}, schema, fmt, Role.PROVIDER, "m")
    return [i.item for i in items if not i.ok]


def test_interface_check_missing_schema_file_fails_with_fix_text(
    tmp_path: Path,
) -> None:
    items = readers.interface_check(
        tmp_path, {}, tmp_path / "nope.json", "json-schema", Role.PROVIDER, "m"
    )
    assert len(items) == 1
    assert not items[0].ok
    assert "nope.json" in items[0].item
    assert items[0].fix == "fix the interface file"


def test_interface_check_non_json_schema_fails_with_fix_text(tmp_path: Path) -> None:
    items = readers.interface_check(
        tmp_path,
        {},
        _schema(tmp_path, "{not json"),
        "json-schema",
        Role.CONSUMER,
        "m",
    )
    assert [i.ok for i in items] == [False]
    assert items[0].fix == "fix the interface file"


@pytest.mark.parametrize("text", ["{}", '{"properties": []}', "[1]", '"x"'])
def test_interface_check_schema_without_properties_fails(
    tmp_path: Path, text: str
) -> None:
    items = readers.interface_check(
        tmp_path, {}, _schema(tmp_path, text), "json-schema", Role.PROVIDER, "m"
    )
    assert [i.ok for i in items] == [False]
    assert "properties" in items[0].item
    assert items[0].fix == "fix the interface file"


def test_interface_check_unsupported_format_fails(tmp_path: Path) -> None:
    schema = _schema(tmp_path, '{"properties": {}}')
    items = readers.interface_check(tmp_path, {}, schema, "openapi", Role.PROVIDER, "m")
    assert [i.item for i in items] == ["interface format `openapi` is not supported"]
    assert not items[0].ok


def test_interface_check_unsupported_field_type_is_reported(tmp_path: Path) -> None:
    schema = _schema(tmp_path, '{"properties": {"x": {"type": "array"}}}')
    _contracts(tmp_path, "field x: array\n")
    failing = _check(tmp_path, schema)
    assert len(failing) == 1
    assert "unsupported type" in failing[0]
    assert "`x`" in failing[0]


def test_interface_check_property_without_type_is_unsupported(tmp_path: Path) -> None:
    schema = _schema(tmp_path, '{"properties": {"x": {}, "y": 5}}')
    _contracts(tmp_path, "field x: string\nfield y: string\n")
    failing = _check(tmp_path, schema)
    assert len(failing) == 2
    assert all("unsupported type" in f for f in failing)


def test_interface_check_module_without_contracts_folder_lacks_every_field(
    tmp_path: Path,
) -> None:
    schema = _schema(
        tmp_path,
        '{"properties": {"a": {"type": "string"}, "b": {"type": "integer"}}}',
    )
    failing = _check(tmp_path, schema)
    assert failing == [
        "provider lacks field `a` from the schema",
        "provider lacks field `b` from the schema",
    ]


def test_interface_check_ignores_non_field_lines_in_contracts(tmp_path: Path) -> None:
    schema = _schema(tmp_path, '{"properties": {"a": {"type": "string"}}}')
    _contracts(
        tmp_path,
        "# comment\npub Thing\nother stuff\nfield a: string\nfield : string\n",
    )
    items = readers.interface_check(
        tmp_path, {}, schema, "json-schema", Role.PROVIDER, "m"
    )
    assert [i.ok for i in items] == [True]


def test_interface_check_reads_every_fx_file_in_contracts(tmp_path: Path) -> None:
    schema = _schema(
        tmp_path,
        '{"properties": {"a": {"type": "string"}, "b": {"type": "boolean"}}}',
    )
    _contracts(tmp_path, "field a: string\n", "one.fx")
    _contracts(tmp_path, "field b: boolean\n", "two.fx")
    assert _check(tmp_path, schema) == []
