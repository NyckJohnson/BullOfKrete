"""Claude Code's hook and status-line JSON in, hook output out."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from bull.Modules.claude_code.Contracts import HookOutput, StatusLineInput
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.usage.Contracts import UsageSample

_PATH_FIELDS = ("file_path", "path", "notebook_path")
_BLOCK_EXIT = 2


def parse_hook(kind: HookKind, raw: str) -> HookEvent:
    """Claude Code's hook JSON as a `HookEvent` of `kind`.

    Unreadable input (malformed JSON, or not a JSON object) gives an event with cwd `.`
    and no other fields, which the hooks module allows.
    """
    data = _object(raw)
    if data is None:
        return HookEvent(
            kind=kind,
            cwd=Path("."),
            agent=None,
            target_agent=None,
            prompt=None,
            command=None,
            paths=(),
        )
    tool_input = data.get("tool_input")
    fields = tool_input if isinstance(tool_input, dict) else {}
    paths = tuple(
        Path(value)
        for name in _PATH_FIELDS
        if isinstance(value := fields.get(name), str) and value
    )
    return HookEvent(
        kind=kind,
        cwd=Path(_string(data.get("cwd")) or "."),
        agent=_string(data.get("agent_type")),
        target_agent=_string(fields.get("subagent_type")),
        prompt=_string(fields.get("prompt")),
        command=_string(fields.get("command")),
        paths=paths,
    )


def hook_output(kind: HookKind, decision: HookDecision) -> HookOutput:
    """What the hook command prints and exits with for `decision`.

    Block → exit 2 with the message on stderr (Claude Code shows it to the model);
    allow → exit 0; session start prints the message on stdout (added to the model's
    context), every other kind prints it on stderr (a warning such as unknown usage).
    """
    if not decision.allow:
        return HookOutput(stdout="", stderr=decision.message, exit_code=_BLOCK_EXIT)
    if kind is HookKind.SESSION_START:
        return HookOutput(stdout=decision.message, stderr="", exit_code=0)
    return HookOutput(stdout="", stderr=decision.message, exit_code=0)


def parse_statusline(raw: str, now: datetime) -> StatusLineInput:
    """Claude Code's status-line JSON as the cwd and, when present, a usage sample at `now`.

    A sample exists when `rate_limits.five_hour`, `rate_limits.seven_day` or
    `context_window` has a finite numeric `used_percentage`; the context figure goes into the
    sample's `context`. Malformed input gives cwd `.` and no usage.
    """
    data = _object(raw)
    if data is None:
        return StatusLineInput(cwd=Path("."), usage=None)
    cwd = _string(data.get("cwd"))
    if cwd is None:
        workspace = data.get("workspace")
        if isinstance(workspace, dict):
            cwd = _string(workspace.get("current_dir"))
    usage = _usage(data, now)
    return StatusLineInput(cwd=Path(cwd or "."), usage=usage)


def _usage(data: dict[str, object], now: datetime) -> UsageSample | None:
    """The rate-limit windows and context figure as a sample, or None when none is readable."""
    limits = data.get("rate_limits")
    if not isinstance(limits, dict):
        limits = {}
    five_used, five_resets = _window(limits.get("five_hour"))
    week_used, week_resets = _window(limits.get("seven_day"))
    context, _ = _window(data.get("context_window"))
    if five_used is None and week_used is None and context is None:
        return None
    return UsageSample(
        time=now,
        five_hour=five_used,
        weekly=week_used,
        five_hour_resets=five_resets,
        weekly_resets=week_resets,
        context=context,
    )


def _window(value: object) -> tuple[float | None, datetime | None]:
    """A rate-limit window's used percentage and reset time, each None when unreadable."""
    if not isinstance(value, dict):
        return None, None
    return _percent(value.get("used_percentage")), _time(value.get("resets_at"))


def _percent(value: object) -> float | None:
    """A percentage as a float, or None unless it is a finite number (booleans excluded)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        percent = float(value)
    except OverflowError:
        return None
    return percent if math.isfinite(percent) else None


def _time(value: object) -> datetime | None:
    """Epoch seconds or an ISO 8601 string as an aware datetime (UTC when no offset)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _object(raw: str) -> dict[str, object] | None:
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None
