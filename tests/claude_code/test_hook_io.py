"""Tests for `parse_hook` and `hook_output` (`bull.Modules.claude_code.hook_io`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bull.Modules.claude_code.Contracts import HookOutput
from bull.Modules.claude_code.plugin import LiveProvider
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.plugin_text.mocks import MockPluginText


def _provider() -> LiveProvider:
    return LiveProvider(MockPluginText())


def _raw(**fields: object) -> str:
    return json.dumps(fields)


def test_parse_hook_reads_cwd_into_the_event() -> None:
    event = _provider().parse_hook(HookKind.SESSION_START, _raw(cwd="/work/app"))
    assert event.cwd == Path("/work/app")
    assert event.kind is HookKind.SESSION_START


@pytest.mark.parametrize("kind", list(HookKind))
def test_parse_hook_keeps_the_requested_kind(kind: HookKind) -> None:
    event = _provider().parse_hook(kind, _raw(cwd="/work/app"))
    assert event.kind is kind


def test_parse_hook_reads_calling_subagent_type_as_agent() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_SHELL,
        _raw(
            cwd="/work/app",
            agent_type="bull:code-writer",
            tool_name="Bash",
            tool_input={"command": "ls"},
        ),
    )
    assert event.agent == "bull:code-writer"


def test_parse_hook_agent_is_none_when_not_called_from_a_subagent() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_SHELL,
        _raw(cwd="/work/app", tool_name="Bash", tool_input={"command": "ls"}),
    )
    assert event.agent is None


def test_parse_hook_reads_launched_subagent_type_and_prompt() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_AGENT,
        _raw(
            cwd="/work/app",
            tool_name="Task",
            tool_input={"subagent_type": "bull:test-writer", "prompt": "TASK: x"},
        ),
    )
    assert event.target_agent == "bull:test-writer"
    assert event.prompt == "TASK: x"


def test_parse_hook_reads_bash_command() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_SHELL,
        _raw(cwd="/work/app", tool_name="Bash", tool_input={"command": "git merge x"}),
    )
    assert event.command == "git merge x"


def test_parse_hook_reads_file_path_into_paths() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_EDIT,
        _raw(cwd="/work/app", tool_name="Edit", tool_input={"file_path": "/work/a.py"}),
    )
    assert event.paths == (Path("/work/a.py"),)


def test_parse_hook_reads_path_into_paths() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_READ,
        _raw(cwd="/work/app", tool_name="Grep", tool_input={"path": "/work/src"}),
    )
    assert event.paths == (Path("/work/src"),)


def test_parse_hook_reads_notebook_path_into_paths() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_EDIT,
        _raw(
            cwd="/work/app",
            tool_name="NotebookEdit",
            tool_input={"notebook_path": "/work/n.ipynb"},
        ),
    )
    assert event.paths == (Path("/work/n.ipynb"),)


def test_parse_hook_collects_every_path_field_present() -> None:
    event = _provider().parse_hook(
        HookKind.BEFORE_EDIT,
        _raw(
            cwd="/work/app",
            tool_input={"file_path": "/work/a.py", "notebook_path": "/work/n.ipynb"},
        ),
    )
    assert set(event.paths) == {Path("/work/a.py"), Path("/work/n.ipynb")}


def test_parse_hook_without_tool_input_has_empty_fields() -> None:
    event = _provider().parse_hook(HookKind.SESSION_START, _raw(cwd="/work/app"))
    assert event.paths == ()
    assert event.command is None
    assert event.prompt is None
    assert event.target_agent is None


@pytest.mark.parametrize("raw", ["", "not json", "{", "[1, 2"])
def test_parse_hook_malformed_json_gives_allow_everything_event(raw: str) -> None:
    event = _provider().parse_hook(HookKind.BEFORE_SHELL, raw)
    assert event == HookEvent(
        kind=HookKind.BEFORE_SHELL,
        cwd=Path("."),
        agent=None,
        target_agent=None,
        prompt=None,
        command=None,
        paths=(),
    )


def test_parse_hook_malformed_json_keeps_the_kind() -> None:
    event = _provider().parse_hook(HookKind.AGENT_END, "}{")
    assert event.kind is HookKind.AGENT_END
    assert event.cwd == Path(".")


def test_hook_output_block_exits_2_with_message_on_stderr() -> None:
    out = _provider().hook_output(
        HookKind.BEFORE_SHELL, HookDecision(allow=False, message="no merging")
    )
    assert out == HookOutput(stdout="", stderr="no merging", exit_code=2)


@pytest.mark.parametrize("kind", list(HookKind))
def test_hook_output_block_exits_2_for_every_kind(kind: HookKind) -> None:
    out = _provider().hook_output(kind, HookDecision(allow=False, message="stop"))
    assert out.exit_code == 2
    assert out.stderr == "stop"


@pytest.mark.parametrize(
    "kind",
    [k for k in HookKind if k is not HookKind.SESSION_START],
)
def test_hook_output_allow_exits_0_and_prints_nothing(kind: HookKind) -> None:
    out = _provider().hook_output(kind, HookDecision(allow=True, message=""))
    assert out == HookOutput(stdout="", stderr="", exit_code=0)


def test_hook_output_session_start_prints_message_on_stdout() -> None:
    out = _provider().hook_output(
        HookKind.SESSION_START, HookDecision(allow=True, message="resume here")
    )
    assert out.stdout == "resume here"
    assert out.stderr == ""
    assert out.exit_code == 0


def test_hook_output_session_start_with_empty_message_prints_nothing() -> None:
    out = _provider().hook_output(
        HookKind.SESSION_START, HookDecision(allow=True, message="")
    )
    assert out == HookOutput(stdout="", stderr="", exit_code=0)
