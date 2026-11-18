"""Tests for the `ios` stack's `stack.toml`, loaded through the stacks module's contract."""

from __future__ import annotations

from pathlib import Path

import pytest

import bull.Modules.stack_ios as pkg
from bull.Modules.stacks.Contracts import Maturity, Requirement, Stack, StackKind
from bull.Modules.stacks.registry import LiveStackRegistry

_FOLDER = Path(pkg.__file__).parent / "ios"


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    registry = LiveStackRegistry([], tmp_path_factory.mktemp("userdata"))
    return registry.load_path(_FOLDER)


def test_manifest_loads_with_expected_identity(stack: Stack) -> None:
    m = stack.manifest
    assert m.name == "ios"
    assert m.kind is StackKind.APP
    assert m.maturity is Maturity.EXPERIMENTAL
    assert m.language == "swift"
    assert m.title
    assert m.description
    assert stack.home == _FOLDER


def test_manifest_file_patterns_and_comment_prefix(stack: Stack) -> None:
    m = stack.manifest
    assert m.source_glob == "*.swift"
    assert tuple(m.test_glob) == ("*Tests.swift",)
    assert m.comment == "//"


def test_manifest_scaffold_and_gitignore(stack: Stack) -> None:
    m = stack.manifest
    assert tuple(m.scaffold) == ("App",)
    assert tuple(m.gitignore) == ("xcuserdata/", "*.xcuserstate", ".DS_Store")


def test_manifest_agents_are_the_eight_including_surveyor_and_screen_builder(
    stack: Stack,
) -> None:
    assert set(stack.manifest.agents) == {
        "skeleton-builder",
        "screen-builder",
        "test-writer",
        "code-writer",
        "reviewer",
        "coverage-analyst",
        "journey-test-writer",
        "surveyor",
    }
    assert len(stack.manifest.agents) == 8


def test_manifest_requires_xcodebuild_then_swiftlint_with_hints(stack: Stack) -> None:
    reqs = stack.manifest.requires
    assert [r.tool for r in reqs] == ["xcodebuild", "swiftlint"]
    assert all(isinstance(r, Requirement) for r in reqs)
    assert "Xcode" in reqs[0].hint
    assert "xcode-select" in reqs[0].hint
    assert "brew install swiftlint" in reqs[1].hint


def test_manifest_has_no_run_section(stack: Stack) -> None:
    assert stack.manifest.run is None


def test_manifest_has_no_interface_formats(stack: Stack) -> None:
    assert tuple(stack.manifest.interface_formats) == ()


def test_manifest_has_a_prune_command(stack: Stack) -> None:
    assert tuple(stack.manifest.commands["prune"]) == (
        "{python}",
        "{stack_dir}/gates.py",
        "prune",
    )


_SETTING_DEFAULTS = {
    "project": "App/MyApp/MyApp.xcodeproj",
    "scheme": "MyApp",
    "source_dir": "App/MyApp/MyApp",
    "test_dir": "App/MyApp/MyAppTests",
    "ui_test_dir": "App/MyApp/MyAppUITests",
    "unit_test_target": "MyAppTests",
    "ui_test_target": "MyAppUITests",
    "simulator": "",
}


@pytest.mark.parametrize(("key", "default"), sorted(_SETTING_DEFAULTS.items()))
def test_setting_exists_with_its_default(stack: Stack, key: str, default: str) -> None:
    keys = {s.key for s in stack.manifest.settings.schema}
    assert key in keys
    assert stack.manifest.settings.values[key] == default


def test_coverage_exclude_defaults_leave_out_views_and_mocks(stack: Stack) -> None:
    assert tuple(stack.manifest.settings.values["coverage.exclude"]) == (
        "*/Views/*",
        "*/Mocks/*",
    )


def test_every_setting_has_a_description(stack: Stack) -> None:
    schema = stack.manifest.settings.schema
    assert schema
    for setting in schema:
        assert setting.description.strip(), setting.key


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


def test_journeys_gate_is_set(stack: Stack) -> None:
    assert stack.manifest.gates.journeys is not None


def test_readers_define_every_required_function(stack: Stack) -> None:
    for fn in ("contract_declarations", "test_results", "uncovered", "check"):
        assert callable(getattr(stack.readers, fn))


def test_optional_readers_offer_detect_inventory_and_legacy_declarations_only(
    stack: Stack,
) -> None:
    assert stack.optional.detect is not None
    assert stack.optional.inventory is not None
    assert stack.optional.legacy_declarations is not None
    assert stack.optional.interface_check is None
