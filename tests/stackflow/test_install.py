"""Tests for `bull.Modules.stackflow.install` (`bull stack install`'s static check)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.stackflow.install import LiveStackInstaller, check_static
from bull.Modules.stacks.Contracts import Maturity, Stack, StackError
from bull.Modules.stacks.mocks import MockStackRegistry
from bull.Modules.stacktest.Contracts import StackTestReport
from bull.Modules.stacktest.mocks import MockStackTester


def _static_failure(*problems: str) -> StackTestReport:
    return StackTestReport("mystack", True, problems, ())


def _names(calls: list[tuple[str, tuple[object, ...]]]) -> list[str]:
    return [c[0] for c in calls]


def test_check_static_passes_silently_on_an_ok_report(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    assert check_static(tester, registry, tmp_path / "mystack") is None
    assert ("load_path", (tmp_path / "mystack",)) in registry.calls
    assert "static" in _names(tester.calls)


def test_check_static_refuses_with_every_problem_listed(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = _static_failure("rules.md missing", "cases.json invalid")
    with pytest.raises(StackError) as info:
        check_static(tester, registry, tmp_path / "mystack")
    assert "rules.md missing" in str(info.value)
    assert "cases.json invalid" in str(info.value)


def test_check_static_does_not_install(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    check_static(tester, registry, tmp_path / "mystack")
    assert "install" not in _names(registry.calls)


def test_install_runs_the_static_check_then_registry_install(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    folder = tmp_path / "mystack"
    stack = LiveStackInstaller(tester, registry).install(folder)
    assert "static" in _names(tester.calls)
    assert ("install", (folder,)) in registry.calls
    assert stack is registry.stacks["mystack"]


def test_install_keeps_the_manifest_maturity(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    stack = LiveStackInstaller(tester, registry).install(tmp_path / "mystack")
    assert stack.manifest.maturity is Maturity.EXPERIMENTAL


def test_a_failing_static_check_installs_nothing(tmp_path: Path) -> None:
    tester, registry = MockStackTester(), MockStackRegistry()
    tester.report = _static_failure("stack.toml has TODO values")
    with pytest.raises(StackError, match="TODO values"):
        LiveStackInstaller(tester, registry).install(tmp_path / "mystack")
    assert "install" not in _names(registry.calls)
    assert "mystack" not in registry.stacks


def test_a_load_error_from_the_registry_propagates(tmp_path: Path) -> None:
    class BrokenRegistry(MockStackRegistry):
        def load_path(self, path: Path) -> Stack:
            raise StackError("stack.toml is not valid")

    tester, registry = MockStackTester(), BrokenRegistry()
    with pytest.raises(StackError, match="not valid"):
        LiveStackInstaller(tester, registry).install(tmp_path / "mystack")
    assert "install" not in _names(registry.calls)
