"""Tests for `app_files` (`bull.Modules.claude_code.app_files`)."""

from __future__ import annotations

import json
from pathlib import Path

from bull.Modules.claude_code.plugin import LiveProvider
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.plugin_text.mocks import MockPluginText

BEGIN = "<!-- bull:begin -->"
END = "<!-- bull:end -->"
IMPORT = "@.bull/plugin/orchestrator.md"


def _files(app: AppLayout) -> dict[Path, str]:
    return LiveProvider(MockPluginText()).app_files(app)


def _app(tmp_path: Path) -> AppLayout:
    root = tmp_path / "app"
    root.mkdir()
    return sample_layout(root)


def _settings(app: AppLayout) -> dict[str, object]:
    text = _files(app)[app.root / ".claude" / "settings.json"]
    data = json.loads(text)
    assert isinstance(data, dict)
    return data


def test_app_files_returns_settings_and_claude_md_paths(tmp_path: Path) -> None:
    app = _app(tmp_path)
    assert set(_files(app)) == {
        app.root / ".claude" / "settings.json",
        app.root / "CLAUDE.md",
    }


def test_app_files_does_not_write_anything(tmp_path: Path) -> None:
    app = _app(tmp_path)
    _files(app)
    assert list(app.root.iterdir()) == []


def test_settings_status_line_runs_bull_statusline(tmp_path: Path) -> None:
    data = _settings(_app(tmp_path))
    status_line = data["statusLine"]
    assert isinstance(status_line, dict)
    assert status_line["command"] == "bull statusline"


def test_settings_allow_bull_and_git_commands(tmp_path: Path) -> None:
    data = _settings(_app(tmp_path))
    permissions = data["permissions"]
    assert isinstance(permissions, dict)
    allow = permissions["allow"]
    assert isinstance(allow, list)
    assert "Bash(bull:*)" in allow
    assert "Bash(git:*)" in allow


def test_settings_disable_background_tasks(tmp_path: Path) -> None:
    data = _settings(_app(tmp_path))
    env = data["env"]
    assert isinstance(env, dict)
    assert env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"


def test_settings_merge_keeps_the_users_other_keys(tmp_path: Path) -> None:
    app = _app(tmp_path)
    (app.root / ".claude").mkdir()
    (app.root / ".claude" / "settings.json").write_text(
        json.dumps({"model": "opus", "env": {"MY_VAR": "x"}})
    )
    data = _settings(app)
    assert data["model"] == "opus"
    env = data["env"]
    assert isinstance(env, dict)
    assert env["MY_VAR"] == "x"
    assert env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    assert "statusLine" in data


def test_settings_merge_keeps_the_users_permissions(tmp_path: Path) -> None:
    app = _app(tmp_path)
    (app.root / ".claude").mkdir()
    (app.root / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls:*)"], "deny": ["Read(.env)"]}})
    )
    permissions = _settings(app)["permissions"]
    assert isinstance(permissions, dict)
    assert "Bash(ls:*)" in permissions["allow"]
    assert "Bash(bull:*)" in permissions["allow"]
    assert "Bash(git:*)" in permissions["allow"]
    assert permissions["deny"] == ["Read(.env)"]


def test_settings_merge_does_not_duplicate_entries_when_applied_twice(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    settings_path = app.root / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text(_files(app)[settings_path])
    permissions = _settings(app)["permissions"]
    assert isinstance(permissions, dict)
    allow = permissions["allow"]
    assert allow.count("Bash(bull:*)") == 1
    assert allow.count("Bash(git:*)") == 1


def test_settings_output_is_stable_when_applied_twice(tmp_path: Path) -> None:
    app = _app(tmp_path)
    settings_path = app.root / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    first = _files(app)[settings_path]
    settings_path.write_text(first)
    assert _files(app)[settings_path] == first


def test_claude_md_new_file_has_marked_block_importing_the_orchestrator(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    text = _files(app)[app.root / "CLAUDE.md"]
    assert text.count(BEGIN) == 1
    assert text.count(END) == 1
    assert text.index(BEGIN) < text.index(IMPORT) < text.index(END)


def test_claude_md_replaces_only_the_marked_block(tmp_path: Path) -> None:
    app = _app(tmp_path)
    (app.root / "CLAUDE.md").write_text(
        f"# My app\n\nNotes above.\n\n{BEGIN}\nOLD CONTENT\n{END}\n\nNotes below.\n"
    )
    text = _files(app)[app.root / "CLAUDE.md"]
    assert "OLD CONTENT" not in text
    assert text.startswith("# My app\n\nNotes above.\n\n" + BEGIN)
    assert text.endswith(END + "\n\nNotes below.\n")
    assert text.count(BEGIN) == 1
    assert IMPORT in text


def test_claude_md_without_a_block_keeps_existing_text_and_adds_the_block(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    (app.root / "CLAUDE.md").write_text("# My app\n\nKeep me.\n")
    text = _files(app)[app.root / "CLAUDE.md"]
    assert "# My app\n\nKeep me.\n" in text
    assert text.count(BEGIN) == 1
    assert IMPORT in text


def test_claude_md_output_is_stable_when_applied_twice(tmp_path: Path) -> None:
    app = _app(tmp_path)
    claude_md = app.root / "CLAUDE.md"
    claude_md.write_text("# My app\n")
    first = _files(app)[claude_md]
    claude_md.write_text(first)
    assert _files(app)[claude_md] == first


def test_generated_files_contain_no_absolute_paths(tmp_path: Path) -> None:
    app = _app(tmp_path)
    for text in _files(app).values():
        assert str(app.root) not in text
        assert str(tmp_path) not in text
