"""Tests for `bull.Modules.cli.help`: the command list grouped as in the Commands table."""

from __future__ import annotations

import pytest

from bull.Modules.cli.help import render_help

# Top-level commands in the order the Commands table lists them (first appearance).
_TABLE_ORDER = [
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
    "part",
    "config",
    "migrate",
    "template",
    "hook",
    "statusline",
    "help",
]


def _first_tokens(text: str) -> list[str]:
    """The first word of every non-empty line, with a leading `bull` dropped."""
    tokens: list[str] = []
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "bull" and len(words) > 1:
            words = words[1:]
        tokens.append(words[0])
    return tokens


def test_help_is_non_empty_text_ending_in_a_newline() -> None:
    text = render_help()

    assert text.strip() != ""
    assert text.endswith("\n")


@pytest.mark.parametrize("command", _TABLE_ORDER + ["stack"])
def test_help_lists_every_command(command: str) -> None:
    assert command in _first_tokens(render_help())


def test_help_lists_commands_in_the_order_of_the_commands_table() -> None:
    tokens = _first_tokens(render_help())

    positions = [tokens.index(command) for command in _TABLE_ORDER]

    assert positions == sorted(positions)


@pytest.mark.parametrize(
    "fragment",
    ["--version", "--json", "--print-command", "usage-check", "init-modules"],
)
def test_help_mentions_the_options_and_subcommands_of_the_table(fragment: str) -> None:
    assert fragment in render_help()


def test_help_mentions_the_stack_subcommands() -> None:
    text = render_help()

    for word in ("select", "rules", "setup", "check", "install", "test"):
        assert word in text


def test_help_is_the_same_every_time() -> None:
    assert render_help() == render_help()
