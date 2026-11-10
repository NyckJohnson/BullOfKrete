"""Tests for `coverage-exempt` marker scanning (`LiveCoverageTriage.markers`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.coverage.Contracts import MarkerScan
from bull.Modules.coverage.triage import LiveCoverageTriage


def _scan(tmp_path: Path, text: str, comment: str = "#") -> tuple[Path, MarkerScan]:
    path = tmp_path / "sample.src"
    path.write_text(text, encoding="utf-8")
    return path, LiveCoverageTriage().markers(path, comment)


def test_line_marker_exempts_its_own_line(tmp_path: Path) -> None:
    path, scan = _scan(tmp_path, "a = 1\nb = 2  # coverage-exempt: defensive\nc = 3\n")
    assert len(scan.exemptions) == 1
    ex = scan.exemptions[0]
    assert ex.path == path
    assert ex.lines == (2,)
    assert ex.reason == "defensive"
    assert scan.invalid == ()


def test_no_markers_gives_empty_scan(tmp_path: Path) -> None:
    _, scan = _scan(tmp_path, "a = 1\nb = 2\n")
    assert scan.exemptions == ()
    assert scan.invalid == ()


def test_empty_file_gives_empty_scan(tmp_path: Path) -> None:
    _, scan = _scan(tmp_path, "")
    assert scan.exemptions == ()
    assert scan.invalid == ()


def test_block_marker_exempts_every_line_inclusive(tmp_path: Path) -> None:
    text = (
        "a = 1\n"
        "# coverage-exempt-begin: platform specific\n"
        "b = 2\n"
        "c = 3\n"
        "# coverage-exempt-end\n"
        "d = 4\n"
    )
    path, scan = _scan(tmp_path, text)
    assert len(scan.exemptions) == 1
    ex = scan.exemptions[0]
    assert ex.path == path
    assert ex.lines == (2, 3, 4, 5)
    assert ex.reason == "platform specific"
    assert scan.invalid == ()


def test_two_blocks_give_two_exemptions(tmp_path: Path) -> None:
    text = (
        "# coverage-exempt-begin: one\n"
        "x = 1\n"
        "# coverage-exempt-end\n"
        "y = 2\n"
        "# coverage-exempt-begin: two\n"
        "z = 3\n"
        "# coverage-exempt-end\n"
    )
    _, scan = _scan(tmp_path, text)
    assert sorted(ex.lines or () for ex in scan.exemptions) == [(1, 2, 3), (5, 6, 7)]
    assert scan.invalid == ()


def test_file_marker_in_first_line_exempts_whole_file(tmp_path: Path) -> None:
    path, scan = _scan(tmp_path, "# coverage-exempt-file: declarations only\nx = 1\n")
    assert len(scan.exemptions) == 1
    ex = scan.exemptions[0]
    assert ex.path == path
    assert ex.lines is None
    assert ex.reason == "declarations only"
    assert scan.invalid == ()


def test_file_marker_on_line_ten_is_accepted(tmp_path: Path) -> None:
    text = "x = 1\n" * 9 + "# coverage-exempt-file: ok\n"
    _, scan = _scan(tmp_path, text)
    assert [ex.lines for ex in scan.exemptions] == [None]


def test_file_marker_after_line_ten_exempts_nothing(tmp_path: Path) -> None:
    text = "x = 1\n" * 10 + "# coverage-exempt-file: too late\n"
    _, scan = _scan(tmp_path, text)
    assert all(ex.lines is not None for ex in scan.exemptions)
    assert not any(ex.lines is None for ex in scan.exemptions)


@pytest.mark.parametrize(
    "line",
    [
        "x = 1  # coverage-exempt:",
        "x = 1  # coverage-exempt:   ",
    ],
)
def test_line_marker_without_reason_is_invalid(tmp_path: Path, line: str) -> None:
    path, scan = _scan(tmp_path, f"a = 1\n{line}\n")
    assert scan.exemptions == ()
    assert len(scan.invalid) == 1
    assert scan.invalid[0].startswith(f"{path}:2:")


def test_begin_without_reason_is_invalid_and_exempts_nothing(tmp_path: Path) -> None:
    text = "# coverage-exempt-begin:\nx = 1\n# coverage-exempt-end\n"
    path, scan = _scan(tmp_path, text)
    assert scan.exemptions == ()
    assert any(msg.startswith(f"{path}:1:") for msg in scan.invalid)


def test_file_marker_without_reason_is_invalid(tmp_path: Path) -> None:
    path, scan = _scan(tmp_path, "# coverage-exempt-file:\nx = 1\n")
    assert scan.exemptions == ()
    assert len(scan.invalid) == 1
    assert scan.invalid[0].startswith(f"{path}:1:")


def test_unclosed_begin_is_invalid_and_exempts_nothing(tmp_path: Path) -> None:
    text = "a = 1\n# coverage-exempt-begin: never closed\nb = 2\nc = 3\n"
    path, scan = _scan(tmp_path, text)
    assert scan.exemptions == ()
    assert len(scan.invalid) == 1
    assert scan.invalid[0].startswith(f"{path}:2:")


def test_stray_end_is_invalid_and_exempts_nothing(tmp_path: Path) -> None:
    text = "a = 1\nb = 2\n# coverage-exempt-end\n"
    path, scan = _scan(tmp_path, text)
    assert scan.exemptions == ()
    assert len(scan.invalid) == 1
    assert scan.invalid[0].startswith(f"{path}:3:")


def test_valid_markers_survive_alongside_invalid_ones(tmp_path: Path) -> None:
    text = "a = 1  # coverage-exempt: fine\nb = 2  # coverage-exempt:\n"
    path, scan = _scan(tmp_path, text)
    assert [ex.lines for ex in scan.exemptions] == [(1,)]
    assert len(scan.invalid) == 1
    assert scan.invalid[0].startswith(f"{path}:2:")


def test_comment_prefix_parameter_selects_marker_syntax(tmp_path: Path) -> None:
    text = "a = 1 // coverage-exempt: slash style\nb = 2 # coverage-exempt: hash\n"
    _, scan = _scan(tmp_path, text, comment="//")
    assert [ex.lines for ex in scan.exemptions] == [(1,)]
    assert scan.exemptions[0].reason == "slash style"


def test_marker_with_other_comment_prefix_is_not_recognised(tmp_path: Path) -> None:
    _, scan = _scan(tmp_path, "a = 1  # coverage-exempt: hash\n", comment="//")
    assert scan.exemptions == ()
    assert scan.invalid == ()


def test_begin_inside_open_block_is_invalid_and_outer_block_continues(
    tmp_path: Path,
) -> None:
    text = (
        "a = 1\n"
        "# coverage-exempt-begin: outer\n"
        "b = 2\n"
        "# coverage-exempt-begin: inner\n"
        "c = 3\n"
        "# coverage-exempt-end\n"
        "d = 4\n"
    )
    path, scan = _scan(tmp_path, text)
    assert scan.invalid == (
        f"{path}:4: coverage-exempt-begin inside an open block",
    )
    assert len(scan.exemptions) == 1
    assert scan.exemptions[0].lines == (2, 3, 4, 5, 6)
    assert scan.exemptions[0].reason == "outer"
