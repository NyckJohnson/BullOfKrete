"""Tests for `bull.Modules.stack_ios.ios.pbxproj`.

Choices where the spec is open: `parse(text: str) -> dict[str, Any]` returns the file's top-level
dictionary (dicts as `dict`, lists as `list`, every scalar as `str`, comments dropped);
`build_setting(project, target, key, configuration="Debug") -> str | None` takes that parsed
dictionary and a native target's name and returns the target's value for `key` in the named build
configuration, falling back to the project's own build settings, or None when neither sets it;
malformed input raises `PbxprojError` (a `ValueError`).
"""

from __future__ import annotations

from typing import Any

import pytest

from bull.Modules.stack_ios.ios import pbxproj

_HEADER = "// !$*UTF8*$!\n"


def _wrap(objects: str, root: str = "P1") -> str:
    return (
        _HEADER
        + "{\n\tarchiveVersion = 1;\n\tobjects = {\n"
        + objects
        + f"\n\t}};\n\trootObject = {root} /* Project object */;\n}}\n"
    )


_PROJECT = """
\t\tP1 /* Project object */ = {
\t\t\tisa = PBXProject;
\t\t\tbuildConfigurationList = PCL /* Build configuration list for PBXProject "MyApp" */;
\t\t\ttargets = (
\t\t\t\tT1 /* MyApp */,
\t\t\t\tT2 /* MyAppTests */,
\t\t\t);
\t\t};
\t\tPCL = {
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (PD, PR);
\t\t};
\t\tPD = {
\t\t\tisa = XCBuildConfiguration;
\t\t\tname = Debug;
\t\t\tbuildSettings = {
\t\t\t\tSWIFT_VERSION = 5.0;
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t\tONLY_IN_DEBUG = YES;
\t\t\t};
\t\t};
\t\tPR = {
\t\t\tisa = XCBuildConfiguration;
\t\t\tname = Release;
\t\t\tbuildSettings = {
\t\t\t\tSWIFT_VERSION = 5.0;
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t};
\t\t};
\t\tT1 /* MyApp */ = {
\t\t\tisa = PBXNativeTarget;
\t\t\tname = MyApp;
\t\t\tbuildConfigurationList = T1L;
\t\t};
\t\tT1L = {
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (T1D, T1R);
\t\t};
\t\tT1D = {
\t\t\tisa = XCBuildConfiguration;
\t\t\tname = Debug;
\t\t\tbuildSettings = {
\t\t\t\tSWIFT_VERSION = 6.0;
\t\t\t\tPRODUCT_NAME = "$(TARGET_NAME)";
\t\t\t};
\t\t};
\t\tT1R = {
\t\t\tisa = XCBuildConfiguration;
\t\t\tname = Release;
\t\t\tbuildSettings = {
\t\t\t\tSWIFT_VERSION = 6.0;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = "-O";
\t\t\t};
\t\t};
\t\tT2 /* MyAppTests */ = {
\t\t\tisa = PBXNativeTarget;
\t\t\tname = MyAppTests;
\t\t\tbuildConfigurationList = T2L;
\t\t};
\t\tT2L = {
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (T2D);
\t\t};
\t\tT2D = {
\t\t\tisa = XCBuildConfiguration;
\t\t\tname = Debug;
\t\t\tbuildSettings = {
\t\t\t\tPRODUCT_NAME = "$(TARGET_NAME)";
\t\t\t};
\t\t};
"""


def _project() -> dict[str, Any]:
    return pbxproj.parse(_wrap(_PROJECT))


# --- parse ---------------------------------------------------------------------------------


def test_parse_returns_the_top_level_dictionary() -> None:
    root = _project()
    assert root["archiveVersion"] == "1"
    assert root["rootObject"] == "P1"
    assert root["objects"]["P1"]["isa"] == "PBXProject"


def test_parse_drops_line_and_block_comments() -> None:
    text = (
        "// !$*UTF8*$!\n"
        "{ /* a block comment */\n"
        "\tkey = value; // trailing comment\n"
        "\tother /* inline */ = /* before */ thing /* after */;\n"
        "}\n"
    )
    assert pbxproj.parse(text) == {"key": "value", "other": "thing"}


