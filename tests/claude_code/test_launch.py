"""Tests for `launch_argv` and `tool_check` (`bull.Modules.claude_code.launch`)."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

from bull.Modules.claude_code.plugin import LiveProvider
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.plugin_text.mocks import MockPluginText

INSTALL_FIX = "install Claude Code: https://docs.claude.com/claude-code"


def _provider() -> LiveProvider:
    return LiveProvider(MockPluginText())


def test_launch_argv_points_plugin_dir_at_the_apps_plugin(tmp_path: Path) -> None:
    app = sample_layout(tmp_path / "app")
    argv = _provider().launch_argv(app, [])
    assert argv == [
        "claude",
        "--plugin-dir",
        str(tmp_path / "app" / ".bull" / "plugin"),
    ]


def test_launch_argv_appends_extra_arguments_in_order(tmp_path: Path) -> None:
    app = sample_layout(tmp_path / "app")
    argv = _provider().launch_argv(app, ["--resume", "abc"])
    assert argv[:3] == ["claude", "--plugin-dir", str(app.plugin_dir)]
    assert argv[3:] == ["--resume", "abc"]


def test_launch_argv_returns_a_list_of_strings(tmp_path: Path) -> None:
    app = sample_layout(tmp_path / "app")
    argv = _provider().launch_argv(app, ("-p",))
    assert isinstance(argv, list)
    assert all(isinstance(a, str) for a in argv)


def _fake_claude(bin_dir: Path, version_text: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "claude"
    script.write_text(f'#!/bin/sh\necho "{version_text}"\n', encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


def test_tool_check_ok_with_claude_version_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_claude(tmp_path / "bin", "2.1.0 (Claude Code)")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    result = _provider().tool_check()
    assert result.ok is True
    assert "2.1.0 (Claude Code)" in result.item


def test_tool_check_not_ok_when_claude_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    result = _provider().tool_check()
    assert result.ok is False
    assert result.fix == INSTALL_FIX


def _install_claude(bin_dir: Path, body: str, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "claude"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bin_dir))


def test_tool_check_not_ok_when_claude_version_cannot_be_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_claude(tmp_path / "bin", "#!/nonexistent/interpreter\n", monkeypatch)
    result = _provider().tool_check()
    assert result.ok is False
    assert result.fix == INSTALL_FIX
    assert result.item


def test_tool_check_not_ok_when_claude_version_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_claude(tmp_path / "bin", "#!/bin/sh\necho 1.0\n", monkeypatch)

    def _timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="claude --version", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    result = _provider().tool_check()
    assert result.ok is False
    assert result.fix == INSTALL_FIX
    assert result.item


def test_tool_check_not_ok_when_claude_version_raises_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_claude(tmp_path / "bin", "#!/bin/sh\necho 1.0\n", monkeypatch)

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("exec failed")

    monkeypatch.setattr(subprocess, "run", _boom)
    result = _provider().tool_check()
    assert result.ok is False
    assert result.fix == INSTALL_FIX


def test_tool_check_not_ok_when_claude_version_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_claude(
        tmp_path / "bin",
        "#!/bin/sh\necho 'broken install' >&2\necho 'oops out'\nexit 3\n",
        monkeypatch,
    )
    result = _provider().tool_check()
    assert result.ok is False
    assert result.fix == INSTALL_FIX
    assert "3" in result.item
    assert "broken install" in result.item or "oops out" in result.item
