"""The plugin's `hooks/hooks.json`."""

from __future__ import annotations

import json

# Claude Code tool names each `bull hook <kind>` command watches before a tool runs.
# The agent-launch tool has been named both `Task` and `Agent` across Claude Code versions.
_PRE_TOOL_USE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("Task", "Agent"), "before-agent"),
    (("Bash",), "before-shell"),
    (("Edit", "Write", "MultiEdit", "NotebookEdit"), "before-edit"),
    (("Read", "Grep", "Glob"), "before-read"),
)


def _command(kind: str) -> dict[str, str]:
    return {"type": "command", "command": f"bull hook {kind}"}


def hooks_json() -> str:
    """The text of `hooks/hooks.json` in Claude Code's hook configuration shape."""
    table: dict[str, list[dict[str, object]]] = {
        "SessionStart": [{"hooks": [_command("session-start")]}],
        "PreToolUse": [
            {"matcher": "|".join(tools), "hooks": [_command(kind)]}
            for tools, kind in _PRE_TOOL_USE
        ],
        "SubagentStop": [{"hooks": [_command("agent-end")]}],
    }
    return json.dumps({"hooks": table}, indent=2) + "\n"
