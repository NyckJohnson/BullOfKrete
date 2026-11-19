"""Tests for the `fixture_service` stack folder: manifest, through the real loader.

Choices where the spec is open: the service stack's gates and `[run]` steps all invoke
`python -m bull.Modules.stack_fixture.tool <step>`; `[run]` start/ready/stop pass `{port}`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import bull.Modules.stack_fixture as pkg
from bull.Modules.stacks.Contracts import Maturity, Stack, StackKind
from bull.Modules.stacks.registry import LiveStackRegistry

_FOLDER = Path(pkg.__file__).parent / "fixture_service"
_TOOL = "bull.Modules.stack_fixture.tool"


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    registry = LiveStackRegistry([], tmp_path_factory.mktemp("userdata"))
    return registry.load_path(_FOLDER)


def _step_of(argv: tuple[str, ...]) -> str:
    assert _TOOL in argv, argv
    assert argv[argv.index(_TOOL) - 1] == "-m"
    return argv[argv.index(_TOOL) + 1]


def test_manifest_loads_with_expected_identity(stack: Stack) -> None:
    assert stack.manifest.name == "fixture_service"
    assert stack.manifest.maturity is Maturity.TEST
    assert stack.manifest.kind is StackKind.SERVICE
    assert stack.home == _FOLDER


def test_manifest_declares_json_schema_interfaces(stack: Stack) -> None:
    assert tuple(stack.manifest.interface_formats) == ("json-schema",)


def test_manifest_has_run_section_with_positive_ready_timeout(stack: Stack) -> None:
    run = stack.manifest.run
    assert run is not None
    assert run.ready_timeout > 0


@pytest.mark.parametrize("step", ["start", "ready", "stop"])
def test_run_steps_invoke_the_tool_with_the_port(stack: Stack, step: str) -> None:
    run = stack.manifest.run
    assert run is not None
    argv = tuple(getattr(run, step))
    assert _step_of(argv) == step
    assert "{port}" in argv


def test_manifest_agents_cover_required_roles(stack: Stack) -> None:
    required = {
        "skeleton-builder",
        "test-writer",
        "code-writer",
        "reviewer",
        "coverage-analyst",
    }
    assert required <= set(stack.manifest.agents)


@pytest.mark.parametrize(
    ("field", "step"),
    [
        ("preflight", "preflight"),
        ("setup", "setup"),
        ("build_test", "build-test"),
        ("build_test_fast", "build-test-fast"),
        ("lint", "lint"),
        ("rerun_failed", "rerun"),
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


def test_manifest_defines_source_and_test_dir_settings(stack: Stack) -> None:
    assert stack.manifest.settings is not None
    assert stack.manifest.source_glob
    assert stack.manifest.test_glob


def test_readers_define_every_required_function(stack: Stack) -> None:
    for fn in ("contract_declarations", "test_results", "uncovered", "check"):
        assert callable(getattr(stack.readers, fn))


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
