"""Tests for `bull.Modules.gates.failed`."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.mocks import MockFiles
from bull.Modules.gates.failed import read_failed, write_failed

RESULTS = Path("/tmp/apps/tally/.bull/results/app")
FAILED = RESULTS / "failed.txt"


def test_read_failed_returns_one_id_per_line() -> None:
    files = MockFiles()
    files.texts[FAILED] = "tests/a.py::test_one\ntests/b.py::test_two\n"
    assert read_failed(files, RESULTS) == (
        "tests/a.py::test_one",
        "tests/b.py::test_two",
    )


def test_read_failed_drops_blank_lines_and_surrounding_spaces() -> None:
    files = MockFiles()
    files.texts[FAILED] = "\n  a::one  \n\n   \n\tb::two\t\n"
    assert read_failed(files, RESULTS) == ("a::one", "b::two")


def test_read_failed_missing_file_is_empty() -> None:
    assert read_failed(MockFiles(), RESULTS) == ()


def test_read_failed_empty_file_is_empty() -> None:
    files = MockFiles()
    files.texts[FAILED] = ""
    assert read_failed(files, RESULTS) == ()


def test_write_failed_writes_one_id_per_line_with_trailing_newline() -> None:
    files = MockFiles()
    write_failed(files, RESULTS, ["a::one", "b::two"])
    assert files.texts[FAILED] == "a::one\nb::two\n"


def test_write_failed_with_no_ids_writes_an_empty_file() -> None:
    files = MockFiles()
    files.texts[FAILED] = "old::id\n"
    write_failed(files, RESULTS, [])
    assert files.texts[FAILED] == ""


def test_write_then_read_round_trips() -> None:
    files = MockFiles()
    write_failed(files, RESULTS, ["x::1", "y::2"])
    assert read_failed(files, RESULTS) == ("x::1", "y::2")


def test_written_ids_replace_the_previous_list() -> None:
    files = MockFiles()
    write_failed(files, RESULTS, ["old::1", "old::2"])
    write_failed(files, RESULTS, ["new::1"])
    assert read_failed(files, RESULTS) == ("new::1",)
