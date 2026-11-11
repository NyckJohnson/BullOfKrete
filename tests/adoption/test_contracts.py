"""Tests for the adoption contract types."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from bull.Modules.adoption.Contracts import DetectionReport, LegacyLeft
from bull.Modules.stacks.Contracts import Issue, IssueLevel


def _report(*levels: IssueLevel) -> DetectionReport:
    issues = tuple(
        Issue(level, f"item {i}", "fix it") for i, level in enumerate(levels)
    )
    return DetectionReport(stack="fixture", detection=None, issues=issues)


def test_report_without_issues_is_not_blocked() -> None:
    assert _report().blocked is False


@pytest.mark.parametrize(
    "levels",
    [
        (IssueLevel.NOTE,),
        (IssueLevel.FIX,),
        (IssueLevel.NOTE, IssueLevel.FIX, IssueLevel.NOTE),
    ],
)
def test_report_with_only_fix_or_note_issues_is_not_blocked(
    levels: tuple[IssueLevel, ...],
) -> None:
    assert _report(*levels).blocked is False


@pytest.mark.parametrize(
    "levels",
    [
        (IssueLevel.BLOCK,),
        (IssueLevel.NOTE, IssueLevel.BLOCK),
        (IssueLevel.BLOCK, IssueLevel.FIX, IssueLevel.NOTE),
    ],
)
def test_report_with_any_block_issue_is_blocked(
    levels: tuple[IssueLevel, ...],
) -> None:
    assert _report(*levels).blocked is True


def test_report_with_no_stack_and_block_issue_is_blocked() -> None:
    report = DetectionReport(
        stack=None,
        detection=None,
        issues=(Issue(IssueLevel.BLOCK, "no stack recognizes this project", ""),),
    )
    assert report.blocked is True


def test_detection_report_is_frozen() -> None:
    report = _report()
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.stack = "other"  # type: ignore[misc]


def test_legacy_left_with_everything_empty_is_empty() -> None:
    assert LegacyLeft(files=(), declarations=(), tests=(), memo_files=()).empty is True


@pytest.mark.parametrize("field", ["files", "declarations", "tests", "memo_files"])
def test_legacy_left_with_any_one_field_non_empty_is_not_empty(field: str) -> None:
    kwargs: dict[str, Any] = {
        "files": (),
        "declarations": (),
        "tests": (),
        "memo_files": (),
    }
    kwargs[field] = ("x",)
    assert LegacyLeft(**kwargs).empty is False


def test_legacy_left_with_all_fields_non_empty_is_not_empty() -> None:
    left = LegacyLeft(
        files=("a",), declarations=("b",), tests=("c",), memo_files=("d",)
    )
    assert left.empty is False


def test_legacy_left_is_frozen() -> None:
    left = LegacyLeft(files=(), declarations=(), tests=(), memo_files=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        left.files = ("x",)  # type: ignore[misc]
