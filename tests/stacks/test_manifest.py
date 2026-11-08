"""Tests for `bull.Modules.stacks.manifest`: parsing and validating `stack.toml`."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.stacks.Contracts import (
    Maturity,
    Requirement,
    StackError,
    StackKind,
)
from bull.Modules.stacks.manifest import parse_manifest

from .stack_builder import (
    ALL_AGENTS,
    JOURNEYS_LINE,
    RUN_SECTION,
    manifest_text,
    write_stack,
)


def _parse(tmp_path: Path, name: str, text: str):  # type: ignore[no-untyped-def]
    folder = write_stack(tmp_path, name, manifest=text)
    return parse_manifest(folder)


def _problems(tmp_path: Path, name: str, text: str) -> str:
    folder = write_stack(tmp_path, name, manifest=text)
    with pytest.raises(StackError) as info:
        parse_manifest(folder)
    return info.value.message


def test_valid_manifest_parses_scalar_fields(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    assert m.name == "sample"
    assert m.title == "Sample stack"
    assert m.description == "A sample stack for tests."
    assert m.language == "sample"
    assert m.kind is StackKind.TOOL
    assert m.maturity is Maturity.EXPERIMENTAL
    assert m.source_glob == "*.sm"
    assert m.comment == "#"


def test_valid_manifest_parses_lists(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    assert m.test_glob == ("test_*.sm", "*_test.sm")
    assert m.scaffold == ("src", "tests")
    assert m.gitignore == (".venv/",)
    assert m.agents == (
        "skeleton-builder",
        "test-writer",
        "code-writer",
        "reviewer",
        "coverage-analyst",
    )


def test_requires_become_requirements(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    assert m.requires == (Requirement("uv", "https://example.invalid/uv"),)


def test_settings_carry_source_and_test_dir_defaults(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    keys = {s.key for s in m.settings.schema}
    assert {"source_dir", "test_dir"} <= keys
    assert m.settings.values["source_dir"] == "src/sm"
    assert m.settings.values["test_dir"] == "tests"


def test_gate_commands_are_argv_tuples(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    g = m.gates
    assert g.preflight == ("{python}", "{stack_dir}/gates.py", "preflight")
    assert g.setup == ("{python}", "{stack_dir}/gates.py", "setup")
    assert g.build_test == ("{python}", "{stack_dir}/gates.py", "build-test")
    assert g.build_test_fast[-2:] == ("build-test-fast", "{module}")
    assert g.lint[-2:] == ("lint", "{module}")
    assert g.rerun_failed[-2:] == ("rerun", "{failed_ids}")


def test_journeys_absent_is_none(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    assert m.gates.journeys is None


def test_run_section_is_optional_and_defaults_to_none(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    assert m.run is None


def test_interfaces_and_commands_are_optional(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample"))
    assert m.interface_formats == ()
    assert dict(m.commands) == {}


def test_run_section_parses_when_present(tmp_path: Path) -> None:
    m = _parse(tmp_path, "sample", manifest_text("sample", append=RUN_SECTION))
    assert m.run is not None
    assert m.run.start == ("serve", "{port}")
    assert m.run.ready == ("ping", "{port}")
    assert m.run.stop == ("halt", "{port}")
    assert m.run.ready_timeout == 12


def test_interfaces_formats_parse(tmp_path: Path) -> None:
    extra = '[interfaces]\nformats = ["json-schema", "openapi"]\n'
    m = _parse(tmp_path, "sample", manifest_text("sample", append=extra))
    assert m.interface_formats == ("json-schema", "openapi")


def test_commands_parse_as_argv_tuples(tmp_path: Path) -> None:
    extra = '[commands]\nprune = ["{python}", "{stack_dir}/gates.py", "prune"]\n'
    m = _parse(tmp_path, "sample", manifest_text("sample", append=extra))
    assert dict(m.commands) == {"prune": ("{python}", "{stack_dir}/gates.py", "prune")}


def test_journeys_parse_when_given_with_journey_agent(tmp_path: Path) -> None:
    text = manifest_text(
        "sample",
        replace={'"coverage-analyst"]': '"coverage-analyst", "journey-test-writer"]'},
    ).replace('"{failed_ids}"]\n', '"{failed_ids}"]\n' + JOURNEYS_LINE, 1)
    m = _parse(tmp_path, "sample", text)
    assert m.gates.journeys == ("{python}", "{stack_dir}/gates.py", "journeys")


@pytest.mark.parametrize("maturity", ["experimental", "verified", "test"])
def test_every_maturity_value_is_accepted(tmp_path: Path, maturity: str) -> None:
    text = manifest_text(
        "sample", replace={'maturity = "experimental"': f'maturity = "{maturity}"'}
    )
    assert _parse(tmp_path, "sample", text).maturity is Maturity(maturity)


@pytest.mark.parametrize("kind", ["app", "service", "tool"])
def test_every_kind_value_is_accepted(tmp_path: Path, kind: str) -> None:
    text = manifest_text("sample", replace={'kind = "tool"': f'kind = "{kind}"'})
    assert _parse(tmp_path, "sample", text).kind is StackKind(kind)


@pytest.mark.parametrize(
    "key",
    [
        "title",
        "description",
        "language",
        "kind",
        "maturity",
        "source_glob",
        "test_glob",
        "comment",
        "agents",
    ],
)
def test_missing_required_key_raises_stack_error_naming_it(
    tmp_path: Path, key: str
) -> None:
    lines = manifest_text("sample").splitlines(keepends=True)
    first = next(i for i, ln in enumerate(lines) if ln.startswith(f"{key} ="))
    kept = lines[:first] + lines[first + 1 :]
    assert len(kept) == len(lines) - 1
    message = _problems(tmp_path, "sample", "".join(kept))
    assert key in message


def test_missing_gates_section_raises_stack_error(tmp_path: Path) -> None:
    text = manifest_text("sample")
    text = text[: text.index("[gates]")]
    assert "gates" in _problems(tmp_path, "sample", text)


def test_bad_maturity_value_raises_stack_error(tmp_path: Path) -> None:
    text = manifest_text(
        "sample", replace={'maturity = "experimental"': 'maturity = "stable"'}
    )
    message = _problems(tmp_path, "sample", text)
    assert "maturity" in message


def test_bad_kind_value_raises_stack_error(tmp_path: Path) -> None:
    text = manifest_text("sample", replace={'kind = "tool"': 'kind = "gadget"'})
    assert "kind" in _problems(tmp_path, "sample", text)


def test_todo_placeholder_raises_stack_error(tmp_path: Path) -> None:
    text = manifest_text("sample", replace={'title = "Sample stack"': 'title = "TODO"'})
    assert "TODO" in _problems(tmp_path, "sample", text)


def test_todo_placeholder_inside_a_longer_value_is_rejected(tmp_path: Path) -> None:
    text = manifest_text(
        "sample",
        replace={
            'description = "A sample stack for tests."': 'description = "TODO: write"'
        },
    )
    assert "TODO" in _problems(tmp_path, "sample", text)


@pytest.mark.parametrize("missing", ["start", "ready", "stop"])
def test_run_section_missing_a_command_raises_stack_error(
    tmp_path: Path, missing: str
) -> None:
    kept = [
        ln for ln in RUN_SECTION.splitlines(keepends=True) if not ln.startswith(missing)
    ]
    message = _problems(
        tmp_path, "sample", manifest_text("sample", append="".join(kept))
    )
    assert missing in message


def test_name_not_matching_folder_raises_stack_error(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "folder_name", manifest=manifest_text("other_name"))
    with pytest.raises(StackError) as info:
        parse_manifest(folder)
    assert "other_name" in info.value.message


@pytest.mark.parametrize("bad", ["Upper", "1abc", "has-dash", "has space", ""])
def test_invalid_name_raises_stack_error(tmp_path: Path, bad: str) -> None:
    folder = write_stack(tmp_path, "okname", manifest=manifest_text(bad))
    with pytest.raises(StackError):
        parse_manifest(folder)


def test_template_name_is_rejected(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "_template", manifest=manifest_text("_template"))
    with pytest.raises(StackError) as info:
        parse_manifest(folder)
    assert "_template" in info.value.message


@pytest.mark.parametrize("missing", ["source_dir", "test_dir"])
def test_missing_required_setting_raises_stack_error(
    tmp_path: Path, missing: str
) -> None:
    text = manifest_text("sample")
    start = text.index(f"[settings.{missing}]")
    end = text.index("[", start + 1)
    message = _problems(tmp_path, "sample", text[:start] + text[end:])
    assert missing in message


@pytest.mark.parametrize(
    "agent",
    ["skeleton-builder", "test-writer", "code-writer", "reviewer", "coverage-analyst"],
)
def test_missing_base_agent_raises_stack_error_naming_it(
    tmp_path: Path, agent: str
) -> None:
    text = manifest_text("sample")
    text = text.replace(f'"{agent}"', '"extra-agent"', 1)
    assert agent in _problems(tmp_path, "sample", text)


def test_journeys_without_journey_test_writer_raises_stack_error(
    tmp_path: Path,
) -> None:
    text = manifest_text("sample").replace(
        '"{failed_ids}"]\n', '"{failed_ids}"]\n' + JOURNEYS_LINE, 1
    )
    assert "journey-test-writer" in _problems(tmp_path, "sample", text)


def test_all_agents_listed_is_valid(tmp_path: Path) -> None:
    text = manifest_text(
        "sample",
        replace={
            'agents = ["skeleton-builder", "test-writer", "code-writer", "reviewer", "coverage-analyst"]': f"agents = {ALL_AGENTS}"
        },
    )
    assert "surveyor" in _parse(tmp_path, "sample", text).agents


def test_all_problems_are_reported_in_one_error(tmp_path: Path) -> None:
    text = manifest_text(
        "sample",
        replace={
            'maturity = "experimental"': 'maturity = "stable"',
            'kind = "tool"': 'kind = "gadget"',
            'title = "Sample stack"': 'title = "TODO"',
            '"reviewer", ': "",
        },
    )
    message = _problems(tmp_path, "sample", text)
    for fragment in ("maturity", "kind", "TODO", "reviewer"):
        assert fragment in message


def test_unparseable_toml_raises_stack_error(tmp_path: Path) -> None:
    assert _problems(tmp_path, "sample", "format = = 1\n")


def test_missing_stack_toml_raises_stack_error(tmp_path: Path) -> None:
    folder = tmp_path / "sample"
    folder.mkdir()
    with pytest.raises(StackError):
        parse_manifest(folder)


@pytest.mark.parametrize(
    "description", ["Scans for todo comments", "TODOLIST tool", "A TODOs-free stack"]
)
def test_values_merely_containing_todo_letters_are_accepted(
    tmp_path: Path, description: str
) -> None:
    text = manifest_text(
        "sample",
        replace={
            'description = "A sample stack for tests."': f'description = "{description}"'
        },
    )
    assert _parse(tmp_path, "sample", text).name == "sample"


@pytest.mark.parametrize("description", ["TODO", "TODO: describe", "Fix this TODO now"])
def test_whole_word_todo_in_a_value_is_rejected(
    tmp_path: Path, description: str
) -> None:
    text = manifest_text(
        "sample",
        replace={
            'description = "A sample stack for tests."': f'description = "{description}"'
        },
    )
    assert "TODO" in _problems(tmp_path, "sample", text)


def test_manifest_that_is_not_valid_utf8_raises_stack_error(tmp_path: Path) -> None:
    folder = write_stack(tmp_path, "sample")
    (folder / "stack.toml").write_bytes(b'format = 1\n[stack]\nname = "\xff\xfe"\n')
    with pytest.raises(StackError):
        parse_manifest(folder)


# ------------------------------------------------ coverage triage: bad manifests

_TAIL = manifest_text("sample")[
    manifest_text("sample").index("[settings.source_dir]") :
]
_REQUIRES_BLOCK = (
    '[[stack.requires]]\ntool = "uv"\nhint = "https://example.invalid/uv"\n'
)


def _bad(tmp_path: Path, text: str) -> str:
    return _problems(tmp_path, "sample", text)


def test_a_stack_toml_that_is_a_directory_raises_stack_error(tmp_path: Path) -> None:
    folder = tmp_path / "sample"
    (folder / "stack.toml").mkdir(parents=True)
    with pytest.raises(StackError):
        parse_manifest(folder)


def test_missing_format_is_reported(tmp_path: Path) -> None:
    text = manifest_text("sample", replace={"format = 1\n": ""})
    assert "format" in _bad(tmp_path, text)


@pytest.mark.parametrize("value", ["2", "true"])
def test_unsupported_format_is_reported(tmp_path: Path, value: str) -> None:
    text = manifest_text("sample", replace={"format = 1\n": f"format = {value}\n"})
    assert "format" in _bad(tmp_path, text)


def test_stack_that_is_not_a_table_is_reported(tmp_path: Path) -> None:
    assert "stack" in _bad(tmp_path, 'format = 1\nstack = "x"\n' + _TAIL)


def test_missing_stack_section_reports_the_section_not_every_key(
    tmp_path: Path,
) -> None:
    message = _bad(tmp_path, "format = 1\n" + _TAIL)
    assert "[stack]" in message
    assert "stack.title" not in message


def test_a_non_string_name_is_reported(tmp_path: Path) -> None:
    text = manifest_text("sample", replace={'name = "sample"': "name = 5"})
    assert "stack.name" in _bad(tmp_path, text)


@pytest.mark.parametrize("value", ['"x"', "[1]"])
def test_a_non_list_of_strings_argv_key_is_reported(tmp_path: Path, value: str) -> None:
    text = manifest_text(
        "sample",
        replace={
            'lint = ["{python}", "{stack_dir}/gates.py", "lint", "{module}"]': f"lint = {value}"
        },
    )
    assert "gates.lint" in _bad(tmp_path, text)


def test_a_journeys_value_that_is_not_a_list_is_reported(tmp_path: Path) -> None:
    text = manifest_text("sample", append='journeys = "x"\n')
    assert "journeys" in _bad(tmp_path, text)


def test_requires_that_is_a_string_is_reported(tmp_path: Path) -> None:
    text = manifest_text("sample", replace={_REQUIRES_BLOCK: 'requires = "x"\n'})
    assert "stack.requires" in _bad(tmp_path, text)


def test_requires_with_a_non_table_entry_is_reported(tmp_path: Path) -> None:
    text = manifest_text("sample", replace={_REQUIRES_BLOCK: 'requires = ["x"]\n'})
    assert "stack.requires" in _bad(tmp_path, text)


@pytest.mark.parametrize("missing", ["tool", "hint"])
def test_a_requires_entry_missing_tool_or_hint_is_reported(
    tmp_path: Path, missing: str
) -> None:
    other = "hint" if missing == "tool" else "tool"
    text = manifest_text(
        "sample",
        replace={_REQUIRES_BLOCK: f'[[stack.requires]]\n{other} = "v"\n'},
    )
    assert f"stack.requires[0].{missing}" in _bad(tmp_path, text)


def test_a_setting_that_is_not_a_table_is_reported(tmp_path: Path) -> None:
    text = manifest_text("sample", append="\n[settings]\nx = 3\n")
    assert "settings.x" in _bad(tmp_path, text)


def test_a_setting_with_neither_type_nor_default_is_reported(tmp_path: Path) -> None:
    text = manifest_text("sample", append='\n[settings.x]\ndescription = "d"\n')
    assert "settings.x" in _bad(tmp_path, text)


def test_a_bare_default_for_a_bull_key_is_accepted_as_a_tuple(tmp_path: Path) -> None:
    text = manifest_text(
        "sample", append='\n[settings."coverage.exclude"]\ndefault = ["a", "b"]\n'
    )
    m = _parse(tmp_path, "sample", text)
    assert m.settings.values["coverage.exclude"] == ("a", "b")
    assert "coverage.exclude" not in {s.key for s in m.settings.schema}


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("type = 5", "settings.x.type"),
        ('type = "nope"', "settings.x.type"),
        ('type = "str"\ndescription = 5', "settings.x.description"),
        ('type = "str"\nchoices = "x"', "settings.x.choices"),
        ('type = "str"\nchoices = [1]', "settings.x.choices"),
        ('type = "choice"', "settings.x.choices"),
        ('type = "int"\nminimum = "a"', "settings.x.minimum"),
        ('type = "int"\nmaximum = true', "settings.x.maximum"),
        ('type = "int"\ndefault = "x"', "settings.x.default"),
        ('type = "int"\ndefault = true', "settings.x.default"),
        ('type = "choice"\nchoices = ["a"]\ndefault = "b"', "settings.x.default"),
        ('type = "list"\ndefault = "x"', "settings.x.default"),
        ('type = "str"\ndefault = 1.5', "settings.x.default"),
    ],
)
def test_an_invalid_setting_is_reported_with_its_key(
    tmp_path: Path, body: str, key: str
) -> None:
    text = manifest_text("sample", append=f"\n[settings.x]\n{body}\n")
    assert key in _bad(tmp_path, text)


@pytest.mark.parametrize("body", ["default = 1.5", "default = { a = 1 }"])
def test_a_float_or_table_default_is_unsupported(tmp_path: Path, body: str) -> None:
    text = manifest_text("sample", append=f'\n[settings."coverage.exclude"]\n{body}\n')
    message = _bad(tmp_path, text)
    assert "unsupported" in message
    assert "coverage.exclude" in message


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('type = "bool"\ndefault = true', True),
        ('type = "int"\ndefault = 3', 3),
        ('type = "choice"\nchoices = ["a", "b"]\ndefault = "b"', "b"),
        ('type = "list"\ndefault = ["a"]', ("a",)),
    ],
)
def test_a_default_matching_its_type_is_accepted(
    tmp_path: Path, body: str, expected: object
) -> None:
    text = manifest_text("sample", append=f"\n[settings.x]\n{body}\n")
    assert _parse(tmp_path, "sample", text).settings.values["x"] == expected


@pytest.mark.parametrize("value", ["0", "-1", '"x"'])
def test_an_invalid_ready_timeout_is_reported(tmp_path: Path, value: str) -> None:
    run = RUN_SECTION.replace("ready_timeout = 12", f"ready_timeout = {value}")
    text = manifest_text("sample", append="\n" + run)
    assert "ready_timeout" in _bad(tmp_path, text)
