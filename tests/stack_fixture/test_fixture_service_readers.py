"""Tests for `bull.Modules.stack_fixture.fixture_service.readers`, written from the spec.

Choice where the spec is open: the service stack uses the same fixture-language readers as the
`fixture` stack (`*.fx` sources, `pub` contract lines, `tests.json`/`coverage.json` results,
`fixture.toml` check), so its four required readers must behave exactly as the fixture's do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.stack_fixture.fixture_service import readers
from bull.Modules.stacks.Contracts import Role


def test_contract_declarations_returns_pub_lines(tmp_path: Path) -> None:
    f = tmp_path / "a.fx"
    f.write_text("# comment\npub Counter\n\nprivate thing\npub func inc\n")
    assert readers.contract_declarations(f) == ["Counter", "func inc"]


def test_contract_declarations_empty_file_gives_nothing(tmp_path: Path) -> None:
    f = tmp_path / "a.fx"
    f.write_text("")
    assert readers.contract_declarations(f) == []


def test_test_results_reads_count_and_failed(tmp_path: Path) -> None:
    (tmp_path / "tests.json").write_text(json.dumps({"count": 3, "failed": ["m/a::x"]}))
    run = readers.test_results(tmp_path)
    assert run is not None
    assert run.count == 3
    assert run.failed == ("m/a::x",)


def test_test_results_missing_file_gives_none(tmp_path: Path) -> None:
    assert readers.test_results(tmp_path) is None


def test_uncovered_is_code_lines_minus_covered(tmp_path: Path) -> None:
    src = tmp_path / "src/a.fx"
    src.parent.mkdir()
    src.write_text("# c\none\n\ntwo\nthree\n")  # code lines 2, 4, 5
    results = tmp_path / "results"
    results.mkdir()
    (results / "coverage.json").write_text(json.dumps({"src/a.fx": [2]}))
    data = readers.uncovered(tmp_path, [src], results)
    assert data.uncovered == {src: (4, 5)}
    assert data.no_data == ()


def test_uncovered_file_without_code_lines_has_no_data(tmp_path: Path) -> None:
    src = tmp_path / "src/empty.fx"
    src.parent.mkdir()
    src.write_text("# only a comment\n")
    results = tmp_path / "results"
    results.mkdir()
    (results / "coverage.json").write_text("{}")
    data = readers.uncovered(tmp_path, [src], results)
    assert data.no_data == (src,)


@pytest.mark.parametrize("adopting", [False, True])
def test_check_passes_when_fixture_toml_present(tmp_path: Path, adopting: bool) -> None:
    (tmp_path / "fixture.toml").write_text("")
    assert all(i.ok for i in readers.check(tmp_path, {}, adopting))


def test_check_fails_when_fixture_toml_missing(tmp_path: Path) -> None:
    failing = [i for i in readers.check(tmp_path, {}, False) if not i.ok]
    assert failing
    assert "fixture.toml" in failing[0].item


def test_check_reports_not_ok_flag(tmp_path: Path) -> None:
    (tmp_path / "fixture.toml").write_text("ok = false\n")
    failing = [i for i in readers.check(tmp_path, {}, False) if not i.ok]
    assert [i.item for i in failing] == ["fixture.toml says not ok"]


# --- interface_check (same json-schema check as the fixture stack) -------------------------

_SCHEMA = {
    "title": "Tally",
    "type": "object",
    "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
}
_GOOD = ["field name: string", "field count: integer"]


def _setup_interface(tmp_path: Path, fields: list[str]) -> Path:
    contracts = tmp_path / "src" / "Modules" / "m" / "Contracts"
    contracts.mkdir(parents=True)
    (contracts / "tally.fx").write_text("".join(f"{line}\n" for line in fields))
    schema = tmp_path / "tally.json"
    schema.write_text(json.dumps(_SCHEMA))
    return schema


@pytest.mark.parametrize("role", [Role.PROVIDER, Role.CONSUMER])
def test_interface_check_matching_fields_pass(tmp_path: Path, role: Role) -> None:
    schema = _setup_interface(tmp_path, _GOOD)
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", role, "m"
    )
    assert all(i.ok for i in items)


def test_interface_check_extra_provider_field_is_reported(tmp_path: Path) -> None:
    schema = _setup_interface(tmp_path, [*_GOOD, "field x: string"])
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", Role.PROVIDER, "m"
    )
    failing = [i for i in items if not i.ok]
    assert [i.item for i in failing] == ["provider has field `x` not in the schema"]


def test_interface_check_wrong_type_is_reported(tmp_path: Path) -> None:
    schema = _setup_interface(tmp_path, ["field name: string", "field count: string"])
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", Role.CONSUMER, "m"
    )
    assert any(not i.ok and "count" in i.item for i in items)


def test_interface_check_unsupported_format_is_reported(tmp_path: Path) -> None:
    schema = _setup_interface(tmp_path, _GOOD)
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "openapi", Role.PROVIDER, "m"
    )
    assert any(i.item == "interface format `openapi` is not supported" for i in items)
