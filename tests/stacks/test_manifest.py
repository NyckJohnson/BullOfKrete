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
    kept = [ln for ln in lines if not ln.startswith(f"{key} =")]
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
    text = manifest_text(
        "sample", replace={'title = "Sample stack"': 'title = "TODO"'}
    )
    assert "TODO" in _problems(tmp_path, "sample", text)


def test_todo_placeholder_inside_a_longer_value_is_rejected(tmp_path: Path) -> None:
    text = manifest_text(
        "sample",
        replace={'description = "A sample stack for tests."': 'description = "TODO: write"'},
    )
    assert "TODO" in _problems(tmp_path, "sample", text)


@pytest.mark.parametrize("missing", ["start", "ready", "stop"])
def test_run_section_missing_a_command_raises_stack_error(
    tmp_path: Path, missing: str
) -> None:
    kept = [
        ln for ln in RUN_SECTION.splitlines(keepends=True) if not ln.startswith(missing)
    ]
    message = _problems(tmp_path, "sample", manifest_text("sample", append="".join(kept)))
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
