"""Tests for the `python_cli` stack's `stack.toml`, loaded through the stacks module's contract."""

from __future__ import annotations

from pathlib import Path

import pytest

import bull.Modules.stack_python_cli as pkg
from bull.Modules.stacks.Contracts import Maturity, Requirement, Stack, StackKind
from bull.Modules.stacks.registry import LiveStackRegistry

_FOLDER = Path(pkg.__file__).parent / "python_cli"


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    registry = LiveStackRegistry([], tmp_path_factory.mktemp("userdata"))
    return registry.load_path(_FOLDER)


def test_manifest_loads_with_expected_identity(stack: Stack) -> None:
    m = stack.manifest
    assert m.name == "python_cli"
    assert m.kind is StackKind.TOOL
    assert m.maturity is Maturity.EXPERIMENTAL
    assert m.language == "python"
    assert stack.home == _FOLDER


def test_manifest_file_patterns_and_comment_prefix(stack: Stack) -> None:
    m = stack.manifest
    assert m.source_glob == "*.py"
    assert "test_*.py" in m.test_glob
    assert "*_test.py" in m.test_glob
    assert m.comment == "#"


def test_manifest_requires_uv_with_install_hint(stack: Stack) -> None:
    reqs = stack.manifest.requires
    assert [r.tool for r in reqs] == ["uv"]
    assert isinstance(reqs[0], Requirement)
    assert reqs[0].hint.startswith("https://")


def test_manifest_agents_are_the_six_without_surveyor(stack: Stack) -> None:
    assert set(stack.manifest.agents) == {
        "skeleton-builder",
        "test-writer",
        "code-writer",
        "reviewer",
        "coverage-analyst",
        "journey-test-writer",
    }


def test_manifest_has_no_run_section(stack: Stack) -> None:
    assert stack.manifest.run is None


def test_manifest_declares_json_schema_interfaces(stack: Stack) -> None:
    assert stack.manifest.interface_formats == ("json-schema",)


def test_settings_define_source_dir_test_dir_and_package(stack: Stack) -> None:
    keys = {s.key for s in stack.manifest.settings.schema}
    assert {"source_dir", "test_dir", "package"} <= keys


def test_test_dir_defaults_to_tests(stack: Stack) -> None:
    assert stack.manifest.settings.values["test_dir"] == "tests"


def test_source_dir_default_is_under_src(stack: Stack) -> None:
    value = stack.manifest.settings.values["source_dir"]
    assert isinstance(value, str)
    assert value.startswith("src/")


def test_coverage_exclude_defaults_leave_out_mocks_and_views(stack: Stack) -> None:
    assert stack.manifest.settings.values["coverage.exclude"] == (
        "*/mocks/*",
        "*/Views/*",
    )


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
def test_every_gate_step_runs_gates_py_with_its_step_name(
    stack: Stack, field: str, step: str
) -> None:
    argv = getattr(stack.manifest.gates, field)
    assert argv is not None
    assert argv[0] == "{python}"
    assert argv[1] == "{stack_dir}/gates.py"
    assert argv[2] == step


def test_module_taking_steps_pass_the_module(stack: Stack) -> None:
    gates = stack.manifest.gates
    assert gates.build_test_fast[-1] == "{module}"
    assert gates.lint[-1] == "{module}"


def test_rerun_step_passes_the_failed_ids(stack: Stack) -> None:
    assert stack.manifest.gates.rerun_failed[-1] == "{failed_ids}"


def test_readers_define_every_required_function(stack: Stack) -> None:
    for fn in ("contract_declarations", "test_results", "uncovered", "check"):
        assert callable(getattr(stack.readers, fn))


def test_optional_readers_offer_interface_check_only(stack: Stack) -> None:
    assert stack.optional.interface_check is not None
    assert stack.optional.detect is None
    assert stack.optional.inventory is None
    assert stack.optional.legacy_declarations is None
