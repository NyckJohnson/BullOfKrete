"""Tests for the ios stack's `rules.md`, `setup.md` and lint configs.

The guides are read through the stacks module (`rules`, `setup_guide`); only required headings,
steps and distinctive tokens are checked, never exact prose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import bull.Modules.stack_ios as pkg
from bull.Modules.stacks import docs
from bull.Modules.stacks.Contracts import Stack, StackError
from bull.Modules.stacks.registry import LiveStackRegistry

_FOLDER = Path(pkg.__file__).parent / "ios"

_AGENTS = [
    "skeleton-builder",
    "screen-builder",
    "test-writer",
    "code-writer",
    "reviewer",
    "coverage-analyst",
    "journey-test-writer",
    "surveyor",
]

_BANNED = [
    "ios-pipeline",
    ".pipeline/",
    "config.sh",
    "stack.sh",
    "gates.sh",
    "owned_warnings.py",
    "ui-test-writer",
    "APP_",
    "UNIT_TEST_TARGET",
    "UI_TEST_TARGET",
    "MAX_FILES_PER_UNIT",
    "the pipeline",
]

_ALLOWED_SYMBOLS = {"✅", "✗"}


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    return LiveStackRegistry([], tmp_path_factory.mktemp("userdata")).load_path(_FOLDER)


def _headings(text: str) -> list[str]:
    return [
        m.group(1).strip().lower()
        for m in re.finditer(r"^## (.+)$", text, re.MULTILINE)
    ]


def _read(name: str) -> str:
    return (_FOLDER / name).read_text(encoding="utf-8")


def _is_emoji(ch: str) -> bool:
    code = ord(ch)
    return code >= 0x1F000 or 0x2600 <= code <= 0x27BF or 0x2B00 <= code <= 0x2BFF


# --- rules.md -----------------------------------------------------------------------------


def test_rules_has_the_title() -> None:
    assert _read("rules.md").lstrip().startswith("# iOS stack: rules")


def test_rules_sections_are_in_the_notes_order() -> None:
    assert _headings(_read("rules.md")) == ["common", "outline", *_AGENTS]


def test_rules_has_a_section_for_every_manifest_agent(stack: Stack) -> None:
    headings = _headings(_read("rules.md"))
    assert list(stack.manifest.agents) == _AGENTS
    for agent in stack.manifest.agents:
        assert agent in headings


@pytest.mark.parametrize("agent", _AGENTS)
def test_rules_for_an_agent_are_common_plus_its_section(
    stack: Stack, agent: str
) -> None:
    assert _headings(docs.rules(stack, agent)) == ["common", agent]


def test_rules_for_outline_is_only_the_outline_section(stack: Stack) -> None:
    assert _headings(docs.rules(stack, "outline")) == ["outline"]


def test_rules_for_an_unknown_agent_is_an_error(stack: Stack) -> None:
    with pytest.raises(StackError):
        docs.rules(stack, "ui-test-writer")


_SECTION_TOKENS: dict[str, list[str]] = {
    "common": [
        "Swift 6",
        "SwiftUI",
        "Modules/<Module>/",
        "Contracts/",
        "Mocks/",
        "Views/",
        "<File>Tests.swift",
        "JourneyTests.swift",
        "Swift module",
        "Depends on",
        "Swift API Design Guidelines",
        "import Testing",
        "@testable import",
        "#expect",
        "#require",
        "PRODUCT_MODULE_NAME",
        "XCUITest",
        "try!",
        ".pbxproj",
        "swiftlint lint --strict",
        "xcrun swift-format lint",
        ".swiftlint.yml",
        ".swift-format",
        "bull stack run prune",
        "-uiTesting",
        "AppDependencies.swift",
        "UI: UIKit",
        "UI: SwiftUI",
        "Swift 6 language mode",
    ],
    "outline": [
        "```swift",
        "Sendable",
        "Codable",
        "Equatable",
        "Hashable",
        "Views/<Screen>View.swift",
        "<Screen>ViewModel.swift",
        "minimum iOS",
        "Info.plist",
        "AppDependencies.swift",
        "bull template outline",
        "Legacy files:",
        "Legacy tests:",
        "Callers to repoint:",
        "UI: UIKit",
        "UI: SwiftUI",
        "Views/<Screen>ViewController.swift",
    ],
    "skeleton-builder": [
        "Contracts/",
        'fatalError("Not implemented:',
        "(feature <slug>)",
        "Mock<Protocol>",
        "Mocks/",
        "@Suite struct <File>Tests",
        "@Test func placeholder()",
        "// coverage-exempt-file: declarations only",
        "MANUAL STEPS FOR HUMAN",
        "bull stack setup",
        "LegacyFoo",
        "@objc",
        "AppDependencies.swift",
    ],
    "screen-builder": [
        "Views/<Screen>View.swift",
        "<Screen>ViewModel.swift",
        "@MainActor",
        "@Observable",
        "#Preview",
        "Dynamic Type",
        "dark mode",
        ".accessibilityIdentifier",
        "<screen>.<element>",
        "adopt-identifiers",
        "viewDidLoad",
        "Identity inspector",
    ],
    "test-writer": [
        "@Suite struct <File>Tests",
        "Tests",
        "bull gates <Module> --fast",
        "@Test(arguments:",
        "UUID",
        "xcrun swift-format format -i",
        "swiftlint lint --fix",
        "swiftlint lint --strict",
    ],
    "code-writer": [
        "strict concurrency",
        "@unchecked Sendable",
        "nonisolated(unsafe)",
        "@MainActor",
        "Keychain",
        "UserDefaults",
        "[weak self]",
        "///",
        "bull gates --failed",
        "bull gates <Module> --fast",
        "@IBOutlet private weak var",
        "withObservationTracking",
        "@Observable",
        "AppDependencies",
        "static let shared",
    ],
    "reviewer": [
        "try!",
        "try?",
        "Keychain",
        "HTTPS",
        "ATS",
        "@unchecked Sendable",
        "nonisolated(unsafe)",
        "SCOPE: whole app",
        "Dynamic Type",
        "coverage-exempt-file:",
        "declaration-only",
        "Contracts/",
        "@IBOutlet",
    ],
    "coverage-analyst": [
        "// coverage-exempt:",
        "// coverage-exempt-begin:",
        "// coverage-exempt-end",
        "Files without coverage data",
        "// coverage-exempt-file: declarations only",
        "missed",
        "fatalError",
        "Views/",
        "Mocks/",
    ],
    "journey-test-writer": [
        "JourneyTests.swift",
        "final class JourneyTests: XCTestCase",
        "testJourney1_AddFirstCounter()",
        "accessibilityIdentifier",
        "blocked",
        '["-uiTesting"]',
        "waitForExistence(timeout:)",
        "sleep",
        "BULL_URL_<PART>",
        "ProcessInfo.processInfo.environment",
        "launchEnvironment",
        "adopt-baseline",
    ],
    "surveyor": [
        "NavigationStack",
        "UINavigationController",
        "Interface Builder",
        "storyboard",
        "static let shared",
        "UserDefaults.standard",
        "NotificationCenter.default",
        "Core Data",
        "SwiftData",
        "Keychain",
        "DispatchQueue",
        "async",
    ],
}


@pytest.mark.parametrize(
    ("section", "token"),
    [(s, t) for s, tokens in _SECTION_TOKENS.items() for t in tokens],
)
def test_rules_section_states_the_required_item(
    stack: Stack, section: str, token: str
) -> None:
    assert token in docs.rules(stack, section)


def test_rules_for_an_agent_do_not_include_other_agents_sections(stack: Stack) -> None:
    text = docs.rules(stack, "reviewer")
    assert "journey-test-writer" not in _headings(text)
    assert "BULL_URL_<PART>" not in text


# --- setup.md -----------------------------------------------------------------------------


def _setup_intro() -> str:
    return re.split(r"^## ", _read("setup.md"), maxsplit=1, flags=re.MULTILINE)[0]


def test_setup_has_the_title() -> None:
    assert _read("setup.md").lstrip().startswith("# iOS stack: setup")


def test_setup_has_nine_numbered_steps() -> None:
    numbers = re.findall(r"^\s*(\d+)\. ", _setup_intro(), re.MULTILINE)
    assert [int(n) for n in numbers[:9]] == list(range(1, 10))


@pytest.mark.parametrize(
    "needle",
    [
        "Xcode",
        "Swift Testing with XCUITests",
        "Create Git repository",
        "Swift 6",
        "Swift Language Version",
        "Default Actor Isolation",
        "nonisolated",
        "Shared",
        ".swiftlint.yml",
        ".swift-format",
        "lint/swiftlint.yml",
        "lint/swift-format.json",
        "bull config set",
        "bull stack check",
        "xcuserdata",
        "/bull:skeleton",
    ],
)
def test_setup_states_the_required_step(needle: str) -> None:
    assert needle in _read("setup.md")


@pytest.mark.parametrize(
    "setting",
    [
        "project",
        "scheme",
        "source_dir",
        "test_dir",
        "ui_test_dir",
        "unit_test_target",
        "ui_test_target",
        "simulator",
    ],
)
def test_setup_names_every_setting_to_set(setting: str) -> None:
    assert setting in _setup_intro()


def test_setup_shows_the_lint_configs_content() -> None:
    text = _read("setup.md")
    for needle in (
        "force_unwrapping",
        "implicitly_unwrapped_optional",
        "line_length",
        "lineLength",
        "120",
        "NeverForceUnwrap",
        "NeverUseForceTry",
        "AlwaysUseLowerCamelCase",
    ):
        assert needle in text


def test_setup_has_feature_adoption_and_final_switch_sections() -> None:
    headings = _headings(_read("setup.md"))
    assert "for a feature" in headings
    assert "for an adoption" in headings
    assert "final switch" in headings


def test_setup_guide_returns_the_feature_section(stack: Stack) -> None:
    section = docs.setup_guide(stack, "For a feature")
    assert "capability" in section.lower()
    assert "bull stack check" in section


@pytest.mark.parametrize(
    "needle",
    [
        "bull stack detect --apply",
        "Convert to Folder",
        "Unit Testing Bundle",
        "UI Testing Bundle",
        "Shared",
        "nonisolated",
        "Leave the Swift Language Version",
        "chore: adopt setup",
        "bull stack check",
    ],
)
def test_setup_guide_adoption_section_states_the_step(
    stack: Stack, needle: str
) -> None:
    assert needle.lower() in docs.setup_guide(stack, "For an adoption").lower()


def test_setup_guide_final_switch_section(stack: Stack) -> None:
    section = docs.setup_guide(stack, "Final switch")
    assert "Swift Language Version" in section
    assert "Swift 6" in section
    assert "bull stack check" in section
    assert "bull gates --all" in section


def test_setup_guide_unknown_section_is_an_error(stack: Stack) -> None:
    with pytest.raises(StackError):
        docs.setup_guide(stack, "For a robot")


# --- text rules for every Markdown and lint file ------------------------------------------

_FILES = ["rules.md", "setup.md", "lint/swiftlint.yml", "lint/swift-format.json"]


@pytest.mark.parametrize("name", _FILES)
@pytest.mark.parametrize("banned", _BANNED)
def test_file_has_no_banned_string(name: str, banned: str) -> None:
    assert banned not in _read(name)


@pytest.mark.parametrize("name", _FILES)
def test_file_has_no_absolute_paths(name: str) -> None:
    text = _read(name)
    for prefix in ("/Users/", "/home/", "/private/", "/tmp/", "/var/"):
        assert prefix not in text


@pytest.mark.parametrize("name", _FILES)
def test_file_uses_only_the_check_and_cross_emoji(name: str) -> None:
    found = {ch for ch in _read(name) if _is_emoji(ch)}
    assert found <= _ALLOWED_SYMBOLS


# --- lint/swiftlint.yml -------------------------------------------------------------------


def _swiftlint_lines() -> list[str]:
    lines = []
    for raw in _read("lint/swiftlint.yml").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def _list_under(key: str) -> list[str]:
    items: list[str] = []
    inside = False
    for line in _swiftlint_lines():
        if re.match(r"^\S", line):
            inside = line.startswith(f"{key}:")
            continue
        match = re.match(r"^\s+-\s+(\S+)", line)
        if inside and match:
            items.append(match.group(1))
    return items


def _block_under(key: str) -> list[str]:
    block: list[str] = []
    inside = False
    for line in _swiftlint_lines():
        if re.match(r"^\S", line):
            inside = line.startswith(f"{key}:")
            continue
        if inside:
            block.append(line.strip())
    return block


def test_swiftlint_config_has_the_agreed_top_level_keys() -> None:
    keys = [
        m.group(1)
        for line in _swiftlint_lines()
        if (m := re.match(r"^([A-Za-z_]+):", line))
    ]
    assert keys == ["disabled_rules", "opt_in_rules", "line_length", "identifier_name"]


def test_swiftlint_config_disables_trailing_comma_and_todo() -> None:
    assert _list_under("disabled_rules") == ["trailing_comma", "todo"]


def test_swiftlint_config_opts_in_to_the_agreed_rules() -> None:
    assert sorted(_list_under("opt_in_rules")) == sorted(
        [
            "force_unwrapping",
            "implicitly_unwrapped_optional",
            "empty_count",
            "first_where",
            "contains_over_first_not_nil",
            "redundant_nil_coalescing",
        ]
    )


def test_swiftlint_config_line_length_warns_at_120_and_ignores_comments() -> None:
    block = _block_under("line_length")
    assert "warning: 120" in block
    assert "ignores_comments: true" in block


def test_swiftlint_config_identifier_names_allow_short_ids() -> None:
    block = _block_under("identifier_name")
    assert "min_length: 1" in block
    excluded = next(b for b in block if b.startswith("excluded:"))
    assert re.findall(r"\w+", excluded.split(":", 1)[1]) == ["id", "x", "y"]


# --- lint/swift-format.json ---------------------------------------------------------------


def test_swift_format_config_is_the_agreed_json() -> None:
    assert json.loads(_read("lint/swift-format.json")) == {
        "version": 1,
        "lineLength": 120,
        "indentation": {"spaces": 4},
        "maximumBlankLines": 1,
        "respectsExistingLineBreaks": True,
        "lineBreakBeforeEachArgument": False,
        "rules": {
            "AlwaysUseLowerCamelCase": False,
            "NeverForceUnwrap": True,
            "NeverUseForceTry": True,
        },
    }
