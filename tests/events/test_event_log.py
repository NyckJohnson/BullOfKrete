"""Tests for `bull.Modules.events.event_log`.

Decision for the code-writer: `LiveEventLog(path, files, clock)` takes the events file path,
a foundation `Files` and a foundation `Clock`; tests pass them by keyword (`path=`, `files=`,
`clock=`). `time` is written as an ISO-8601 string that `datetime.fromisoformat` parses back
to the clock's instant.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bull.Modules.events.Contracts import EventKind, EventLog, EventValue
from bull.Modules.events.event_log import LiveEventLog
from bull.Modules.foundation.Contracts import Files
from bull.Modules.foundation.mocks import MockClock, MockFiles

WHEN = datetime(2026, 11, 7, 12, 30, 45, tzinfo=UTC)


class RaisingFiles(MockFiles):
    def append_line(self, path: Path, line: str) -> None:
        raise OSError("read-only")


def make(path: Path, files: Files | None = None, when: datetime = WHEN) -> LiveEventLog:
    return LiveEventLog(path=path, files=files or MockFiles(), clock=MockClock(when))


def lines(files: MockFiles, path: Path) -> list[str]:
    return files.texts[path].splitlines()


def test_live_event_log_satisfies_the_protocol(tmp_path: Path) -> None:
    log: EventLog = make(tmp_path / "events.jsonl")
    assert log.read() == []


def test_append_writes_one_json_line_with_time_kind_and_data(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    make(path, files).append(EventKind.GATE_STEP, step="build", seconds=1.5)
    (line,) = lines(files, path)
    obj = json.loads(line)
    assert obj["kind"] == "gate_step"
    assert obj["step"] == "build"
    assert obj["seconds"] == 1.5
    assert set(obj) == {"time", "kind", "step", "seconds"}


def test_append_time_comes_from_the_clock_as_iso_8601(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    make(path, files).append(EventKind.STATUS)
    obj = json.loads(lines(files, path)[0])
    assert datetime.fromisoformat(obj["time"]) == WHEN


def test_append_without_data_writes_only_time_and_kind(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    make(path, files).append(EventKind.RESUME)
    assert set(json.loads(lines(files, path)[0])) == {"time", "kind"}


def test_append_adds_lines_in_call_order(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    log = make(path, files)
    log.append(EventKind.PAUSE, n=1)
    log.append(EventKind.RESUME, n=2)
    assert [json.loads(x)["n"] for x in lines(files, path)] == [1, 2]


@pytest.mark.parametrize("value", ["text", "", 0, -3, 42, 2.5, True, False, None])
def test_append_data_values_round_trip(tmp_path: Path, value: EventValue) -> None:
    log = make(tmp_path / "events.jsonl")
    log.append(EventKind.DECISION, v=value)
    (event,) = log.read()
    assert event.data["v"] == value
    assert type(event.data["v"]) is type(value)


def test_append_writes_through_to_a_real_file(tmp_path: Path) -> None:
    from bull.Modules.foundation.files import LiveFiles

    path = tmp_path / ".bull" / "events.jsonl"
    log = LiveEventLog(path=path, files=LiveFiles(), clock=MockClock(WHEN))
    log.append(EventKind.STATUS, what="unit")
    log.append(EventKind.PAUSE, reason="usage")
    assert len(path.read_text().splitlines()) == 2
    assert [e.kind for e in log.read()] == [EventKind.STATUS, EventKind.PAUSE]


def test_append_to_unwritable_path_never_raises(tmp_path: Path) -> None:
    from bull.Modules.foundation.files import LiveFiles

    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    log = LiveEventLog(
        path=blocker / "events.jsonl", files=LiveFiles(), clock=MockClock(WHEN)
    )
    log.append(EventKind.STATUS, what="x")
    assert log.read() == []


def test_append_when_files_raises_never_raises(tmp_path: Path) -> None:
    make(tmp_path / "events.jsonl", RaisingFiles()).append(EventKind.STATUS)


_WARN_SCRIPT = """
import sys
from pathlib import Path
from bull.Modules.events.Contracts import EventKind
from bull.Modules.events.event_log import LiveEventLog
from bull.Modules.foundation.files import LiveFiles
from bull.Modules.foundation.mocks import MockClock

