"""Tests for the claude_code mocks."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.claude_code.Contracts import HookOutput, Provider, StatusLineInput
from bull.Modules.claude_code.mocks import MockProvider
from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.hooks.Contracts import HookDecision, HookKind
from bull.Modules.settings.mocks import MockSettings


def test_mock_satisfies_protocol() -> None:
    provider: Provider = MockProvider()
    assert provider.name == "mock"


def test_mock_starts_with_no_calls() -> None:
    assert MockProvider().calls == []


def test_block_decision_exits_2_with_message_on_stderr() -> None:
    out = MockProvider().hook_output(
        HookKind.BEFORE_SHELL, HookDecision(False, "no way")
    )
    assert out == HookOutput("", "no way", 2)


@pytest.mark.parametrize(
    "kind",
    [
        HookKind.BEFORE_AGENT,
        HookKind.BEFORE_SHELL,
        HookKind.BEFORE_EDIT,
        HookKind.BEFORE_READ,
        HookKind.AGENT_END,
    ],
)
def test_allow_decision_exits_0_with_no_output(kind: HookKind) -> None:
    out = MockProvider().hook_output(kind, HookDecision(True, "ignored"))
    assert out == HookOutput("", "", 0)


def test_session_start_message_goes_to_stdout() -> None:
    out = MockProvider().hook_output(
        HookKind.SESSION_START, HookDecision(True, "context")
    )
    assert out == HookOutput("context", "", 0)


def test_launch_argv_is_claude_plugin_dir_then_extra() -> None:
    app = sample_layout()
    argv = MockProvider().launch_argv(app, ["--resume", "x"])
    assert argv == [
        "claude",
        "--plugin-dir",
        str(app.root / ".bull" / "plugin"),
        "--resume",
        "x",
    ]


def test_launch_argv_without_extra_has_only_the_base() -> None:
    app = sample_layout()
    assert MockProvider().launch_argv(app, []) == [
        "claude",
        "--plugin-dir",
        str(app.plugin_dir),
    ]


def test_tool_check_reports_ok() -> None:
    assert MockProvider().tool_check().ok is True


def test_render_plugin_returns_dest() -> None:
    assert MockProvider().render_plugin(
        Path("/x/plugin"), MockSettings(), "1.0"
    ) == Path("/x/plugin")


def test_parse_hook_returns_event_of_the_kind_with_raw_as_prompt() -> None:
    event = MockProvider().parse_hook(HookKind.BEFORE_AGENT, "hello")
    assert event.kind is HookKind.BEFORE_AGENT
    assert event.prompt == "hello"


def test_parse_statusline_returns_a_status_line_input() -> None:
    assert isinstance(MockProvider().parse_statusline("{}"), StatusLineInput)


def test_app_files_keys_are_under_the_app_root() -> None:
    app = sample_layout()
    files = MockProvider().app_files(app)
    assert files
    assert all(path.is_relative_to(app.root) for path in files)


def test_app_files_cover_settings_and_claude_md() -> None:
    app = sample_layout()
    files = MockProvider().app_files(app)
    assert app.root / ".claude" / "settings.json" in files
    assert app.root / "CLAUDE.md" in files


def test_app_files_content_has_no_absolute_paths() -> None:
    app = sample_layout()
    for content in MockProvider().app_files(app).values():
        assert str(app.root) not in content


def test_calls_are_recorded_in_order() -> None:
    provider = MockProvider()
    app = sample_layout()
    provider.tool_check()
    provider.launch_argv(app, ["a"])
    provider.hook_output(HookKind.BEFORE_EDIT, HookDecision(True, ""))
    provider.app_files(app)
    assert [name for name, _ in provider.calls] == [
        "tool_check",
        "launch_argv",
        "hook_output",
        "app_files",
    ]
    assert provider.calls[1][1] == (app, ("a",))
