"""Tests for the settings mocks other modules' tests rely on."""

from __future__ import annotations

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
