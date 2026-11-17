"""Tests for `bull.Modules.hooks.protection`: test-file and reference-folder protection."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.hooks.protection import Protection
from bull.Modules.parts.mocks import MockParts
from bull.Modules.settings.Contracts import SettingValue
from bull.Modules.settings.mocks import MockSettings


class _Settings(MockSettings):
    """Settings that serve `reference_dir` from a plain value."""

    def __init__(self, reference_dir: SettingValue) -> None:
        super().__init__()
        self.reference_dir = reference_dir

    def get(self, key: str, part: str | None = None) -> SettingValue:
        if key == "reference_dir":
            return self.reference_dir
        return super().get(key, part)


def _layout(root: Path) -> AppLayout:
    values = {f.name: root / f.name for f in dataclasses.fields(AppLayout)}
    values["root"] = root
    return AppLayout(**values)


def _event(
    kind: HookKind, agent: str | None, app: AppLayout, *paths: Path
) -> HookEvent:
    return HookEvent(kind, app.root, agent, None, None, None, tuple(paths))


def _check(
    tmp_path: Path,
    kind: HookKind,
    agent: str | None,
    *paths: Path,
    reference_dir: str = "reference",
    parts: MockParts | None = None,
) -> HookDecision:
    app = _layout(tmp_path)
    protection = Protection(parts or MockParts(), _Settings(reference_dir))
    return protection.check(app, _event(kind, agent, app, *paths))


# --- test protection


def test_code_writer_may_not_edit_a_test_file(tmp_path: Path) -> None:
    decision = _check(
        tmp_path,
        HookKind.BEFORE_EDIT,
        "code-writer",
        tmp_path / "tests" / "Counter" / "test_a.py",
    )
    assert not decision.allow
    assert "code-writer may not edit tests" in decision.message


def test_code_writer_may_edit_a_source_file(tmp_path: Path) -> None:
    decision = _check(
        tmp_path, HookKind.BEFORE_EDIT, "code-writer", tmp_path / "src" / "a.py"
    )
    assert decision.allow


def test_namespaced_code_writer_is_protected_the_same(tmp_path: Path) -> None:
    decision = _check(
        tmp_path,
        HookKind.BEFORE_EDIT,
        "bull:code-writer",
        tmp_path / "tests" / "test_a.py",
    )
    assert not decision.allow
    assert "code-writer may not edit tests" in decision.message


@pytest.mark.parametrize("agent", ["test-writer", "reviewer", "bull:test-writer", None])
def test_other_agents_may_edit_tests(tmp_path: Path, agent: str | None) -> None:
    decision = _check(
        tmp_path, HookKind.BEFORE_EDIT, agent, tmp_path / "tests" / "test_a.py"
    )
    assert decision.allow


def test_one_test_path_among_several_blocks_the_edit(tmp_path: Path) -> None:
    decision = _check(
        tmp_path,
        HookKind.BEFORE_EDIT,
        "code-writer",
        tmp_path / "src" / "a.py",
        tmp_path / "tests" / "test_a.py",
    )
    assert not decision.allow


def test_tests_of_any_part_are_protected(tmp_path: Path) -> None:
    parts = MockParts()
    web_test = tmp_path / "web" / "spec" / "a.spec"

    def is_test_path(app: AppLayout, path: Path) -> bool:
        return path == web_test

    parts.is_test_path = is_test_path  # type: ignore[method-assign]
    decision = _check(
        tmp_path, HookKind.BEFORE_EDIT, "code-writer", web_test, parts=parts
    )
    assert not decision.allow


def test_edit_check_asks_parts_whether_the_path_is_a_test(tmp_path: Path) -> None:
    parts = MockParts()
    path = tmp_path / "src" / "a.py"
    _check(tmp_path, HookKind.BEFORE_EDIT, "code-writer", path, parts=parts)
    assert any(name == "is_test_path" for name, _ in parts.calls)


# --- reference protection


@pytest.mark.parametrize("agent", ["test-writer", "code-writer", "bull:test-writer"])
def test_test_and_code_writers_may_not_read_the_reference_folder(
    tmp_path: Path, agent: str
) -> None:
    (tmp_path / "reference").mkdir()
    decision = _check(
        tmp_path, HookKind.BEFORE_READ, agent, tmp_path / "reference" / "old_test.py"
    )
    assert not decision.allow
    assert decision.message != ""


def test_reading_a_nested_file_in_the_reference_folder_is_blocked(
    tmp_path: Path,
) -> None:
    (tmp_path / "reference" / "v1" / "deep").mkdir(parents=True)
    decision = _check(
        tmp_path,
        HookKind.BEFORE_READ,
        "test-writer",
        tmp_path / "reference" / "v1" / "deep" / "t.py",
    )
    assert not decision.allow


@pytest.mark.parametrize("agent", ["reviewer", "legacy-test-scanner", None])
def test_other_agents_may_read_the_reference_folder(
    tmp_path: Path, agent: str | None
) -> None:
    (tmp_path / "reference").mkdir()
    decision = _check(
        tmp_path, HookKind.BEFORE_READ, agent, tmp_path / "reference" / "old.py"
    )
    assert decision.allow


def test_reading_outside_the_reference_folder_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "reference").mkdir()
    decision = _check(
        tmp_path, HookKind.BEFORE_READ, "test-writer", tmp_path / "docs" / "outline.md"
    )
    assert decision.allow


def test_a_sibling_folder_with_the_same_prefix_is_not_the_reference_folder(
    tmp_path: Path,
) -> None:
    (tmp_path / "reference").mkdir()
    decision = _check(
        tmp_path,
        HookKind.BEFORE_READ,
        "test-writer",
        tmp_path / "reference-notes" / "a.md",
    )
    assert decision.allow


def test_reference_rule_does_not_apply_when_the_folder_does_not_exist(
    tmp_path: Path,
) -> None:
    decision = _check(
        tmp_path, HookKind.BEFORE_READ, "test-writer", tmp_path / "reference" / "a.py"
    )
    assert decision.allow


def test_reference_dir_setting_can_be_a_relative_path(tmp_path: Path) -> None:
    (tmp_path / "old" / "v1").mkdir(parents=True)
    decision = _check(
        tmp_path,
        HookKind.BEFORE_READ,
        "code-writer",
        tmp_path / "old" / "v1" / "a.py",
        reference_dir="old/v1",
    )
    assert not decision.allow


def test_reference_dir_setting_can_be_an_absolute_path(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    app_root = tmp_path / "app"
    app_root.mkdir()
    app = _layout(app_root)
    protection = Protection(MockParts(), _Settings(str(elsewhere)))
    event = _event(HookKind.BEFORE_READ, "test-writer", app, elsewhere / "a.py")
    assert not protection.check(app, event).allow


def test_one_reference_path_among_several_blocks_the_read(tmp_path: Path) -> None:
    (tmp_path / "reference").mkdir()
    decision = _check(
        tmp_path,
        HookKind.BEFORE_READ,
        "test-writer",
        tmp_path / "docs" / "outline.md",
        tmp_path / "reference" / "a.py",
    )
    assert not decision.allow


def test_code_writer_editing_the_reference_folder_is_not_a_read(
    tmp_path: Path,
) -> None:
    (tmp_path / "reference").mkdir()
    decision = _check(
        tmp_path, HookKind.BEFORE_EDIT, "code-writer", tmp_path / "reference" / "a.py"
    )
    assert decision.allow


def test_code_writer_reading_tests_is_allowed(tmp_path: Path) -> None:
    decision = _check(
        tmp_path, HookKind.BEFORE_READ, "code-writer", tmp_path / "tests" / "test_a.py"
    )
    assert decision.allow


def test_non_string_reference_dir_setting_raises_type_error(tmp_path: Path) -> None:
    app = _layout(tmp_path)
    protection = Protection(MockParts(), _Settings(5))
    event = _event(HookKind.BEFORE_READ, "test-writer", app, tmp_path / "a.py")
    with pytest.raises(TypeError):
        protection.check(app, event)
