"""Tests for the settings contract types."""

from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import (
    ConfigError,
    ConfigProblem,
    Layer,
    Resolved,
    Setting,
    SettingType,
    StackLayer,
)


def test_setting_type_values_match_the_spec() -> None:
    assert {t.name: t.value for t in SettingType} == {
        "INT": "int",
        "BOOL": "bool",
        "STR": "str",
        "CHOICE": "choice",
        "STR_LIST": "list",
    }


def test_layer_values_match_the_spec() -> None:
    assert {layer.name: layer.value for layer in Layer} == {
        "BULL": "bull default",
        "STACK": "stack",
        "USER": "user",
        "APP": "app",
        "PART": "part",
    }


def test_layers_are_declared_in_precedence_order_lowest_first() -> None:
    assert list(Layer) == [Layer.BULL, Layer.STACK, Layer.USER, Layer.APP, Layer.PART]


@pytest.mark.parametrize("layer", list(Layer))
def test_layer_round_trips_through_its_value(layer: Layer) -> None:
    assert Layer(layer.value) is layer


@pytest.mark.parametrize("kind", list(SettingType))
def test_setting_type_round_trips_through_its_value(kind: SettingType) -> None:
    assert SettingType(kind.value) is kind


def test_setting_defaults_for_optional_fields() -> None:
    s = Setting("k", SettingType.STR, "v", "A key.")
    assert s.choices == ()
    assert s.minimum is None
    assert s.maximum is None


def test_setting_is_allowed_in_every_layer_by_default() -> None:
    s = Setting("k", SettingType.STR, "v", "A key.")
    assert s.layers == frozenset(Layer)


def test_setting_can_restrict_its_layers() -> None:
    s = Setting(
        "base_branch",
        SettingType.STR,
        "main",
        "Trunk.",
        layers=frozenset({Layer.USER, Layer.APP}),
    )
    assert s.layers == frozenset({Layer.USER, Layer.APP})


def test_setting_carries_choices_and_range() -> None:
    choice = Setting(
        "review_mode",
        SettingType.CHOICE,
        "combined",
        "d",
        choices=("combined", "split"),
    )
    ranged = Setting("n", SettingType.INT, 5, "d", minimum=1, maximum=100)
    assert choice.choices == ("combined", "split")
    assert (ranged.minimum, ranged.maximum) == (1, 100)


def test_setting_default_may_be_none() -> None:
    assert Setting("stack", SettingType.STR, None, "d").default is None


def test_setting_is_frozen() -> None:
    s = Setting("k", SettingType.STR, "v", "d")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.key = "other"  # type: ignore[misc]


def test_setting_equality_is_by_value() -> None:
    assert Setting("k", SettingType.INT, 1, "d") == Setting(
        "k", SettingType.INT, 1, "d"
    )


def test_resolved_holds_key_value_layer_and_source() -> None:
    r = Resolved("max_attempts", 3, Layer.BULL, None)
    assert (r.key, r.value, r.layer, r.source) == ("max_attempts", 3, Layer.BULL, None)
    r2 = Resolved("k", ("a", "b"), Layer.APP, Path("/x/config.toml"))
    assert r2.value == ("a", "b")
    assert r2.source == Path("/x/config.toml")


def test_resolved_is_frozen() -> None:
    r = Resolved("k", 1, Layer.APP, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.value = 2  # type: ignore[misc]


def test_config_problem_holds_file_line_key_and_message() -> None:
    p = ConfigProblem(Path("/a/config.toml"), 7, "bogus", "unknown setting `bogus`")
    assert p.file == Path("/a/config.toml")
    assert p.line == 7
    assert p.key == "bogus"
    assert p.message == "unknown setting `bogus`"


def test_config_problem_is_frozen() -> None:
    p = ConfigProblem(Path("f"), 0, "k", "m")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.line = 1  # type: ignore[misc]


def test_config_error_is_a_bull_error() -> None:
    assert issubclass(ConfigError, BullError)


def test_config_error_declares_a_problems_list() -> None:
    hints = typing.get_type_hints(ConfigError)
    assert hints["problems"] == list[ConfigProblem]


def test_stack_layer_holds_schema_and_values() -> None:
    schema = (Setting("source_dir", SettingType.STR, "src", "Source."),)
    layer = StackLayer(schema=schema, values={"source_dir": "app"})
    assert layer.schema == schema
    assert layer.values["source_dir"] == "app"


def test_stack_layer_is_frozen() -> None:
    layer = StackLayer(schema=(), values={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        layer.schema = ()  # type: ignore[misc]
