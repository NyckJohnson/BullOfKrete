"""Tests for `bull.Modules.gates.passes`."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from bull.Modules.foundation.mocks import MockClock, MockFiles, sample_layout
from bull.Modules.gates.Contracts import PassRecord
from bull.Modules.gates.passes import LivePassRecords

APP = sample_layout(Path("/tmp/apps/tally"))
SHA = "abc123def456"
PATH = APP.passes_dir / f"{SHA}.json"
TIME = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def make() -> tuple[LivePassRecords, MockFiles, MockClock]:
    files = MockFiles()
    clock = MockClock(TIME)
    return LivePassRecords(files, clock), files, clock


def valid_doc() -> dict[str, object]:
    return {
        "format": 1,
        "sha": SHA,
        "branch": "module/gates",
        "command": "gates gates",
        "time": "2026-11-07T12:00:00Z",
        "parts": ["app", "web"],
    }


def put(files: MockFiles, doc: object) -> None:
    files.texts[PATH] = json.dumps(doc)


def test_record_writes_file_named_after_sha_in_passes_dir() -> None:
    records, files, _ = make()
    records.record(APP, SHA, "module/gates", "gates gates", ["app"])
    assert PATH in files.texts


def test_record_writes_the_documented_json_shape() -> None:
    records, files, _ = make()
    records.record(APP, SHA, "module/gates", "gates gates", ["app", "web"])
    doc = json.loads(files.texts[PATH])
    assert doc == valid_doc()


def test_record_with_no_branch_writes_null() -> None:
    records, files, _ = make()
    records.record(APP, SHA, None, "gates --all", ["app"])
    assert json.loads(files.texts[PATH])["branch"] is None


def test_record_time_is_the_clock_time_in_utc_z_form() -> None:
    records, files, clock = make()
    clock.time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    records.record(APP, SHA, None, "c", [])
    assert json.loads(files.texts[PATH])["time"] == "2026-01-02T03:04:05Z"


def test_record_treats_naive_clock_time_as_utc() -> None:
    records, files, clock = make()
    clock.time = datetime(2026, 1, 2, 3, 4, 5)
    records.record(APP, SHA, None, "c", [])
    assert json.loads(files.texts[PATH])["time"] == "2026-01-02T03:04:05Z"


def test_record_with_no_parts_writes_empty_list() -> None:
    records, files, _ = make()
    records.record(APP, SHA, None, "c", [])
    assert json.loads(files.texts[PATH])["parts"] == []


def test_get_round_trips_a_recorded_pass() -> None:
    records, _, _ = make()
    records.record(APP, SHA, "module/gates", "gates gates", ["app", "web"])
    assert records.get(APP, SHA) == PassRecord(
        sha=SHA,
        branch="module/gates",
        command="gates gates",
        time=TIME,
        parts=("app", "web"),
    )


def test_get_returns_timezone_aware_utc_time() -> None:
    records, files, _ = make()
    put(files, valid_doc())
    got = records.get(APP, SHA)
    assert got is not None
    assert got.time.tzinfo is not None
    assert got.time.utcoffset() == timedelta(0)


def test_get_after_recording_naive_time_is_aware_utc() -> None:
    records, _, clock = make()
    clock.time = datetime(2026, 5, 6, 7, 8, 9)
    records.record(APP, SHA, None, "c", ["app"])
    got = records.get(APP, SHA)
    assert got is not None
    assert got.time == datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


def test_get_converts_non_utc_clock_time_to_the_same_instant() -> None:
    records, _, clock = make()
    zone = timezone(timedelta(hours=2))
    clock.time = datetime(2026, 5, 6, 9, 0, 0, tzinfo=zone)
    records.record(APP, SHA, None, "c", ["app"])
    got = records.get(APP, SHA)
    assert got is not None
    assert got.time == datetime(2026, 5, 6, 7, 0, 0, tzinfo=UTC)


def test_get_null_branch_gives_none_branch() -> None:
    records, files, _ = make()
    doc = valid_doc()
    doc["branch"] = None
    put(files, doc)
    got = records.get(APP, SHA)
    assert got is not None
    assert got.branch is None


def test_get_missing_file_is_none() -> None:
    records, _, _ = make()
    assert records.get(APP, SHA) is None


def test_get_invalid_json_is_none() -> None:
    records, files, _ = make()
    files.texts[PATH] = "{not json"
    assert records.get(APP, SHA) is None


@pytest.mark.parametrize("doc", [[1, 2], "text", 5, None])
def test_get_non_object_is_none(doc: object) -> None:
    records, files, _ = make()
    put(files, doc)
    assert records.get(APP, SHA) is None


@pytest.mark.parametrize("fmt", [2, 0, "1", None])
def test_get_wrong_format_is_none(fmt: object) -> None:
    records, files, _ = make()
    doc = valid_doc()
    doc["format"] = fmt
    put(files, doc)
    assert records.get(APP, SHA) is None


def test_get_missing_format_is_none() -> None:
    records, files, _ = make()
    doc = valid_doc()
    del doc["format"]
    put(files, doc)
    assert records.get(APP, SHA) is None


@pytest.mark.parametrize("field", ["sha", "branch", "command", "time", "parts"])
def test_get_missing_field_is_none(field: str) -> None:
    records, files, _ = make()
    doc = valid_doc()
    del doc[field]
    put(files, doc)
    assert records.get(APP, SHA) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sha", 5),
        ("branch", 5),
        ("command", ["gates"]),
        ("time", 12345),
        ("time", "not a time"),
        ("parts", "app"),
        ("parts", [1, 2]),
    ],
)
def test_get_mistyped_field_is_none(field: str, value: object) -> None:
    records, files, _ = make()
    doc = valid_doc()
    doc[field] = value
    put(files, doc)
    assert records.get(APP, SHA) is None
