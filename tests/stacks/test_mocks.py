"""Tests for the stacks mocks other modules' tests rely on."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.stacks.Contracts import (
    CheckItem,
    CoverageData,
    Maturity,
    Stack,
    StackError,
    StackManifest,
    StackOps,
    StackReaders,
    StackRegistry,
    TestRun,
)
from bull.Modules.stacks.mocks import (
    MockStackOps,
    MockStackReaders,
    MockStackRegistry,
    sample_manifest,
    sample_stack,
)


def _app(tmp_path: Path) -> AppLayout:
    import dataclasses

    values = {f.name: tmp_path / f.name for f in dataclasses.fields(AppLayout)}
    return AppLayout(**values)


def test_sample_manifest_is_a_manifest_with_requested_name_and_maturity() -> None:
    manifest = sample_manifest("abc", Maturity.VERIFIED)
    assert isinstance(manifest, StackManifest)
    assert manifest.name == "abc"
    assert manifest.maturity is Maturity.VERIFIED


def test_sample_manifest_defaults_to_fixture_with_test_maturity() -> None:
    manifest = sample_manifest()
    assert manifest.name == "fixture"
    assert manifest.maturity is Maturity.TEST


def test_sample_stack_wraps_a_manifest_with_default_readers() -> None:
    stack = sample_stack("zed", Maturity.EXPERIMENTAL)
    assert isinstance(stack, Stack)
    assert stack.manifest.name == "zed"
    assert stack.manifest.maturity is Maturity.EXPERIMENTAL
    assert stack.builtin is True
    assert stack.optional.detect is None


def test_mock_readers_satisfy_the_stack_readers_protocol() -> None:
    readers: StackReaders = MockStackReaders()
    assert readers.contract_declarations(Path("x"))


def test_mock_readers_report_passing_tests_full_coverage_and_ok_checks() -> None:
    readers = MockStackReaders()
    run = readers.test_results(Path("r"))
    assert isinstance(run, TestRun)
    assert run.failed == ()
    cov = readers.uncovered(Path("p"), [Path("a")], Path("r"))
    assert isinstance(cov, CoverageData)
    assert cov.uncovered == {}
    assert cov.no_data == ()
    items = readers.check(Path("p"), {}, False)
    assert items and all(isinstance(i, CheckItem) and i.ok for i in items)


def test_mock_readers_record_calls() -> None:
    readers = MockStackReaders()
    readers.test_results(Path("r"))
    readers.check(Path("p"), {}, True)
    assert [name for name, _ in readers.calls] == ["test_results", "check"]


def test_mock_registry_satisfies_protocol() -> None:
    registry: StackRegistry = MockStackRegistry()
    assert isinstance(registry.all(), list)


def test_registry_all_hides_test_maturity_by_default() -> None:
    names = [s.manifest.name for s in MockStackRegistry().all()]
    assert names == ["python_cli"]


def test_registry_all_with_include_test_lists_every_stack_sorted() -> None:
    names = [s.manifest.name for s in MockStackRegistry().all(include_test=True)]
    assert names == ["fixture", "python_cli"]


def test_registry_get_returns_the_named_stack() -> None:
    assert MockStackRegistry().get("fixture").manifest.name == "fixture"


def test_registry_get_unknown_raises_stack_error_listing_known_names() -> None:
    with pytest.raises(StackError) as info:
        MockStackRegistry().get("nope")
    message = str(info.value)
    assert "nope" in message
    assert "fixture" in message
    assert "python_cli" in message


def test_registry_load_path_returns_a_stack_named_for_the_folder() -> None:
    stack = MockStackRegistry().load_path(Path("/somewhere/mystack"))
    assert stack.manifest.name == "mystack"


def test_registry_install_makes_the_stack_available_to_get_and_all() -> None:
    registry = MockStackRegistry()
    installed = registry.install(Path("/somewhere/mystack"))
    assert registry.get("mystack") is installed
    assert "mystack" in [s.manifest.name for s in registry.all()]


def test_registry_records_calls() -> None:
    registry = MockStackRegistry()
    registry.all(True)
    registry.get("fixture")
    names = [name for name, _ in registry.calls]
    assert names == ["all", "get"]


def test_mock_ops_satisfy_protocol_and_return_passing_check_items(
    tmp_path: Path,
) -> None:
    ops: StackOps = MockStackOps()
    items = ops.check(_app(tmp_path))
    assert items and all(i.ok for i in items)


def test_ops_run_command_returns_configured_exit_code(tmp_path: Path) -> None:
    ops = MockStackOps()
    assert ops.run_command(_app(tmp_path), "prune") == 0
    ops.exit_code = 3
    assert ops.run_command(_app(tmp_path), "prune") == 3


def test_ops_rules_and_setup_guide_return_text() -> None:
    ops = MockStackOps()
    stack = sample_stack()
    assert "test-writer" in ops.rules(stack, "test-writer")
    assert ops.setup_guide(stack)
    assert ops.setup_guide(stack, "For a feature")


def test_ops_record_calls(tmp_path: Path) -> None:
    ops = MockStackOps()
    app = _app(tmp_path)
    ops.select(app, "fixture")
    ops.check(app, "app")
    assert [name for name, _ in ops.calls] == ["select", "check"]
