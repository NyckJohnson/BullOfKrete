"""Neutrality: bull's own code names no platform-specific tool outside the stack modules."""

from __future__ import annotations

import re
from pathlib import Path

import bull

_BANNED = [
    "Xcode",
    "Swift",
    "SwiftUI",
    "UIKit",
    "iOS",
    "iPhone",
    "simulator",
    "XCUITest",
    "pytest",
    "mypy",
    "ruff",
    "xcodebuild",
]
_PATTERN = re.compile(r"\b(" + "|".join(_BANNED) + r")\b", re.IGNORECASE)


def _package_files() -> list[Path]:
    root = Path(bull.__file__).resolve().parent
    modules = root / "Modules"
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(modules) if modules in path.parents else None
        if relative is not None and relative.parts[0].startswith("stack_"):
            continue
        files.append(path)
    return files


def test_the_neutrality_scan_sees_the_package() -> None:
    names = {path.name for path in _package_files()}

    assert "wiring.py" in names
    assert "__init__.py" in names


def test_no_file_outside_the_stack_modules_names_a_banned_word() -> None:
    found: list[str] = []
    for path in _package_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), start=1):
            match = _PATTERN.search(line)
            if match:
                found.append(f"{path.name}:{number}: {match.group(0)}")

    assert found == []


def test_the_banned_word_pattern_is_case_insensitive_and_whole_word() -> None:
    assert _PATTERN.search("uses XCODE here")
    assert _PATTERN.search("the iOS app")
    assert _PATTERN.search("a Simulator")
    assert not _PATTERN.search("biosphere")
    assert not _PATTERN.search("rubyruff2")
