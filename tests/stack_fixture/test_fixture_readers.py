"""Tests for `bull.Modules.stack_fixture.fixture.readers`, written from the spec.

Choices where the spec is open: `contract_declarations(path)` reads one `.fx` file and returns the
text after `pub ` for each `pub` line; `legacy_declarations(root)` scans every `*.fx` under the
part root and returns the `Legacy<Name>` names; `uncovered` returns the source paths as passed
in; `interface_check` reads `<part_root>/<source_dir>/Modules/<module>/Contracts/*.fx`
(`source_dir` from settings, default `src`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.stack_fixture.fixture import readers
from bull.Modules.stacks.Contracts import Role

# --- contract_declarations ---------------------------------------------------------------


def test_contract_declarations_returns_pub_lines(tmp_path: Path) -> None:
    f = tmp_path / "a.fx"
    f.write_text("# comment\npub Counter\n\nprivate thing\npub func inc\n")
    assert readers.contract_declarations(f) == ["Counter", "func inc"]


def test_contract_declarations_empty_file_gives_nothing(tmp_path: Path) -> None:
    f = tmp_path / "a.fx"
    f.write_text("")
    assert readers.contract_declarations(f) == []


def test_contract_declarations_ignores_non_pub_and_field_lines(tmp_path: Path) -> None:
    f = tmp_path / "a.fx"
    f.write_text("field name: string\nhidden Foo\n")
    assert readers.contract_declarations(f) == []


# --- legacy_declarations -----------------------------------------------------------------


def test_legacy_declarations_finds_pub_legacy_names(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "old.fx").write_text(
        "pub LegacyThing\npub Modern\nother LegacyNo\n"
    )
    assert readers.legacy_declarations(tmp_path) == ["LegacyThing"]


def test_legacy_declarations_empty_when_none(tmp_path: Path) -> None:
    (tmp_path / "a.fx").write_text("pub Modern\n")
    assert readers.legacy_declarations(tmp_path) == []


# --- test_results ------------------------------------------------------------------------


def test_test_results_reads_count_and_failed(tmp_path: Path) -> None:
    (tmp_path / "tests.json").write_text(
        json.dumps({"count": 3, "failed": ["m/a::one"]})
    )
    run = readers.test_results(tmp_path)
    assert run is not None
    assert run.count == 3
    assert tuple(run.failed) == ("m/a::one",)


def test_test_results_none_when_file_missing(tmp_path: Path) -> None:
    assert readers.test_results(tmp_path) is None


def test_test_results_none_when_results_folder_missing(tmp_path: Path) -> None:
    assert readers.test_results(tmp_path / "nope") is None


# --- uncovered ---------------------------------------------------------------------------


def _coverage(results: Path, data: dict[str, list[int]]) -> None:
    results.mkdir(parents=True, exist_ok=True)
    (results / "coverage.json").write_text(json.dumps(data))


def test_uncovered_is_code_lines_minus_covered(tmp_path: Path) -> None:
    src = tmp_path / "src/Modules/m/a.fx"
    src.parent.mkdir(parents=True)
    src.write_text("# c\none\n\ntwo\nthree\nfour\n")  # code lines 2, 4, 5, 6
    results = tmp_path / "results"
    _coverage(results, {"src/Modules/m/a.fx": [2, 5]})
    data = readers.uncovered(tmp_path, [src], results)
    assert data.uncovered == {src: (4, 6)}
    assert data.no_data == ()


def test_uncovered_omits_fully_covered_file(tmp_path: Path) -> None:
    src = tmp_path / "src/a.fx"
    src.parent.mkdir()
    src.write_text("one\ntwo\n")
    results = tmp_path / "results"
    _coverage(results, {"src/a.fx": [1, 2]})
    data = readers.uncovered(tmp_path, [src], results)
    assert src not in data.uncovered
    assert data.no_data == ()


def test_uncovered_file_without_code_lines_has_no_data(tmp_path: Path) -> None:
    src = tmp_path / "src/empty.fx"
    src.parent.mkdir()
    src.write_text("# only a comment\n\n")
    results = tmp_path / "results"
    _coverage(results, {})
    data = readers.uncovered(tmp_path, [src], results)
    assert data.no_data == (src,)
    assert src not in data.uncovered


def test_uncovered_file_never_covered_lists_every_code_line(tmp_path: Path) -> None:
    src = tmp_path / "src/a.fx"
    src.parent.mkdir()
    src.write_text("one\n# c\ntwo\n")
    results = tmp_path / "results"
    _coverage(results, {"src/other.fx": [1]})
    data = readers.uncovered(tmp_path, [src], results)
    assert data.uncovered == {src: (1, 3)}


# --- check -------------------------------------------------------------------------------


@pytest.mark.parametrize("adopting", [False, True])
def test_check_passes_when_fixture_toml_present(tmp_path: Path, adopting: bool) -> None:
    (tmp_path / "fixture.toml").write_text("")
    items = readers.check(tmp_path, {}, adopting)
    assert all(i.ok for i in items)


def test_check_fails_when_fixture_toml_missing(tmp_path: Path) -> None:
    items = readers.check(tmp_path, {}, False)
    failing = [i for i in items if not i.ok]
    assert failing
    assert "fixture.toml" in failing[0].item


def test_check_reports_not_ok_flag(tmp_path: Path) -> None:
    (tmp_path / "fixture.toml").write_text("ok = false\n")
    items = readers.check(tmp_path, {}, False)
    failing = [i for i in items if not i.ok]
    assert [i.item for i in failing] == ["fixture.toml says not ok"]


def test_check_ok_true_is_not_a_failure(tmp_path: Path) -> None:
    (tmp_path / "fixture.toml").write_text("ok = true\n")
    assert all(i.ok for i in readers.check(tmp_path, {}, False))


# --- detect ------------------------------------------------------------------------------


def test_detect_confident_with_fixture_toml_and_fx_files(tmp_path: Path) -> None:
    (tmp_path / "fixture.toml").write_text("")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.fx").write_text("one\n")
    found = readers.detect(tmp_path)
    assert found.confidence == 0.9
    assert found.summary


def test_detect_not_confident_without_fx_files(tmp_path: Path) -> None:
    (tmp_path / "fixture.toml").write_text("")
    assert readers.detect(tmp_path).confidence < 0.9


def test_detect_not_confident_without_fixture_toml(tmp_path: Path) -> None:
    (tmp_path / "a.fx").write_text("one\n")
    assert readers.detect(tmp_path).confidence < 0.9


def test_detect_not_confident_in_empty_folder(tmp_path: Path) -> None:
    assert readers.detect(tmp_path).confidence < 0.9


# --- interface_check ---------------------------------------------------------------------

_SCHEMA = {
    "title": "Tally",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer"},
        "done": {"type": "boolean"},
    },
}


def _setup_interface(
    tmp_path: Path, fields: list[str], source_dir: str = "src"
) -> Path:
    contracts = tmp_path / source_dir / "Modules" / "m" / "Contracts"
    contracts.mkdir(parents=True)
    (contracts / "tally.fx").write_text("".join(f"{line}\n" for line in fields))
    schema = tmp_path / "tally.json"
    schema.write_text(json.dumps(_SCHEMA))
    return schema


_GOOD = ["field name: string", "field count: integer", "field done: boolean"]


@pytest.mark.parametrize("role", [Role.PROVIDER, Role.CONSUMER])
def test_interface_check_matching_fields_pass(tmp_path: Path, role: Role) -> None:
    schema = _setup_interface(tmp_path, _GOOD)
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", role, "m"
    )
    assert all(i.ok for i in items)


def test_interface_check_uses_source_dir_setting(tmp_path: Path) -> None:
    schema = _setup_interface(tmp_path, [*_GOOD, "field extra: string"], "lib")
    items = readers.interface_check(
        tmp_path, {"source_dir": "lib"}, schema, "json-schema", Role.PROVIDER, "m"
    )
    assert any(not i.ok for i in items)


def test_interface_check_extra_provider_field_is_reported(tmp_path: Path) -> None:
    schema = _setup_interface(tmp_path, [*_GOOD, "field x: string"])
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", Role.PROVIDER, "m"
    )
    failing = [i for i in items if not i.ok]
    assert [i.item for i in failing] == ["provider has field `x` not in the schema"]


def test_interface_check_extra_consumer_field_names_the_consumer(
    tmp_path: Path,
) -> None:
    schema = _setup_interface(tmp_path, [*_GOOD, "field x: string"])
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", Role.CONSUMER, "m"
    )
    failing = [i for i in items if not i.ok]
    assert any("consumer" in i.item and "`x`" in i.item for i in failing)


def test_interface_check_missing_field_is_reported(tmp_path: Path) -> None:
    schema = _setup_interface(tmp_path, ["field name: string", "field count: integer"])
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", Role.PROVIDER, "m"
    )
    failing = [i for i in items if not i.ok]
    assert any("done" in i.item for i in failing)


def test_interface_check_wrong_type_is_reported(tmp_path: Path) -> None:
    schema = _setup_interface(
        tmp_path, ["field name: string", "field count: string", "field done: boolean"]
    )
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", Role.PROVIDER, "m"
    )
    failing = [i for i in items if not i.ok]
    assert any("count" in i.item for i in failing)


def test_interface_check_fix_text_present_on_failures(tmp_path: Path) -> None:
    schema = _setup_interface(tmp_path, [*_GOOD, "field x: string"])
    items = readers.interface_check(
        tmp_path, {"source_dir": "src"}, schema, "json-schema", Role.PROVIDER, "m"
    )
    assert all(i.fix for i in items if not i.ok)
