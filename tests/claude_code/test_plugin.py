"""Tests for `render_plugin` in `bull.Modules.claude_code.plugin`."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.claude_code.plugin import LiveProvider
from bull.Modules.plugin_text.Contracts import PluginFile
from bull.Modules.plugin_text.mocks import MockPluginText
from bull.Modules.settings.Contracts import SettingValue
from bull.Modules.settings.mocks import MockSettings

REVIEWER_FILE = "agents/reviewer.md"


def _render(
    dest: Path,
    text: MockPluginText | None = None,
    settings: MockSettings | None = None,
    version: str = "1.2.3",
) -> Path:
    provider = LiveProvider(text or MockPluginText())
    return provider.render_plugin(dest, settings or MockSettings(), version)


def _frontmatter(text: str) -> list[str]:
    lines = text.split("\n")
    assert lines[0] == "---"
    end = lines.index("---", 1)
    return lines[1:end]


def test_render_plugin_returns_dest(tmp_path: Path) -> None:
    dest = tmp_path / "plugin"
    assert _render(dest) == dest


def test_render_plugin_creates_missing_parent_folders(tmp_path: Path) -> None:
    dest = tmp_path / "a" / "b" / "plugin"
    _render(dest)
    assert (dest / ".claude-plugin" / "plugin.json").is_file()


def test_plugin_json_names_bull_with_given_version(tmp_path: Path) -> None:
    dest = _render(tmp_path / "plugin", version="4.5.6")
    data = json.loads((dest / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert data["name"] == "bull"
    assert data["version"] == "4.5.6"


def test_command_files_are_copied_from_plugin_text(tmp_path: Path) -> None:
    text = MockPluginText()
    dest = _render(tmp_path / "plugin", text)
    expected = next(f for f in text.plugin_files if f.path == "commands/status.md")
    assert (dest / "commands" / "status.md").read_text("utf-8") == expected.text


def test_orchestrator_file_holds_the_orchestrator_text(tmp_path: Path) -> None:
    text = MockPluginText()
    dest = _render(tmp_path / "plugin", text)
    assert (dest / "orchestrator.md").read_text("utf-8") == text.orchestrator()


def test_hooks_json_is_written_and_valid_json(tmp_path: Path) -> None:
    dest = _render(tmp_path / "plugin")
    data = json.loads((dest / "hooks" / "hooks.json").read_text("utf-8"))
    assert isinstance(data, dict)


def test_agent_gets_model_line_from_its_setting(tmp_path: Path) -> None:
    settings = MockSettings()
    settings.values["models.reviewer"] = "haiku"
    dest = _render(tmp_path / "plugin", settings=settings)
    front = _frontmatter((dest / REVIEWER_FILE).read_text("utf-8"))
    assert "model: haiku" in front


def test_agent_model_line_keeps_the_original_frontmatter_and_body(
    tmp_path: Path,
) -> None:
    text = MockPluginText()
    original = text.plugin_files[0]
    text.plugin_files[0] = type(original)(
        original.path, original.text + "Body line one.\nBody line two.\n"
    )
    dest = _render(tmp_path / "plugin", text)
    written = (dest / REVIEWER_FILE).read_text("utf-8")
    front = _frontmatter(written)
    for line in ("name: reviewer", "description: Reviews a unit.", "tools: Read, Grep"):
        assert line in front
    assert written.endswith("---\nBody line one.\nBody line two.\n")
    assert sum(1 for line in front if line.startswith("model:")) == 1


def test_agent_has_no_model_line_when_setting_is_inherit(tmp_path: Path) -> None:
    settings = MockSettings()
    settings.values["models.reviewer"] = "inherit"
    dest = _render(tmp_path / "plugin", settings=settings)
    written = (dest / REVIEWER_FILE).read_text("utf-8")
    assert "model:" not in written
    assert written == MockPluginText().plugin_files[0].text


def test_render_plugin_replaces_dest_completely(tmp_path: Path) -> None:
    dest = tmp_path / "plugin"
    (dest / "commands").mkdir(parents=True)
    (dest / "commands" / "stale.md").write_text("old", encoding="utf-8")
    (dest / "leftover.txt").write_text("old", encoding="utf-8")
    _render(dest)
    assert not (dest / "commands" / "stale.md").exists()
    assert not (dest / "leftover.txt").exists()
    assert (dest / "commands" / "status.md").is_file()


def test_render_plugin_twice_gives_same_files(tmp_path: Path) -> None:
    dest = tmp_path / "plugin"
    _render(dest)
    first = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*"))
    _render(dest)
    second = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*"))
    assert first == second


@pytest.mark.parametrize("version", ["0.0.1", "2.0.0-rc1"])
def test_plugin_json_carries_any_version_string(tmp_path: Path, version: str) -> None:
    dest = _render(tmp_path / "plugin", version=version)
    data = json.loads((dest / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert data["version"] == version


def _with_files(*files: PluginFile) -> MockPluginText:
    text = MockPluginText()
    text.plugin_files = list(files) + [
        f for f in text.plugin_files if f.path == "orchestrator.md"
    ]
    return text


@pytest.mark.parametrize(
    "bad_path",
    ["", "/etc/evil.md", "commands/../../evil.md", "../evil.md", "commands/.."],
)
def test_plugin_file_path_empty_absolute_or_with_dotdot_is_refused(
    tmp_path: Path, bad_path: str
) -> None:
    dest = tmp_path / "plugin"
    text = _with_files(PluginFile(bad_path, "x"))
    with pytest.raises(ValueError):
        _render(dest, text)
    assert not (tmp_path / "evil.md").exists()
    assert not (tmp_path.parent / "evil.md").exists()


class _FailingSettings(MockSettings):
    def get(self, key: str, part: str | None = None) -> SettingValue:
        raise RuntimeError("settings exploded")


def test_failed_build_removes_temporary_folder_and_reraises(tmp_path: Path) -> None:
    dest = tmp_path / "plugin"
    with pytest.raises(RuntimeError, match="settings exploded"):
        _render(dest, settings=_FailingSettings())
    assert list(tmp_path.iterdir()) == []


def test_failed_build_leaves_the_old_dest_untouched(tmp_path: Path) -> None:
    dest = tmp_path / "plugin"
    dest.mkdir()
    (dest / "keep.txt").write_text("old", encoding="utf-8")
    with pytest.raises(RuntimeError):
        _render(dest, settings=_FailingSettings())
    assert (dest / "keep.txt").read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["plugin"]


def test_failed_swap_restores_old_dest_and_reraises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "plugin"
    dest.mkdir()
    (dest / "keep.txt").write_text("old", encoding="utf-8")

    def _is_new_build(src: object) -> bool:
        return (Path(str(src)) / ".claude-plugin").exists()

    real_rename = os.rename
    real_replace = os.replace

    def _fail_for_build(real: Callable[..., None]) -> Callable[..., None]:
        def wrapper(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
            if Path(str(dst)) == dest and _is_new_build(src):
                raise OSError("swap failed")
            real(src, dst, *args, **kwargs)

        return wrapper

    monkeypatch.setattr(os, "rename", _fail_for_build(real_rename))
    monkeypatch.setattr(os, "replace", _fail_for_build(real_replace))
    real_move = shutil.move

    def _move(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
        if Path(str(dst)) == dest and _is_new_build(src):
            raise OSError("swap failed")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "move", _move)
    with pytest.raises(OSError, match="swap failed"):
        _render(dest)
    assert (dest / "keep.txt").read_text(encoding="utf-8") == "old"
    assert not (dest / ".claude-plugin").exists()
    assert [p.name for p in tmp_path.iterdir()] == ["plugin"]


def test_old_dest_symlink_is_unlinked_and_its_target_untouched(
    tmp_path: Path,
) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "precious.txt").write_text("mine", encoding="utf-8")
    dest = tmp_path / "plugin"
    dest.symlink_to(target, target_is_directory=True)
    _render(dest)
    assert not dest.is_symlink()
    assert (dest / ".claude-plugin" / "plugin.json").is_file()
    assert [p.name for p in target.iterdir()] == ["precious.txt"]
    assert (target / "precious.txt").read_text(encoding="utf-8") == "mine"


def test_old_dest_symlink_to_a_file_is_unlinked_and_target_kept(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("mine", encoding="utf-8")
    dest = tmp_path / "plugin"
    dest.symlink_to(target)
    _render(dest)
    assert dest.is_dir() and not dest.is_symlink()
    assert target.read_text(encoding="utf-8") == "mine"


@pytest.mark.parametrize(
    "agent_text",
    [
        "No frontmatter here.\nJust a body.\n",
        "---\nname: reviewer\ndescription: Never closed.\nBody continues.\n",
    ],
)
def test_agent_without_closed_frontmatter_is_written_unchanged(
    tmp_path: Path, agent_text: str
) -> None:
    settings = MockSettings()
    settings.values["models.reviewer"] = "haiku"
    text = _with_files(PluginFile(REVIEWER_FILE, agent_text))
    dest = _render(tmp_path / "plugin", text, settings)
    assert (dest / REVIEWER_FILE).read_text("utf-8") == agent_text
