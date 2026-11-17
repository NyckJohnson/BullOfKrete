"""Tests for the claude_code contract types."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bull.Modules.claude_code.Contracts import HookOutput, Provider, StatusLineInput
from bull.Modules.usage.Contracts import UsageSample

_SAMPLE = UsageSample(
    time=datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC),
    five_hour=10.0,
    weekly=20.0,
    five_hour_resets=None,
    weekly_resets=None,
)


def test_hook_output_holds_stdout_stderr_and_exit_code() -> None:
    out = HookOutput(stdout="o", stderr="e", exit_code=2)
    assert (out.stdout, out.stderr, out.exit_code) == ("o", "e", 2)


def test_hook_output_is_frozen() -> None:
    out = HookOutput("", "", 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.exit_code = 1  # type: ignore[misc]


def test_hook_output_equality_is_by_value() -> None:
    assert HookOutput("a", "b", 0) == HookOutput("a", "b", 0)
    assert HookOutput("a", "b", 0) != HookOutput("a", "b", 2)


def test_status_line_input_holds_cwd_and_usage() -> None:
    value = StatusLineInput(cwd=Path("/tmp/app"), usage=_SAMPLE)
    assert value.cwd == Path("/tmp/app")
    assert value.usage == _SAMPLE


def test_status_line_input_allows_missing_usage() -> None:
    assert StatusLineInput(cwd=Path("."), usage=None).usage is None


def test_status_line_input_is_frozen() -> None:
    value = StatusLineInput(cwd=Path("."), usage=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.cwd = Path("/x")  # type: ignore[misc]


def test_status_line_input_equality_is_by_value() -> None:
    assert StatusLineInput(Path("."), None) == StatusLineInput(Path("."), None)
    assert StatusLineInput(Path("."), None) != StatusLineInput(Path("/x"), None)


def test_provider_is_a_protocol() -> None:
    assert getattr(Provider, "_is_protocol", False) is True


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("render_plugin", ["self", "dest", "settings", "version"]),
        ("launch_argv", ["self", "app", "extra"]),
        ("tool_check", ["self"]),
        ("parse_hook", ["self", "kind", "raw"]),
        ("hook_output", ["self", "kind", "decision"]),
        ("parse_statusline", ["self", "raw"]),
        ("app_files", ["self", "app"]),
    ],
)
def test_provider_declares_method_with_spec_parameters(
    method: str, params: list[str]
) -> None:
    func = getattr(Provider, method)
    assert list(inspect.signature(func).parameters) == params


def test_provider_declares_name_attribute() -> None:
    assert "name" in Provider.__annotations__
