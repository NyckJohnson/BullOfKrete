"""Tests for the `fixture` stack folder: manifest, rules.md and setup.md, through the real loader."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import bull.Modules.stack_fixture as pkg
from bull.Modules.stacks.Contracts import Maturity, Stack, StackKind
from bull.Modules.stacks.registry import LiveStackRegistry

_FOLDER = Path(pkg.__file__).parent / "fixture"
_TOOL = "bull.Modules.stack_fixture.tool"


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    registry = LiveStackRegistry([], tmp_path_factory.mktemp("userdata"))
    return registry.load_path(_FOLDER)


def test_manifest_loads_with_expected_identity(stack: Stack) -> None:
    assert stack.manifest.name == "fixture"
    assert stack.manifest.maturity is Maturity.TEST
    assert stack.manifest.kind is StackKind.TOOL
    assert stack.home == _FOLDER


def test_manifest_has_no_run_section(stack: Stack) -> None:
    assert stack.manifest.run is None


def test_manifest_file_patterns(stack: Stack) -> None:
    assert stack.manifest.source_glob == "*.fx"
    assert "*.test" in stack.manifest.test_glob


def test_manifest_agents_cover_required_roles(stack: Stack) -> None:
    required = {
        "skeleton-builder",
        "test-writer",
        "code-writer",
        "reviewer",
        "coverage-analyst",
        "journey-test-writer",
        "surveyor",
    }
    assert required <= set(stack.manifest.agents)


def test_manifest_declares_json_schema_interfaces(stack: Stack) -> None:
    assert "json-schema" in stack.manifest.interface_formats


def test_manifest_declares_journeys(stack: Stack) -> None:
    assert stack.manifest.gates.journeys is not None


def test_manifest_defines_source_and_test_dir_settings(stack: Stack) -> None:
    assert stack.manifest.settings is not None


def _step_of(argv: tuple[str, ...]) -> str:
    assert _TOOL in argv, argv
    assert argv[argv.index(_TOOL) - 1] == "-m"
    return argv[argv.index(_TOOL) + 1]


@pytest.mark.parametrize(
    ("field", "step"),
    [
        ("preflight", "preflight"),
        ("setup", "setup"),
        ("build_test", "build-test"),
        ("build_test_fast", "build-test-fast"),
        ("lint", "lint"),
        ("rerun_failed", "rerun"),
        ("journeys", "journeys"),
    ],
)
def test_gate_steps_invoke_the_fixture_tool(
    stack: Stack, field: str, step: str
) -> None:
    argv = getattr(stack.manifest.gates, field)
    assert argv is not None
    assert _step_of(tuple(argv)) == step


def test_module_taking_steps_pass_the_module(stack: Stack) -> None:
    gates = stack.manifest.gates
    assert gates.build_test_fast[-1] == "{module}"
    assert gates.lint[-1] == "{module}"


def test_optional_readers_include_detect_legacy_and_interface_check(
    stack: Stack,
) -> None:
    assert stack.optional.detect is not None
    assert stack.optional.legacy_declarations is not None
    assert stack.optional.interface_check is not None


def test_rules_has_common_outline_and_one_section_per_agent(stack: Stack) -> None:
    text = (_FOLDER / "rules.md").read_text()
    headings = {
        m.group(1).strip().lower()
        for m in re.finditer(r"^## (.+)$", text, re.MULTILINE)
    }
    assert {"common", "outline"} <= headings
    assert set(stack.manifest.agents) <= headings


def test_setup_guide_has_feature_adoption_and_final_switch_sections() -> None:
    text = (_FOLDER / "setup.md").read_text()
    for heading in ("## For a feature", "## For an adoption", "## Final switch"):
        assert heading in text


@pytest.mark.parametrize("name", ["rules.md", "setup.md"])
def test_guide_files_are_non_empty_and_finished(name: str) -> None:
    text = (_FOLDER / name).read_text()
    assert text.strip()
    assert "placeholder" not in text.lower()
    assert "TODO" not in text


def test_readers_define_every_required_function(stack: Stack) -> None:
    for fn in ("contract_declarations", "test_results", "uncovered", "check"):
        assert callable(getattr(stack.readers, fn))
