"""Tests for the settings mocks other modules' tests rely on."""

from __future__ import annotations

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import (
    Layer,
    Resolved,
    Setting,
    Settings,
    SettingsLoader,
    StackLayer,
)
from bull.Modules.settings.mocks import MockSettings, MockSettingsLoader


def _no_stack(name: str) -> StackLayer:
    return StackLayer(schema=(), values={})


def test_mock_settings_satisfies_the_protocol() -> None:
    settings: Settings = MockSettings()
    assert isinstance(settings.schema(), list)


def test_mock_schema_returns_settings_with_unique_keys() -> None:
    schema = MockSettings().schema()
    assert schema
    assert all(isinstance(s, Setting) for s in schema)
    keys = [s.key for s in schema]
    assert len(keys) == len(set(keys))


def test_mock_schema_returns_a_copy() -> None:
    mock = MockSettings()
    mock.schema().clear()
    assert mock.schema()


def test_mock_get_returns_the_bull_default_for_a_schema_key() -> None:
    mock = MockSettings()
    assert mock.get("max_attempts") == 3
    assert mock.get("max_files_per_unit") == 4
    assert mock.get("review_mode") == "combined"
    assert mock.get("base_branch") == "main"
    assert mock.get("usage.pause_5h") == 85
    assert mock.get("usage.pause_weekly") == 95


def test_mock_get_accepts_a_part() -> None:
    assert MockSettings().get("max_attempts", part="app") == 3


def test_mock_show_lists_every_key_sorted_with_resolved_entries() -> None:
    shown = MockSettings().show()
    assert all(isinstance(r, Resolved) for r in shown)
    keys = [r.key for r in shown]
    assert keys == sorted(keys)
    assert {"max_attempts", "review_mode", "base_branch"} <= set(keys)


def test_mock_show_reports_defaults_from_the_bull_layer() -> None:
    by_key = {r.key: r for r in MockSettings().show()}
    assert by_key["max_attempts"].value == 3
    assert by_key["max_attempts"].layer is Layer.BULL


def test_mock_set_returns_the_resolved_value_in_the_requested_layer() -> None:
    result = MockSettings().set("max_attempts", "5", Layer.USER)
    assert result.key == "max_attempts"
    assert result.value == 5
    assert result.layer is Layer.USER


def test_mock_set_defaults_to_the_app_layer() -> None:
    assert MockSettings().set("review_mode", "split").layer is Layer.APP


def test_mock_set_is_visible_to_later_get_and_show() -> None:
    mock = MockSettings()
    mock.set("review_mode", "split")
    assert mock.get("review_mode") == "split"
    shown = {r.key: r for r in mock.show()}
    assert shown["review_mode"].value == "split"
    assert shown["review_mode"].layer is Layer.APP


def test_mock_records_calls_in_order() -> None:
    mock = MockSettings()
    mock.schema()
    mock.get("max_attempts")
    mock.show()
    mock.set("max_attempts", "2")
    assert [name for name, _ in mock.calls] == ["schema", "get", "show", "set"]


def test_mock_loader_satisfies_the_protocol() -> None:
    loader: SettingsLoader = MockSettingsLoader()
    assert isinstance(loader.load(None, _no_stack), MockSettings)


def test_mock_loader_returns_the_settings_it_was_given() -> None:
    settings = MockSettings()
    assert MockSettingsLoader(settings).load(None, _no_stack) is settings


def test_mock_loader_records_load_calls() -> None:
    loader = MockSettingsLoader()
    loader.load(None, _no_stack)
    loader.load(None, _no_stack)
    assert [name for name, _ in loader.calls] == ["load", "load"]


# --- failure behavior -------------------------------------------------------


def test_mock_get_unknown_key_raises_bull_error() -> None:
    with pytest.raises(BullError):
        MockSettings().get("no.such.key")


def test_mock_set_unknown_key_raises_bull_error() -> None:
    with pytest.raises(BullError):
        MockSettings().set("no.such.key", "1")


def test_mock_set_int_setting_parses_digits_to_int() -> None:
    result = MockSettings().set("max_files_per_unit", "7")
    assert result.value == 7
    assert isinstance(result.value, int)


def test_mock_set_str_setting_keeps_numeric_looking_text_as_str() -> None:
    mock = MockSettings()
    assert mock.set("base_branch", "123").value == "123"
    assert mock.get("base_branch") == "123"


def test_mock_set_str_setting_stores_text() -> None:
    assert MockSettings().set("base_branch", "develop").value == "develop"


def test_mock_set_choice_accepts_a_listed_choice() -> None:
    assert MockSettings().set("review_mode", "split").value == "split"


def test_mock_set_choice_rejects_a_value_not_in_choices() -> None:
    mock = MockSettings()
    with pytest.raises(BullError):
        mock.set("review_mode", "bogus")
    assert mock.get("review_mode") == "combined"


def test_mock_set_int_rejects_non_integer_with_expected_message() -> None:
    mock = MockSettings()
    with pytest.raises(BullError) as info:
        mock.set("max_attempts", "many")
    assert info.value.message == "max_attempts must be an integer \u2265 1"
    assert mock.get("max_attempts") == 3


