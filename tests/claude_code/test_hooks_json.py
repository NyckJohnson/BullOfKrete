"""Tests for the rendered `hooks/hooks.json` (`bull.Modules.claude_code.hooks_json`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.claude_code.plugin import LiveProvider
from bull.Modules.plugin_text.mocks import MockPluginText
from bull.Modules.settings.mocks import MockSettings


def _entries(tmp_path: Path) -> list[tuple[str, set[str], str]]:
    """Every hook as (event, matcher tool names, command)."""
    dest = LiveProvider(MockPluginText()).render_plugin(
        tmp_path / "plugin", MockSettings(), "1.0.0"
    )
    data = json.loads((dest / "hooks" / "hooks.json").read_text("utf-8"))
    hooks = data["hooks"]
    found: list[tuple[str, set[str], str]] = []
    for event, groups in hooks.items():
        for group in groups:
            matcher = group.get("matcher", "")
            tools = {m for m in matcher.split("|") if m}
            for hook in group["hooks"]:
                found.append((event, tools, hook["command"]))
    return found


def _tools_for(entries: list[tuple[str, set[str], str]], command: str) -> set[str]:
    tools: set[str] = set()
    for event, matched, cmd in entries:
        if event == "PreToolUse" and cmd == command:
            tools |= matched
    return tools


def test_hooks_json_is_valid_json_with_hooks_table(tmp_path: Path) -> None:
    dest = LiveProvider(MockPluginText()).render_plugin(
        tmp_path / "plugin", MockSettings(), "1.0.0"
    )
    data = json.loads((dest / "hooks" / "hooks.json").read_text("utf-8"))
    assert isinstance(data["hooks"], dict)


def test_session_start_runs_bull_hook_session_start(tmp_path: Path) -> None:
    entries = _entries(tmp_path)
    assert [c for e, _, c in entries if e == "SessionStart"] == [
        "bull hook session-start"
    ]


def test_subagent_stop_runs_bull_hook_agent_end(tmp_path: Path) -> None:
    entries = _entries(tmp_path)
    assert [c for e, _, c in entries if e == "SubagentStop"] == ["bull hook agent-end"]


def test_pre_tool_use_on_agent_launch_tool_runs_before_agent(tmp_path: Path) -> None:
    tools = _tools_for(_entries(tmp_path), "bull hook before-agent")
    assert len(tools) == 1
    assert tools <= {"Task", "Agent"}


def test_pre_tool_use_on_bash_runs_before_shell(tmp_path: Path) -> None:
    assert _tools_for(_entries(tmp_path), "bull hook before-shell") == {"Bash"}


def test_pre_tool_use_on_edit_tools_runs_before_edit(tmp_path: Path) -> None:
    assert _tools_for(_entries(tmp_path), "bull hook before-edit") == {
        "Edit",
        "Write",
        "MultiEdit",
        "NotebookEdit",
    }


def test_pre_tool_use_on_read_tools_runs_before_read(tmp_path: Path) -> None:
    assert _tools_for(_entries(tmp_path), "bull hook before-read") == {
        "Read",
        "Grep",
        "Glob",
    }


@pytest.mark.parametrize(
    "command",
    [
        "bull hook session-start",
        "bull hook before-agent",
        "bull hook before-shell",
        "bull hook before-edit",
        "bull hook before-read",
        "bull hook agent-end",
    ],
)
def test_every_hook_command_is_present(tmp_path: Path, command: str) -> None:
    assert command in [c for _, _, c in _entries(tmp_path)]
