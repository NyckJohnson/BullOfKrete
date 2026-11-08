"""Tests for `bull.Modules.settings.schema` (bull's own settings keys).

Module-internal API under test (defined by these tests):
    BULL_SCHEMA: tuple[Setting, ...]
    find_setting(key: str) -> Setting | None      # also resolves any `models.<agent>`
    parse_value(setting: Setting, raw: str) -> SettingValue   # raises BullError
"""

from __future__ import annotations

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import Layer, Setting, SettingType
from bull.Modules.settings.schema import BULL_SCHEMA, find_setting, parse_value

FILE_LAYERS = frozenset({Layer.STACK, Layer.USER, Layer.APP, Layer.PART})
SONNET_AGENTS = (
    "test-writer",
    "reviewer",
    "coverage-analyst",
    "journey-test-writer",
    "surveyor",
    "legacy-test-scanner",
)


def _get(key: str) -> Setting:
    setting = find_setting(key)
    assert setting is not None, key
    return setting


def _file_layers(setting: Setting) -> frozenset[Layer]:
    return setting.layers & FILE_LAYERS


def test_schema_keys_are_unique() -> None:
    keys = [s.key for s in BULL_SCHEMA]
    assert len(keys) == len(set(keys))


def test_schema_entries_have_descriptions() -> None:
    assert all(s.description for s in BULL_SCHEMA)


def test_format_is_not_a_setting() -> None:
    assert find_setting("format") is None
    assert "format" not in [s.key for s in BULL_SCHEMA]


def test_unknown_key_is_not_found() -> None:
    assert find_setting("no_such_key") is None


def test_base_branch_is_a_str_defaulting_to_main_for_user_and_app() -> None:
    s = _get("base_branch")
    assert s.type is SettingType.STR
    assert s.default == "main"
    assert _file_layers(s) == {Layer.USER, Layer.APP}


def test_review_mode_is_a_choice_of_combined_or_split_in_all_layers() -> None:
    s = _get("review_mode")
    assert s.type is SettingType.CHOICE
    assert s.default == "combined"
    assert set(s.choices) == {"combined", "split"}
    assert _file_layers(s) == FILE_LAYERS


@pytest.mark.parametrize(("key", "default"), [("max_attempts", 3), ("max_files_per_unit", 4)])
def test_count_settings_are_ints_at_least_one_in_all_layers(key: str, default: int) -> None:
    s = _get(key)
    assert s.type is SettingType.INT
    assert s.default == default
    assert s.minimum == 1
    assert _file_layers(s) == FILE_LAYERS


@pytest.mark.parametrize(("key", "default"), [("usage.pause_5h", 85), ("usage.pause_weekly", 95)])
def test_usage_thresholds_are_ints_1_to_100_for_user_and_app(key: str, default: int) -> None:
    s = _get(key)
    assert s.type is SettingType.INT
    assert s.default == default
    assert (s.minimum, s.maximum) == (1, 100)
    assert _file_layers(s) == {Layer.USER, Layer.APP}


def test_coverage_exclude_is_a_list_set_by_stack_app_and_part() -> None:
    s = _get("coverage.exclude")
    assert s.type is SettingType.STR_LIST
    assert s.default is None  # comes from the stack
    assert _file_layers(s) == {Layer.STACK, Layer.APP, Layer.PART}


def test_coverage_exclude_extra_is_an_empty_list_for_app_and_part() -> None:
    s = _get("coverage.exclude_extra")
    assert s.type is SettingType.STR_LIST
    assert s.default == ()
    assert _file_layers(s) == {Layer.APP, Layer.PART}


def test_reference_dir_defaults_to_reference_for_app_only() -> None:
    s = _get("reference_dir")
    assert s.type is SettingType.STR
    assert s.default == "reference"
    assert _file_layers(s) == {Layer.APP}


def test_bookkeeping_paths_default_to_bull_and_docs_for_app_only() -> None:
    s = _get("bookkeeping_paths")
    assert s.type is SettingType.STR_LIST
    assert s.default == (".bull/", "docs/")
    assert _file_layers(s) == {Layer.APP}