def test_parse_reads_quoted_strings_with_spaces() -> None:
    assert pbxproj.parse('{ name = "My App"; }') == {"name": "My App"}


def test_parse_unescapes_quotes_inside_quoted_strings() -> None:
    assert pbxproj.parse(r'{ shell = "echo \"hi\" there"; }') == {
        "shell": 'echo "hi" there'
    }


def test_parse_keeps_comment_markers_inside_quoted_strings() -> None:
    parsed = pbxproj.parse(
        '{ url = "https://example.com/a"; note = "see /* not a comment */ ok"; }'
    )
    assert parsed["url"] == "https://example.com/a"
    assert parsed["note"] == "see /* not a comment */ ok"


def test_parse_keeps_semicolons_and_braces_inside_quoted_strings() -> None:
    assert pbxproj.parse('{ script = "if (a) { b; }"; }') == {"script": "if (a) { b; }"}


def test_parse_reads_unquoted_values_as_strings() -> None:
    parsed = pbxproj.parse("{ SWIFT_VERSION = 6.0; path = Sources/App.swift; }")
    assert parsed == {"SWIFT_VERSION": "6.0", "path": "Sources/App.swift"}


def test_parse_reads_lists_with_trailing_commas_and_comments() -> None:
    parsed = pbxproj.parse('{ children = (\n\tA /* first */,\n\t"B C",\n\tD,\n); }')
    assert parsed == {"children": ["A", "B C", "D"]}


def test_parse_reads_empty_lists_and_dictionaries() -> None:
    assert pbxproj.parse("{ files = (); settings = {}; }") == {
        "files": [],
        "settings": {},
    }


def test_parse_reads_nested_dictionaries_and_lists() -> None:
    parsed = pbxproj.parse("{ outer = { inner = { deep = ( one, { k = v; } ); }; }; }")
    assert parsed == {"outer": {"inner": {"deep": ["one", {"k": "v"}]}}}


def test_parse_reads_quoted_keys() -> None:
    parsed = pbxproj.parse(
        '{ "CODE_SIGN_IDENTITY[sdk=iphoneos*]" = "iPhone Developer"; }'
    )
    assert parsed == {"CODE_SIGN_IDENTITY[sdk=iphoneos*]": "iPhone Developer"}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n",
        "// only a comment\n",
        "{ key = value;",
        "{ key = value }",
        "{ key value; }",
        '{ key = "unterminated; }',
        "{ key = ( a, b; }",
        "{ key = value; } }",
        "{ key = value; } trailing",
        "{ /* never closed key = value; }",
        "{ key = ; }",
        "not a plist at all",
    ],
)
def test_parse_raises_pbxproj_error_on_malformed_input(text: str) -> None:
    with pytest.raises(pbxproj.PbxprojError):
        pbxproj.parse(text)


# --- build_setting -------------------------------------------------------------------------


def test_target_setting_wins_over_the_project_setting() -> None:
    assert pbxproj.build_setting(_project(), "MyApp", "SWIFT_VERSION") == "6.0"


def test_target_setting_falls_back_to_the_project_setting() -> None:
    project = _project()
    assert pbxproj.build_setting(project, "MyAppTests", "SWIFT_VERSION") == "5.0"
    assert (
        pbxproj.build_setting(project, "MyApp", "IPHONEOS_DEPLOYMENT_TARGET") == "17.0"
    )


def test_a_setting_only_the_target_has_is_found() -> None:
    assert (
        pbxproj.build_setting(_project(), "MyApp", "PRODUCT_NAME") == "$(TARGET_NAME)"
    )


def test_a_setting_nobody_sets_is_none() -> None:
    assert pbxproj.build_setting(_project(), "MyApp", "NO_SUCH_SETTING") is None


