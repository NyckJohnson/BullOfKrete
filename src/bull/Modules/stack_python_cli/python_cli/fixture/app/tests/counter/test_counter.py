"""Tests for the counter: start value, increment, and the count kept in the folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from fixture_cli.Modules.counter.counter import FileCounter


def test_a_new_counter_starts_at_zero(tmp_path: Path) -> None:
    assert FileCounter(tmp_path).value() == 0


@pytest.mark.parametrize("start", [0, 5, -2])
def test_a_new_counter_starts_at_its_start_value(tmp_path: Path, start: int) -> None:
    assert FileCounter(tmp_path, start).value() == start


def test_increment_adds_one(tmp_path: Path) -> None:
    counter = FileCounter(tmp_path, 3)
    assert counter.increment() == 4
    assert counter.value() == 4


def test_the_count_is_kept_in_the_folder(tmp_path: Path) -> None:
    FileCounter(tmp_path).increment()
    FileCounter(tmp_path).increment()
    assert FileCounter(tmp_path).value() == 2
