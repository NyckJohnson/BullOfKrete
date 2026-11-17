"""Tests for `bull.Modules.appinit.doctor` (spec: appinit Behavior spec, `Doctor.run`).

Construction assumed: `LiveDoctor(runner=, registry=, provider=, python_version=)`.
"""

from __future__ import annotations

from dataclasses import replace

from bull.Modules.appinit.doctor import LiveDoctor
from bull.Modules.claude_code.mocks import MockProvider
from bull.Modules.foundation.mocks import MockRunner
from bull.Modules.stacks.Contracts import CheckItem, Requirement, Stack
from bull.Modules.stacks.mocks import MockStackRegistry


def _doctor(
    runner: MockRunner | None = None,
    registry: MockStackRegistry | None = None,
    provider: MockProvider | None = None,
    python_version: tuple[int, int, int] = (3, 12, 4),
) -> LiveDoctor:
    return LiveDoctor(
        runner=runner or MockRunner(),
        registry=registry or MockStackRegistry(),
        provider=provider or MockProvider(),
        python_version=python_version,
    )


def _find(items: tuple[CheckItem, ...], word: str) -> CheckItem:
    matches = [i for i in items if word in i.item.lower()]
    assert len(matches) == 1, [i.item for i in items]
    return matches[0]


def _with_requires(registry: MockStackRegistry, name: str, tools: list[str]) -> None:
    stack = registry.stacks[name]
    manifest = replace(
        stack.manifest,
        requires=tuple(
            Requirement(t, f"install {t}: https://example.com/{t}") for t in tools
        ),
    )
    registry.stacks[name] = Stack(
        manifest=manifest,
        home=stack.home,
        builtin=stack.builtin,
        readers=stack.readers,
        optional=stack.optional,
    )


def test_run_reports_four_core_items_for_python_uv_git_and_the_provider() -> None:
    report = _doctor().run()
    assert len(report.items) == 4
    for word in ("python", "uv", "git"):
        _find(report.items, word)


def test_run_is_ok_when_every_tool_is_present() -> None:
    report = _doctor().run()
    assert report.ok is True
    assert all(item.ok for item in report.items)


def test_run_includes_the_providers_tool_check_item() -> None:
    provider = MockProvider()
    report = _doctor(provider=provider).run()
    assert CheckItem(True, "claude 2.1.0 (Claude Code)", "") in report.items
    assert ("tool_check", ()) in provider.calls


def test_run_fails_when_the_provider_tool_is_missing() -> None:
    class MissingProvider(MockProvider):
        def tool_check(self) -> CheckItem:
            return CheckItem(False, "claude not found", "install Claude Code")

    report = _doctor(provider=MissingProvider()).run()
    assert report.ok is False
    assert CheckItem(False, "claude not found", "install Claude Code") in report.items


def test_python_older_than_3_11_fails_with_a_fix() -> None:
    report = _doctor(python_version=(3, 10, 14)).run()
    item = _find(report.items, "python")
    assert item.ok is False
    assert item.fix != ""
    assert report.ok is False


def test_python_3_11_passes() -> None:
    report = _doctor(python_version=(3, 11, 0)).run()
    assert _find(report.items, "python").ok is True


def test_python_newer_than_3_11_passes() -> None:
    report = _doctor(python_version=(3, 13, 1)).run()
    assert _find(report.items, "python").ok is True


def test_missing_uv_fails_with_a_fix() -> None:
    runner = MockRunner()
    del runner.tools["uv"]
    report = _doctor(runner=runner).run()
    item = _find(report.items, "uv")
    assert item.ok is False
    assert item.fix != ""
    assert report.ok is False


def test_missing_git_fails_with_a_fix() -> None:
    runner = MockRunner()
    del runner.tools["git"]
    report = _doctor(runner=runner).run()
    item = _find(report.items, "git")
    assert item.ok is False
    assert item.fix != ""
    assert report.ok is False


def test_stacks_lists_every_non_test_stack_and_skips_test_stacks() -> None:
    registry = MockStackRegistry()
    report = _doctor(registry=registry).run()
    assert [name for name, _ in report.stacks] == ["python_cli"]
    assert ("all", (False,)) in registry.calls


def test_each_stack_has_one_item_per_required_tool() -> None:
    registry = MockStackRegistry()
    _with_requires(registry, "python_cli", ["git", "uv"])
    report = _doctor(registry=registry).run()
    items = dict(report.stacks)["python_cli"]
    assert len(items) == 2
    assert [("git" in i.item.lower(), "uv" in i.item.lower()) for i in items] == [
        (True, False),
        (False, True),
    ]
    assert all(i.ok for i in items)


def test_a_missing_stack_tool_fails_its_item_with_the_hint() -> None:
    registry = MockStackRegistry()
    _with_requires(registry, "python_cli", ["nosuchtool"])
    report = _doctor(registry=registry).run()
    (item,) = dict(report.stacks)["python_cli"]
    assert item.ok is False
    assert "https://example.com/nosuchtool" in item.fix


def test_a_missing_stack_tool_does_not_make_the_report_not_ok() -> None:
    registry = MockStackRegistry()
    _with_requires(registry, "python_cli", ["nosuchtool"])
    report = _doctor(registry=registry).run()
    assert report.ok is True


def test_a_stack_without_requirements_has_no_items() -> None:
    registry = MockStackRegistry()
    _with_requires(registry, "python_cli", [])
    report = _doctor(registry=registry).run()
    assert report.stacks == (("python_cli", ()),)