def test_build_setting_reads_the_named_configuration() -> None:
    project = _project()
    assert pbxproj.build_setting(project, "MyApp", "SWIFT_OPTIMIZATION_LEVEL") is None
    assert (
        pbxproj.build_setting(
            project, "MyApp", "SWIFT_OPTIMIZATION_LEVEL", configuration="Release"
        )
        == "-O"
    )


def test_project_fallback_uses_the_same_configuration() -> None:
    project = _project()
    assert pbxproj.build_setting(project, "MyAppTests", "ONLY_IN_DEBUG") == "YES"
    assert (
        pbxproj.build_setting(
            project, "MyAppTests", "ONLY_IN_DEBUG", configuration="Release"
        )
        is None
    )


# --- pathological nesting ------------------------------------------------------------------

_DEPTH = 5000


@pytest.mark.parametrize(
    "text",
    [
        "{ a = " * _DEPTH + "x; " + "}; " * (_DEPTH - 1) + "}",
        "{ a = " + "( " * _DEPTH + "x" + " )" * _DEPTH + "; }",
        "{ a = " * _DEPTH,
        "{ a = " + "( " * _DEPTH,
    ],
    ids=["nested-dicts", "nested-lists", "unclosed-dicts", "unclosed-lists"],
)
def test_parse_raises_pbxproj_error_on_deeply_nested_input(text: str) -> None:
    with pytest.raises(pbxproj.PbxprojError):
        pbxproj.parse(text)


# --- coverage triage: build_setting with odd structures -------------------------------------


def _mini(**values: str) -> dict[str, Any]:
    """A parsed project whose target `T` and project `ROOT` each have one Debug config."""
    return {
        "rootObject": "ROOT",
        "objects": {
            "ROOT": {"isa": "PBXProject", "buildConfigurationList": "PL"},
            "PL": {"isa": "XCConfigurationList", "buildConfigurations": ["PD"]},
            "PD": {
                "isa": "XCBuildConfiguration",
                "name": "Debug",
                "buildSettings": dict(values),
            },
            "T": {
                "isa": "PBXNativeTarget",
                "name": "T",
                "buildConfigurationList": "TL",
            },
            "TL": {"isa": "XCConfigurationList", "buildConfigurations": ["TD"]},
            "TD": {
                "isa": "XCBuildConfiguration",
                "name": "Debug",
                "buildSettings": dict(values),
            },
        },
    }


def _no_objects(p: dict[str, Any]) -> None:
    p["objects"] = "nope"


def _no_root(p: dict[str, Any]) -> None:
    del p["rootObject"]
    p["objects"]["TD"]["buildSettings"] = {}


def _no_config_list(p: dict[str, Any]) -> None:
    del p["objects"]["T"]["buildConfigurationList"]
    del p["objects"]["ROOT"]["buildConfigurationList"]


def _configs_not_a_list(p: dict[str, Any]) -> None:
    p["objects"]["TL"]["buildConfigurations"] = "TD"
    p["objects"]["PL"]["buildConfigurations"] = "PD"


def _settings_not_a_dict(p: dict[str, Any]) -> None:
    p["objects"]["TD"]["buildSettings"] = "nope"
    p["objects"]["PD"]["buildSettings"] = "nope"


@pytest.mark.parametrize(
    "damage",
    [_no_objects, _no_root, _no_config_list, _configs_not_a_list, _settings_not_a_dict],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_build_setting_is_none_for_odd_project_structures(damage: Any) -> None:
    project = _mini(KEY="value")
    damage(project)
    assert pbxproj.build_setting(project, "T", "KEY") is None


def test_build_setting_is_none_when_neither_target_nor_project_sets_the_key() -> None:
    assert pbxproj.build_setting(_mini(OTHER="x"), "T", "KEY") is None


def test_build_setting_reads_the_target_value_in_the_plain_structure() -> None:
    assert pbxproj.build_setting(_mini(KEY="value"), "T", "KEY") == "value"


def test_parse_rejects_a_quoted_string_ending_in_a_lone_backslash() -> None:
    with pytest.raises(pbxproj.PbxprojError):
        pbxproj.parse('{ a = "abc\\')
