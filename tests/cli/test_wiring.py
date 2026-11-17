"""Tests for `bull.Modules.cli.wiring`: the composition root and the command table."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

import bull
from bull.Modules.claude_code.mocks import MockProvider
from bull.Modules.cli import wiring
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.hooks.mocks import MockHooks

_COMMANDS = [
    "init",
    "open",
    "doctor",
    "status",
    "feature",
    "adopt",
    "gates",
    "coverage",
    "api",
    "stacks",
    "stack",
    "part",
    "config",
    "migrate",
    "template",
    "hook",
    "statusline",
]

_STACK_LEAVES = [
    "select",
    "rules",
    "setup",
    "check",
    "run",
    "install",
    "test",
    "detect",
]


def _table() -> argparse._SubParsersAction[argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)
    return commands


# --- building ---------------------------------------------------------------------------


def test_the_real_implementations_are_built_once_per_process() -> None:
    assert wiring.get_wiring() is wiring.get_wiring()


def test_the_wiring_provides_what_main_needs() -> None:
    built = wiring.get_wiring()

    for name in (
        "layouts",
        "formats",
        "settings_loader",
        "stack_layer",
        "register_commands",
        "provider",
        "hooks",
    ):
        assert hasattr(built, name), name


def test_builtin_stack_roots_are_the_stack_folders_under_modules() -> None:
    modules = Path(bull.__file__).resolve().parent / "Modules"

    roots = [Path(p).resolve() for p in wiring.builtin_stack_roots()]

    assert roots
    for root in roots:
        assert root.is_dir()
        assert root.parent.parent == modules
        assert root.parent.name.startswith("stack_")
    names = {root.name for root in roots}
    assert {"fixture", "fixture_service", "ios", "python_cli"} <= names


def test_builtin_stack_roots_hold_no_folder_outside_the_stack_modules() -> None:
    roots = [Path(p).resolve() for p in wiring.builtin_stack_roots()]

    assert all(root.parent.name.startswith("stack_") for root in roots)
    assert len(roots) == len(set(roots))


# --- the command table ------------------------------------------------------------------


@pytest.mark.parametrize("command", _COMMANDS)
def test_the_command_table_holds_every_command_of_the_commands_table(
    command: str,
) -> None:
    assert command in _table().choices


@pytest.mark.parametrize("leaf", _STACK_LEAVES)
def test_the_stack_command_has_every_subcommand_of_the_commands_table(
    leaf: str, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)

    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["stack", leaf, "--help"])

    assert raised.value.code == 0
    assert capsys.readouterr().out != ""


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "usage-check", "--help"],
        ["status", "ref", "trunk", "--help"],
        ["feature", "add", "--help"],
        ["adopt", "start", "--help"],
        ["part", "list", "--help"],
        ["config", "show", "--help"],
        ["open", "--help"],
        ["gates", "--help"],
        ["api", "--help"],
    ],
)
def test_subcommands_of_the_commands_table_parse(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)

    with pytest.raises(SystemExit) as raised:
        parser.parse_args(argv)

    assert raised.value.code == 0
    assert capsys.readouterr().out != ""


def test_every_registered_leaf_command_has_a_run_function() -> None:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    wiring.get_wiring().register_commands(commands)

    args = parser.parse_args(["config", "show"])

    assert callable(args.run)


# --- hook entry points ------------------------------------------------------------------


class _Hooks(MockHooks):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[HookEvent] = []

    def handle(self, event: HookEvent) -> HookDecision:
        self.events.append(event)
        return super().handle(event)


class _BadHooks(MockHooks):
    def handle(self, event: HookEvent) -> HookDecision:
        raise RuntimeError("safeguard exploded")


class _BadParse(MockProvider):
    def parse_hook(self, kind: HookKind, raw: str) -> HookEvent:
        raise ValueError("not json")


def _hook(
    kind: str,
    raw: str = "{}",
    *,
    provider: MockProvider | None = None,
    hooks: MockHooks | None = None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = wiring.run_hook(
        kind,
        raw,
        out,
        err,
        provider=provider or MockProvider(),
        hooks=hooks or MockHooks(),
    )
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("session-start", HookKind.SESSION_START),
        ("before-agent", HookKind.BEFORE_AGENT),
        ("before-shell", HookKind.BEFORE_SHELL),
        ("before-edit", HookKind.BEFORE_EDIT),
        ("before-read", HookKind.BEFORE_READ),
        ("agent-end", HookKind.AGENT_END),
    ],
)
def test_a_hook_is_parsed_by_the_provider_and_handled_as_its_kind(
    name: str, kind: HookKind
) -> None:
    provider, hooks = MockProvider(), _Hooks()

    code, _, _ = _hook(name, '{"x": 1}', provider=provider, hooks=hooks)

    assert code == 0
    assert ("parse_hook", (kind, '{"x": 1}')) in provider.calls
    assert [event.kind for event in hooks.events] == [kind]


def test_a_hook_decision_goes_out_through_the_provider() -> None:
    hooks = MockHooks()

    code, out, _ = _hook("session-start", hooks=hooks)

    assert code == 0
    assert "stage 5" in out


def test_a_blocking_hook_decision_uses_the_providers_exit_code_and_stderr() -> None:
    hooks = MockHooks()
    hooks.decision = HookDecision(False, "blocked: merge needs a gate pass")

    code, out, err = _hook("before-shell", hooks=hooks)

    assert code == 2
    assert out == ""
    assert "blocked: merge needs a gate pass" in err


def test_a_hook_whose_input_cannot_be_parsed_allows_and_reports_on_stderr() -> None:
    code, out, err = _hook("before-shell", provider=_BadParse())

    assert code == 0
    assert out == ""
    assert "not json" in err


def test_a_hook_that_raises_allows_and_reports_on_stderr() -> None:
    code, out, err = _hook("before-edit", hooks=_BadHooks())

    assert code == 0
    assert out == ""
    assert "safeguard exploded" in err


def test_a_hook_that_raises_still_allows_session_start() -> None:
    code, _, err = _hook("session-start", hooks=_BadHooks())

    assert code == 0
    assert "safeguard exploded" in err