@pytest.mark.parametrize("raw", ["0", "-1", "-5", "", "1.5"])
def test_mock_set_int_rejects_values_below_minimum_or_malformed(raw: str) -> None:
    mock = MockSettings()
    with pytest.raises(BullError):
        mock.set("max_attempts", raw)
    assert mock.get("max_attempts") == 3


@pytest.mark.parametrize("raw", ["500", "101", "0", "-3"])
def test_mock_set_rejects_usage_values_outside_1_to_100(raw: str) -> None:
    mock = MockSettings()
    with pytest.raises(BullError):
        mock.set("usage.pause_5h", raw)
    assert mock.get("usage.pause_5h") == 85


@pytest.mark.parametrize("raw", ["1", "100"])
def test_mock_set_accepts_usage_range_boundaries(raw: str) -> None:
    assert MockSettings().set("usage.pause_5h", raw).value == int(raw)


@pytest.mark.parametrize(
    "key", ["base_branch", "usage.pause_5h", "usage.pause_weekly"]
)
def test_mock_set_rejects_part_layer_for_user_and_app_only_keys(key: str) -> None:
    raw = "x" if key == "base_branch" else "50"
    mock = MockSettings()
    before = mock.get(key)
    with pytest.raises(BullError):
        mock.set(key, raw, layer=Layer.PART, part="p")
    assert mock.get(key) == before


def test_mock_set_rejects_layers_outside_each_settings_layers() -> None:
    samples = {
        "base_branch": "x",
        "review_mode": "split",
        "max_attempts": "2",
        "max_files_per_unit": "2",
        "usage.pause_5h": "50",
        "usage.pause_weekly": "50",
        "models.reviewer": "opus",
    }
    for setting in MockSettings().schema():
        for layer in Layer:
            if layer in setting.layers:
                continue
            with pytest.raises(BullError):
                MockSettings().set(setting.key, samples[setting.key], layer=layer)


# --- part layering ----------------------------------------------------------


def test_mock_part_layer_value_is_seen_for_that_part_only() -> None:
    mock = MockSettings()
    mock.set("max_attempts", "9", layer=Layer.PART, part="p")
    assert mock.get("max_attempts", part="p") == 9
    assert mock.get("max_attempts") == 3
    assert mock.get("max_attempts", part="other") == 3


def test_mock_part_layer_value_does_not_change_app_level_show() -> None:
    mock = MockSettings()
    mock.set("max_attempts", "9", layer=Layer.PART, part="p")
    by_key = {r.key: r for r in mock.show()}
    assert by_key["max_attempts"].value == 3
    assert by_key["max_attempts"].layer is Layer.BULL


def test_mock_show_for_a_part_reports_the_part_value_and_layer() -> None:
    mock = MockSettings()
    mock.set("max_attempts", "9", layer=Layer.PART, part="p")
    by_key = {r.key: r for r in mock.show(part="p")}
    assert by_key["max_attempts"].value == 9
    assert by_key["max_attempts"].layer is Layer.PART


def test_mock_part_value_overrides_an_app_value_for_that_part() -> None:
    mock = MockSettings()
    mock.set("max_attempts", "5", layer=Layer.APP)
    mock.set("max_attempts", "9", layer=Layer.PART, part="p")
    assert mock.get("max_attempts") == 5
    assert mock.get("max_attempts", part="p") == 9


# --- sources ----------------------------------------------------------------


def test_mock_set_reports_a_different_source_per_layer() -> None:
    mock = MockSettings()
    user = mock.set("max_attempts", "2", layer=Layer.USER).source
    app = mock.set("max_attempts", "2", layer=Layer.APP).source
    part = mock.set("max_attempts", "2", layer=Layer.PART, part="p").source
    assert user is not None and app is not None and part is not None
    assert len({user, app, part}) == 3


def test_mock_set_source_follows_the_spec_file_naming() -> None:
    mock = MockSettings()
    app = mock.set("max_attempts", "2", layer=Layer.APP).source
    part = mock.set("max_attempts", "2", layer=Layer.PART, part="p").source
    user = mock.set("max_attempts", "2", layer=Layer.USER).source
    assert app is not None and part is not None and user is not None
    assert app.parts[-2:] == (".bull", "config.toml")
    assert part.parts[-3:] == (".bull", "parts", "p.toml")
    assert user.name == "config.toml"
    assert ".bull" not in user.parts


def test_mock_show_reports_the_same_source_as_set_for_the_app_layer() -> None:
    mock = MockSettings()
    set_source = mock.set("max_attempts", "2", layer=Layer.APP).source
    shown = {r.key: r for r in mock.show()}["max_attempts"]
    assert shown.source == set_source


def test_mock_show_reports_the_same_source_as_set_for_the_user_layer() -> None:
    mock = MockSettings()
    set_source = mock.set("review_mode", "split", layer=Layer.USER).source
    shown = {r.key: r for r in mock.show()}["review_mode"]
    assert shown.layer is Layer.USER
    assert shown.source == set_source


def test_mock_show_reports_the_same_source_as_set_for_the_part_layer() -> None:
    mock = MockSettings()
    set_source = mock.set("max_attempts", "2", layer=Layer.PART, part="p").source
    shown = {r.key: r for r in mock.show(part="p")}["max_attempts"]
    assert shown.source == set_source