def test_stack_is_a_str_without_default_for_app_and_part() -> None:
    s = _get("stack")
    assert s.type is SettingType.STR
    assert s.default is None
    assert _file_layers(s) == {Layer.APP, Layer.PART}


def test_dir_defaults_to_dot_for_part_only() -> None:
    s = _get("dir")
    assert s.type is SettingType.STR
    assert s.default == "."
    assert _file_layers(s) == {Layer.PART}


@pytest.mark.parametrize("agent", SONNET_AGENTS)
def test_sonnet_agents_default_to_sonnet(agent: str) -> None:
    s = _get(f"models.{agent}")
    assert s.type is SettingType.STR
    assert s.default == "sonnet"
    assert _file_layers(s) == {Layer.USER, Layer.APP}


@pytest.mark.parametrize("agent", ["code-writer", "skeleton-builder", "anything-else"])
def test_other_agents_default_to_inherit(agent: str) -> None:
    s = _get(f"models.{agent}")
    assert s.key == f"models.{agent}"
    assert s.type is SettingType.STR
    assert s.default == "inherit"
    assert _file_layers(s) == {Layer.USER, Layer.APP}


def test_bare_models_key_is_not_a_setting() -> None:
    assert find_setting("models.") is None
    assert find_setting("models") is None


# ---- parse_value ----


def test_parse_int_returns_an_int() -> None:
    assert parse_value(_get("max_attempts"), "5") == 5


@pytest.mark.parametrize("raw", ["many", "", "1.5", "0", "-2"])
def test_parse_int_rejects_non_integers_and_below_minimum(raw: str) -> None:
    with pytest.raises(BullError) as err:
        parse_value(_get("max_attempts"), raw)
    assert err.value.message == "max_attempts must be an integer ≥ 1"


def test_parse_int_accepts_the_range_bounds() -> None:
    s = _get("usage.pause_5h")
    assert parse_value(s, "1") == 1
    assert parse_value(s, "100") == 100


@pytest.mark.parametrize("raw", ["0", "101", "abc"])
def test_parse_int_rejects_values_outside_the_range_naming_it(raw: str) -> None:
    with pytest.raises(BullError) as err:
        parse_value(_get("usage.pause_5h"), raw)
    message = err.value.message
    assert "usage.pause_5h" in message
    assert "integer" in message
    assert "1" in message and "100" in message


def test_parse_choice_accepts_a_listed_choice() -> None:
    assert parse_value(_get("review_mode"), "split") == "split"


def test_parse_choice_rejects_others_naming_the_choices() -> None:
    with pytest.raises(BullError) as err:
        parse_value(_get("review_mode"), "both")
    message = err.value.message
    assert "review_mode" in message
    assert "combined" in message and "split" in message


def test_parse_str_returns_the_raw_text() -> None:
    assert parse_value(_get("base_branch"), "develop") == "develop"


def test_parse_list_splits_on_commas_and_strips_spaces() -> None:
    assert parse_value(_get("coverage.exclude"), "*/mocks/*, build/*,x") == (
        "*/mocks/*",
        "build/*",
        "x",
    )


def test_parse_list_single_item() -> None:
    assert parse_value(_get("bookkeeping_paths"), "docs/") == ("docs/",)


def test_parse_list_empty_text_is_the_empty_tuple() -> None:
    assert parse_value(_get("coverage.exclude_extra"), "") == ()


def test_parse_bool_accepts_true_and_false() -> None:
    flag = Setting(key="flag", type=SettingType.BOOL, default=False, description="d")
    assert parse_value(flag, "true") is True
    assert parse_value(flag, "false") is False


@pytest.mark.parametrize("raw", ["yes", "1", "", "TRUE-ish"])
def test_parse_bool_rejects_other_text(raw: str) -> None:
    flag = Setting(key="flag", type=SettingType.BOOL, default=False, description="d")
    with pytest.raises(BullError) as err:
        parse_value(flag, raw)
    assert "flag" in err.value.message
    assert "true" in err.value.message and "false" in err.value.message


def test_parse_works_for_a_stack_declared_setting() -> None:
    s = Setting(key="source_dir", type=SettingType.STR, default="src", description="d")
    assert parse_value(s, "lib") == "lib"
