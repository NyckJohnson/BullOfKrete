"""Tests for `bull.Modules.settings.cli` (`bull config show` and `bull config set`).

Shapes chosen here (for the code-writer):
  - `register(commands, settings)` adds a `config` parser with `show` and `set` leaves;
    `settings` is a zero-argument provider, called only when a command runs.
  - text line: `<key> = <value> (<layer>)`, `<layer>` being `Layer.value` ("app", "user",
    "part", "stack", "bull default"); `show` prints one line per Resolved, in order.
  - `--json`: a JSON list of objects `{"key": str, "value": <json>, "layer": Layer.value,
    "source": str path or null}`; tuples become lists. Nothing else is written to `out`.
  - `config set` prints the one resolved line (it takes no `--json`); exit code 0.
  - invalid input raises BullError out of `run`; the module prints nothing for errors.
"""

from __future__ import annotations

import argparse
import io
import json

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.cli import register
from bull.Modules.settings.Contracts import Layer, Settings
from bull.Modules.settings.mocks import SAMPLE_SCHEMA, MockSettings


def build(settings: Settings) -> tuple[argparse.ArgumentParser, list[int]]:
    parser = argparse.ArgumentParser(prog="bull")
    commands = parser.add_subparsers(dest="command")
    provided: list[int] = []

    def provider() -> Settings:
        provided.append(1)
        return settings

    register(commands, provider)
    return parser, provided


def run(settings: Settings, *argv: str) -> tuple[int, str]:
    parser, _ = build(settings)
    args = parser.parse_args(argv)
    out = io.StringIO()
    code = args.run(args, out)
    return code, out.getvalue()


def test_register_does_not_call_the_provider() -> None:
    parser, provided = build(MockSettings())
    parser.parse_args(["config", "show"])
    assert provided == []


def test_config_show_prints_a_sorted_line_per_setting() -> None:
    code, text = run(MockSettings(), "config", "show")
    assert code == 0
    lines = text.splitlines()
    assert [line.split(" = ")[0] for line in lines] == sorted(
        s.key for s in SAMPLE_SCHEMA
    )


def test_config_show_line_has_key_value_and_layer() -> None:
    _, text = run(MockSettings(), "config", "show")
    line = next(x for x in text.splitlines() if x.startswith("max_attempts "))
    assert line.startswith("max_attempts = 3 (")
    assert line.endswith(")")
    assert "bull" in line


def test_config_show_names_the_layer_a_value_came_from() -> None:
    settings = MockSettings()
    settings.app["max_attempts"] = 5
    settings.user["review_mode"] = "split"
    _, text = run(settings, "config", "show")
    lines = text.splitlines()
    assert next(x for x in lines if x.startswith("max_attempts ")).endswith("5 (app)")
    assert next(x for x in lines if x.startswith("review_mode ")).endswith("(user)")


def test_config_show_passes_the_part() -> None:
    settings = MockSettings()
    run(settings, "config", "show", "--part", "api")
    assert ("show", ("api",)) in settings.calls


def test_config_show_without_part_passes_none() -> None:
    settings = MockSettings()
    run(settings, "config", "show")
    assert ("show", (None,)) in settings.calls


def test_config_show_json_is_a_list_of_key_value_layer_source_objects() -> None:
    settings = MockSettings()
    settings.app["max_attempts"] = 5
    code, text = run(settings, "config", "show", "--json")
    assert code == 0
    data = json.loads(text)
    assert [item["key"] for item in data] == sorted(s.key for s in SAMPLE_SCHEMA)
    by_key = {item["key"]: item for item in data}
    assert set(by_key["max_attempts"]) == {"key", "value", "layer", "source"}
    assert by_key["max_attempts"]["value"] == 5
    assert by_key["max_attempts"]["layer"] == Layer.APP.value
    assert by_key["max_attempts"]["source"].endswith(".bull/config.toml")


def test_config_show_json_has_null_source_for_a_default() -> None:
    _, text = run(MockSettings(), "config", "show", "--json")
    by_key = {item["key"]: item for item in json.loads(text)}
    assert by_key["review_mode"]["layer"] == Layer.BULL.value
    assert by_key["review_mode"]["source"] is None


def test_config_show_json_passes_the_part() -> None:
    settings = MockSettings()
    run(settings, "config", "show", "--part", "web", "--json")
    assert ("show", ("web",)) in settings.calls


def test_config_set_prints_the_resolved_line() -> None:
    settings = MockSettings()
    code, text = run(settings, "config", "set", "max_attempts", "5")
    assert code == 0
    assert text.strip() == "max_attempts = 5 (app)"
    assert ("set", ("max_attempts", "5", Layer.APP, None)) in settings.calls


def test_config_set_user_uses_the_user_layer() -> None:
    settings = MockSettings()
    _, text = run(settings, "config", "set", "max_attempts", "2", "--user")
    assert text.strip() == "max_attempts = 2 (user)"
    assert ("set", ("max_attempts", "2", Layer.USER, None)) in settings.calls


def test_config_set_part_uses_the_part_layer() -> None:
    settings = MockSettings()
    _, text = run(settings, "config", "set", "max_attempts", "8", "--part", "api")
    assert text.strip() == "max_attempts = 8 (part)"
    assert ("set", ("max_attempts", "8", Layer.PART, "api")) in settings.calls


def test_config_set_user_and_part_together_are_refused() -> None:
    parser, _ = build(MockSettings())
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["config", "set", "max_attempts", "2", "--user", "--part", "a"]
        )


def test_config_set_invalid_value_raises_bull_error_and_prints_nothing() -> None:
    parser, _ = build(MockSettings())
    args = parser.parse_args(["config", "set", "max_attempts", "many"])
    out = io.StringIO()
    with pytest.raises(BullError):
        args.run(args, out)
    assert out.getvalue() == ""


def test_config_set_unknown_key_raises_bull_error() -> None:
    parser, _ = build(MockSettings())
    args = parser.parse_args(["config", "set", "nope", "1"])
    with pytest.raises(BullError):
        args.run(args, io.StringIO())


def test_config_set_requires_key_and_value() -> None:
    parser, _ = build(MockSettings())
    with pytest.raises(SystemExit):
        parser.parse_args(["config", "set", "max_attempts"])
