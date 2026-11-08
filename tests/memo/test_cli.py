"""Tests for `bull.Modules.memo.cli` (`bull template <name>`).

Shapes chosen here (for the code-writer):
  - `register(commands, templates)` adds a `template` parser with one positional `name`;
    `templates` is a zero-argument provider, called only when the command runs.
  - the name is passed through unrestricted (no argparse `choices`): another module may
    register more template names later.
  - `run` writes the template text to `out` exactly (no added newline), returns 0; an
    unknown name raises the provider's BullError and writes nothing.
"""

from __future__ import annotations

import argparse
import io

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.memo.cli import register
from bull.Modules.memo.Contracts import Templates
from bull.Modules.memo.templates import LiveTemplates


class FakeTemplates:
    def __init__(self) -> None:
        self.asked: list[str] = []
        self.texts = {"outline": "# Outline\n\n- one\n", "design": "no newline"}

    def names(self) -> list[str]:
        return sorted(self.texts)

    def text(self, name: str) -> str:
        self.asked.append(name)
        if name not in self.texts:
            raise BullError(
                f"No template {name!r}.", fix="Use one of: design, outline."
            )
        return self.texts[name]


def build(templates: Templates) -> tuple[argparse.ArgumentParser, list[int]]:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    provided: list[int] = []

    def provider() -> Templates:
        provided.append(1)
        return templates

    register(commands, provider)
    return parser, provided


def run(templates: Templates, *argv: str) -> tuple[int, str]:
    parser, _ = build(templates)
    args = parser.parse_args(argv)
    out = io.StringIO()
    code = args.run(args, out)
    return code, out.getvalue()


def test_register_does_not_call_the_provider() -> None:
    parser, provided = build(FakeTemplates())
    parser.parse_args(["template", "outline"])
    assert provided == []


def test_template_writes_the_text_exactly_and_returns_zero() -> None:
    code, text = run(FakeTemplates(), "template", "outline")
    assert code == 0
    assert text == "# Outline\n\n- one\n"


def test_template_adds_no_trailing_newline() -> None:
    _, text = run(FakeTemplates(), "template", "design")
    assert text == "no newline"


def test_template_passes_the_name_through_unrestricted() -> None:
    fake = FakeTemplates()
    code, text = run(fake, "template", "design")
    assert code == 0
    assert text == "no newline"
    assert fake.asked == ["design"]


def test_template_unknown_name_raises_bull_error_and_prints_nothing() -> None:
    parser, _ = build(FakeTemplates())
    args = parser.parse_args(["template", "nope"])
    out = io.StringIO()
    with pytest.raises(BullError):
        args.run(args, out)
    assert out.getvalue() == ""


def test_template_requires_a_name() -> None:
    parser, _ = build(FakeTemplates())
    with pytest.raises(SystemExit):
        parser.parse_args(["template"])


@pytest.mark.parametrize("name", ["outline", "backlog"])
def test_template_prints_the_live_templates(name: str) -> None:
    live = LiveTemplates()
    code, text = run(live, "template", name)
    assert code == 0
    assert text == live.text(name)
