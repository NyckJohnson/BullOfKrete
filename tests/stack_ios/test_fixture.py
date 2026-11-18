"""Tests for the ios stack's fixture app (`fixture/`) and the end-to-end self-test."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

import bull.Modules.stack_ios as pkg
from bull.Modules.memo.parser import LiveMemoReader
from bull.Modules.stacks.Contracts import Stack
from bull.Modules.stacks.registry import LiveStackRegistry
from bull.Modules.stacktest.Contracts import CaseVerdict
from bull.Modules.stacktest.runner import LiveStackTester

_FOLDER = Path(pkg.__file__).parent / "ios"
_FIXTURE = _FOLDER / "fixture"
_PROJECT = _FIXTURE / "project"
_APP = _FIXTURE / "app"
_MODULE = _APP / "Modules" / "Counter"
_BULL = (sys.executable, "-m", "bull")
_XCODEPROJ = _PROJECT / "App" / "Fixture" / "Fixture.xcodeproj"

_BANNED = [
    "ios-pipeline",
    ".pipeline/",
    "config.sh",
    "stack.sh",
    "gates.sh",
    "owned_warnings.py",
    "ui-test-writer",
    "UNIT_TEST_TARGET",
    "APP_PROJECT",
    "APP_SCHEME",
    "APP_SOURCE_DIR",
    "APP_TEST_DIR",
    "the pipeline",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    return LiveStackRegistry([], tmp_path_factory.mktemp("userdata")).load_path(_FOLDER)


@pytest.mark.parametrize("folder", ["project", "app", "tests", "ui-tests"])
def test_fixture_has_the_four_folders(folder: str) -> None:
    assert (_FIXTURE / folder).is_dir()


@pytest.mark.parametrize(
    "relative",
    [
        "project/docs/outline.md",
        "project/docs/api/Counter.md",
        "project/.swiftlint.yml",
        "project/.swift-format",
        "app/Modules/Counter/Contracts/CounterStore.swift",
        "app/Modules/Counter/Counter.swift",
        "tests/Counter/CounterTests.swift",
        "ui-tests/JourneyTests.swift",
        "SETUP.md",
    ],
)
def test_fixture_has_the_file(relative: str) -> None:
    assert (_FIXTURE / relative).is_file(), relative


def test_outline_parses_without_problems() -> None:
    reader = LiveMemoReader()
    memo = reader.parse(_read(_PROJECT / "docs" / "outline.md"))
    assert memo.parse_problems == ()
    assert reader.problems(memo, list(memo.parts), 8) == []


def test_outline_has_the_app_opens_journey() -> None:
    memo = LiveMemoReader().parse(_read(_PROJECT / "docs" / "outline.md"))
    assert [(j.number, j.title) for j in memo.journeys] == [(1, "App opens")]


def test_outline_has_the_counter_module_in_two_files_and_the_build_order() -> None:
    memo = LiveMemoReader().parse(_read(_PROJECT / "docs" / "outline.md"))
    assert [m.name for m in memo.modules] == ["Counter"]
    assert memo.modules[0].units == (
        ("Contracts/CounterStore.swift",),
        ("Counter.swift",),
    )
    assert memo.modules[0].depends == ()
    assert [(b.name, b.depends) for b in memo.build_order] == [("Counter", ())]


def test_lint_configs_equal_the_stacks_own() -> None:
    assert _read(_PROJECT / ".swiftlint.yml") == _read(
        _FOLDER / "lint" / "swiftlint.yml"
    )
    assert _read(_PROJECT / ".swift-format") == _read(
        _FOLDER / "lint" / "swift-format.json"
    )


def test_counter_store_protocol_is_sendable_with_value_and_increment() -> None:
    text = _read(_MODULE / "Contracts" / "CounterStore.swift")
    assert re.search(r"protocol\s+CounterStore\s*:\s*Sendable", text)
    assert re.search(r"func\s+value\(\)\s+async\s*->\s*Int", text)
    assert re.search(r"func\s+increment\(\)\s+async\s*->\s*Int", text)


def test_counter_store_carries_the_declarations_only_marker() -> None:
    text = _read(_MODULE / "Contracts" / "CounterStore.swift")
    assert "// coverage-exempt-file: declarations only" in text


def test_counter_is_an_actor_conforming_to_the_protocol() -> None:
    text = _read(_MODULE / "Counter.swift")
    assert re.search(r"actor\s+Counter\s*:\s*CounterStore", text)


def test_counter_takes_its_start_value_in_the_initializer_defaulting_to_zero() -> None:
    text = _read(_MODULE / "Counter.swift")
    assert re.search(r"init\([^)]*=\s*0", text)


def test_counter_tests_are_a_swift_testing_suite() -> None:
    text = _read(_FIXTURE / "tests" / "Counter" / "CounterTests.swift")
    assert re.search(r"@Suite\s+struct\s+CounterTests", text)
    assert "@Test" in text


def test_journey_test_launches_with_ui_testing_argument() -> None:
    text = _read(_FIXTURE / "ui-tests" / "JourneyTests.swift")
    assert "func testJourney1_AppOpens" in text
    assert "-uiTesting" in text


def test_setup_guide_has_its_title_and_the_xcode_steps() -> None:
    text = _read(_FIXTURE / "SETUP.md")
    assert text.startswith("# iOS fixture: the Xcode project (once, by hand)")
    for needle in [
        "mkdir -p src/bull/Modules/stack_ios/ios/fixture/project/App",
        "Product Name",
        "Fixture",
        "Swift Testing with XCUITests",
        "Swift 6",
        "nonisolated",
        "18.0",
        "Shared",
        "Fixture.xcscheme",
        "bull stack test ios",
        "xcuserdata/",
    ]:
        assert needle in text, needle


def test_setup_guide_has_the_repair_section() -> None:
    text = _read(_FIXTURE / "SETUP.md")
    assert "## If the template's tests were deleted in Xcode" in text
    assert "PBXFileSystemSynchronizedRootGroup" in text


@pytest.mark.parametrize(
    "path",
    [
        p
        for p in [_FIXTURE / "SETUP.md", *_FIXTURE.rglob("*")]
        if p.is_file()
        and p.suffix in {".md", ".swift", ".json", ".yml", ".txt"}
        and "App" not in p.relative_to(_FIXTURE).parts[:2]
    ],
    ids=lambda p: str(p.relative_to(_FIXTURE)),
)
def test_fixture_text_has_no_banned_strings(path: Path) -> None:
    text = _read(path)
    for banned in _BANNED:
        assert banned not in text, banned
    assert "/Users/" not in text


@pytest.mark.skipif(
    shutil.which("xcodebuild") is None or shutil.which("swiftlint") is None,
    reason="needs xcodebuild and swiftlint (a Mac with Xcode)",
)
@pytest.mark.skipif(
    not _XCODEPROJ.exists(),
    reason="the fixture's Xcode project is not made yet: follow fixture/SETUP.md",
)
def test_the_real_ios_stack_passes(stack: Stack) -> None:
    report = LiveStackTester(_BULL).run(stack, None)
    assert report.problems == ()
    wrong = [
        f"{r.id}: expected {r.expected}, got {r.got}"
        for r in report.cases
        if r.verdict is not CaseVerdict.PASS
    ]
    assert wrong == []
    assert report.ok