blocker = Path(sys.argv[1])
blocker.write_text("not a folder")
a = LiveEventLog(path=blocker / "e.jsonl", files=LiveFiles(), clock=MockClock())
b = LiveEventLog(path=blocker / "f.jsonl", files=LiveFiles(), clock=MockClock())
for _ in range(3):
    a.append(EventKind.STATUS, n=1)
b.append(EventKind.PAUSE)
"""


def _run_failing_process(tmp_path: Path, name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _WARN_SCRIPT, str(tmp_path / name)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_unwritable_appends_warn_exactly_once_per_process_on_stderr(
    tmp_path: Path,
) -> None:
    result = _run_failing_process(tmp_path, "blocker")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert len([x for x in result.stderr.splitlines() if x.strip()]) == 1


def test_a_new_process_warns_again(tmp_path: Path) -> None:
    first = _run_failing_process(tmp_path, "one")
    second = _run_failing_process(tmp_path, "two")
    assert first.stderr.strip() != ""
    assert second.stderr.strip() != ""


def test_successful_append_writes_nothing_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    make(tmp_path / "events.jsonl").append(EventKind.STATUS)
    assert capsys.readouterr().err == ""


def test_read_returns_events_in_file_order(tmp_path: Path) -> None:
    log = make(tmp_path / "events.jsonl")
    log.append(EventKind.AGENT_START, agent="a")
    log.append(EventKind.AGENT_END, agent="a")
    log.append(EventKind.HOOK_BLOCK, why="b")
    events = log.read()
    assert [e.kind for e in events] == [
        EventKind.AGENT_START,
        EventKind.AGENT_END,
        EventKind.HOOK_BLOCK,
    ]
    assert events[0].time == WHEN
    assert dict(events[2].data) == {"why": "b"}


def test_read_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert make(tmp_path / "absent.jsonl").read() == []


def test_read_empty_file_returns_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    files.texts[path] = ""
    assert make(path, files).read() == []


def test_read_skips_blank_and_unparseable_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    good1 = json.dumps({"time": WHEN.isoformat(), "kind": "pause", "n": 1})
    good2 = json.dumps({"time": WHEN.isoformat(), "kind": "resume", "n": 2})
    files.texts[path] = f'{good1}\n\n   \n{{not json\n{good2}\ntruncated {{"time"\n'
    events = make(path, files).read()
    assert [e.kind for e in events] == [EventKind.PAUSE, EventKind.RESUME]
    assert [e.data["n"] for e in events] == [1, 2]


def test_read_separates_time_and_kind_from_data(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    files.texts[path] = (
        json.dumps({"time": WHEN.isoformat(), "kind": "status", "module": "m"}) + "\n"
    )
    (event,) = make(path, files).read()
    assert event.time == WHEN
    assert dict(event.data) == {"module": "m"}


def _line(**fields: object) -> str:
    return json.dumps({"time": WHEN.isoformat(), "kind": "status", **fields})


@pytest.mark.parametrize(
    "bad",
    [
        "[1, 2]",
        '"x"',
        "42",
        "null",
        '{"kind": "status"}',
        json.dumps({"time": WHEN.isoformat()}),
        json.dumps({"time": WHEN.isoformat(), "kind": 5}),
        json.dumps({"time": 5, "kind": "status"}),
        json.dumps({"time": None, "kind": "status"}),
        json.dumps({"time": "yesterday", "kind": "status"}),
        json.dumps({"time": WHEN.isoformat(), "kind": "bogus"}),
        _line(items=[1, 2]),
        _line(nested={"a": 1}),
    ],
)
def test_read_skips_invalid_line_between_valid_ones(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    files.texts[path] = "\n".join([_line(n=1), bad, _line(n=2)]) + "\n"
    events = make(path, files).read()
    assert [e.data["n"] for e in events] == [1, 2]


def test_append_data_key_named_time_keeps_the_clock_time(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    files = MockFiles()
    make(path, files).append(EventKind.STATUS, time="bogus")
    obj = json.loads(lines(files, path)[0])
    assert datetime.fromisoformat(obj["time"]) == WHEN


def test_read_propagates_os_errors_other_than_missing_path(tmp_path: Path) -> None:
    class DeniedFiles(MockFiles):
        def read_text(self, path: Path) -> str | None:
            raise PermissionError("denied")

    with pytest.raises(PermissionError):
        make(tmp_path / "events.jsonl", DeniedFiles()).read()
