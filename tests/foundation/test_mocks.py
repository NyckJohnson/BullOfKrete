"""Tests for the foundation mocks other modules' tests rely on."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import (
    Clock,
    FileFormatError,
    Files,
    Layouts,
    Runner,
    RunResult,
    Spawned,
)
from bull.Modules.foundation.mocks import (
    SAMPLE_ROOT,
    SAMPLE_TIME,
    MockClock,
    MockFiles,
    MockLayouts,
    MockRunner,
    MockSpawned,
    sample_layout,
)

# --- sample_layout / MockLayouts ---


def test_sample_layout_follows_app_folder_table() -> None:
    root = Path("/r")
    lay = sample_layout(root)
    assert lay.root == root
    assert lay.bull_dir == root / ".bull"
    assert lay.config_file == root / ".bull" / "config.toml"
    assert lay.parts_dir == root / ".bull" / "parts"
    assert lay.status_file == root / ".bull" / "status.json"
    assert lay.backlog_file == root / ".bull" / "backlog.json"
    assert lay.usage_file == root / ".bull" / "usage.json"
    assert lay.events_file == root / ".bull" / "events.jsonl"
    assert lay.passes_dir == root / ".bull" / "passes"
    assert lay.results_dir == root / ".bull" / "results"
    assert lay.plugin_dir == root / ".bull" / "plugin"
    assert lay.run_dir == root / ".bull" / "run"
    assert lay.memo_file == root / "docs" / "outline.md"
    assert lay.api_dir == root / "docs" / "api"
    assert lay.features_dir == root / "docs" / "features"
    assert lay.interfaces_dir == root / "interfaces"


def test_sample_layout_defaults_to_sample_root() -> None:
    assert sample_layout().root == SAMPLE_ROOT


def test_mock_layouts_satisfies_protocol() -> None:
    layouts: Layouts = MockLayouts()
    assert layouts.at(Path("/a")).root == Path("/a")


def test_mock_layouts_at_builds_layout_for_given_root() -> None:
    assert MockLayouts().at(Path("/z")) == sample_layout(Path("/z"))


def test_mock_layouts_find_returns_found_layout() -> None:
    m = MockLayouts(Path("/q"))
    assert m.find(Path("/q/sub")) == sample_layout(Path("/q"))


def test_mock_layouts_find_can_be_scripted_to_none() -> None:
    m = MockLayouts()
    m.found = None
    assert m.find(Path("/anywhere")) is None


def test_mock_layouts_user_dirs_are_absolute_and_distinct() -> None:
    m = MockLayouts()
    assert m.user_config_dir().is_absolute()
    assert m.user_data_dir().is_absolute()
    assert m.user_config_dir() != m.user_data_dir()


def test_mock_layouts_machine_local_ignores_lists_six_lines_in_order() -> None:
    assert MockLayouts().machine_local_ignores() == [
        ".bull/usage.json",
        ".bull/events.jsonl",
        ".bull/passes/",
        ".bull/results/",
        ".bull/plugin/",
        ".bull/run/",
    ]


def test_mock_layouts_records_calls() -> None:
    m = MockLayouts()
    m.at(Path("/a"))
    m.find(Path("/b"))
    m.user_config_dir()
    assert m.calls == [
        ("at", (Path("/a"),)),
        ("find", (Path("/b"),)),
        ("user_config_dir", ()),
    ]


# --- MockFiles ---


def test_mock_files_satisfies_protocol() -> None:
    files: Files = MockFiles()
    assert files.read_text(Path("/x")) is None


def test_mock_files_read_text_missing_is_none() -> None:
    assert MockFiles().read_text(Path("/missing")) is None


def test_mock_files_read_text_returns_preset_content() -> None:
    m = MockFiles()
    m.texts[Path("/a")] = "hello"
    assert m.read_text(Path("/a")) == "hello"


def test_mock_files_write_atomic_stores_text() -> None:
    m = MockFiles()
    m.write_atomic(Path("/a"), "x")
    m.write_atomic(Path("/a"), "y")
    assert m.texts[Path("/a")] == "y"
    assert m.read_text(Path("/a")) == "y"


def test_mock_files_read_json_missing_is_none() -> None:
    assert MockFiles().read_json(Path("/nope")) is None


def test_mock_files_read_json_parses_stored_text() -> None:
    m = MockFiles()
    m.texts[Path("/a.json")] = '{"k": [1, 2]}'
    assert m.read_json(Path("/a.json")) == {"k": [1, 2]}


def test_mock_files_write_json_uses_sorted_indented_with_newline() -> None:
    m = MockFiles()
    m.write_json(Path("/a.json"), {"b": {"z": 1, "y": 2}, "a": [3]})
    assert m.texts[Path("/a.json")] == (
        '{\n  "a": [\n    3\n  ],\n  "b": {\n    "y": 2,\n    "z": 1\n  }\n}\n'
    )


def test_mock_files_read_json_invalid_raises_format_error_naming_path() -> None:
    m = MockFiles()
    path = Path("/bad/file.json")
    m.texts[path] = "{not json"
    with pytest.raises(FileFormatError) as info:
        m.read_json(path)
    assert str(path) in info.value.message


def test_mock_files_json_round_trips() -> None:
    m = MockFiles()
    data = {"format": 1, "items": ["a", "b"]}
    m.write_json(Path("/a.json"), data)
    assert m.read_json(Path("/a.json")) == data


def test_mock_files_append_line_creates_and_appends_with_newline() -> None:
    m = MockFiles()
    m.append_line(Path("/log"), "one")
    m.append_line(Path("/log"), "two")
    assert m.texts[Path("/log")] == "one\ntwo\n"


def test_mock_files_records_calls_in_order() -> None:
    m = MockFiles()
    m.write_atomic(Path("/a"), "t")
    m.read_text(Path("/a"))
    m.append_line(Path("/b"), "l")
    assert [c[0] for c in m.calls] == ["write_atomic", "read_text", "append_line"]
    assert m.calls[0][1] == (Path("/a"), "t")


# --- MockSpawned ---


def test_mock_spawned_satisfies_protocol() -> None:
    s: Spawned = MockSpawned()
    assert isinstance(s.pid, int)


def test_mock_spawned_starts_alive_and_stop_ends_it() -> None:
    s = MockSpawned()
    assert s.alive() is True
    s.stop()
    assert s.alive() is False
    assert s.running is False


def test_mock_spawned_stop_records_grace() -> None:
    s = MockSpawned()
    s.stop(2.5)
    assert ("stop", (2.5,)) in s.calls


def test_mock_spawned_stop_default_grace_is_five() -> None:
    s = MockSpawned()
    s.stop()
    assert ("stop", (5.0,)) in s.calls


def test_mock_spawned_uses_given_pid() -> None:
    assert MockSpawned(pid=7).pid == 7


# --- MockRunner ---


def test_mock_runner_satisfies_protocol() -> None:
    r: Runner = MockRunner()
    assert r.which("git") is not None


def test_mock_runner_run_defaults_to_successful_empty_result() -> None:
    res = MockRunner().run(["echo", "hi"], Path("/cwd"))
    assert res == RunResult(
        argv=("echo", "hi"), returncode=0, stdout="", stderr="", seconds=res.seconds
    )
    assert res.argv == ("echo", "hi")


def test_mock_runner_run_returns_scripted_result_by_first_arg() -> None:
    m = MockRunner()
    scripted = RunResult(
        argv=("git",), returncode=3, stdout="o", stderr="e", seconds=1.0
    )
    m.results["git"] = scripted
    assert m.run(["git", "status"], Path("/c")) is scripted
    assert m.run(["other"], Path("/c")).returncode == 0


def test_mock_runner_run_records_arguments() -> None:
    m = MockRunner()
    m.run(["a", "b"], Path("/c"), env={"K": "V"}, timeout=3.0)
    assert m.calls == [("run", (("a", "b"), Path("/c"), {"K": "V"}, 3.0))]


def test_mock_runner_run_with_empty_argv_does_not_fail() -> None:
    assert MockRunner().run([], Path("/c")).returncode == 0


def test_mock_runner_spawn_returns_alive_tracked_process() -> None:
    m = MockRunner()
    p = m.spawn(["srv"], Path("/c"), env=None, log=Path("/l"))
    assert p.alive() is True
    assert m.spawned == [p]
    assert m.calls[0] == ("spawn", (("srv",), Path("/c"), None, Path("/l")))


def test_mock_runner_spawn_gives_distinct_pids() -> None:
    m = MockRunner()
    a = m.spawn(["a"], Path("/c"))
    b = m.spawn(["b"], Path("/c"))
    assert a.pid != b.pid
    assert len(m.spawned) == 2


def test_mock_runner_which_finds_known_tools() -> None:
    m = MockRunner()
    for tool in ("git", "uv", "claude"):
        assert m.which(tool) is not None


def test_mock_runner_which_unknown_is_none() -> None:
    assert MockRunner().which("no-such-tool") is None


def test_mock_runner_which_follows_edited_tools() -> None:
    m = MockRunner()
    m.tools["foo"] = Path("/bin/foo")
    del m.tools["git"]
    assert m.which("foo") == Path("/bin/foo")
    assert m.which("git") is None
    assert ("which", ("foo",)) in m.calls


# --- MockClock ---


def test_mock_clock_satisfies_protocol() -> None:
    c: Clock = MockClock()
    assert c.now() == SAMPLE_TIME


def test_sample_time_is_timezone_aware_utc() -> None:
    assert SAMPLE_TIME.tzinfo is not None
    assert SAMPLE_TIME.utcoffset() == datetime(2026, 1, 1, tzinfo=UTC).utcoffset()


def test_mock_clock_returns_fixed_time_every_call() -> None:
    c = MockClock()
    assert c.now() == c.now()
    assert len(c.calls) == 2


def test_mock_clock_returns_given_time_and_follows_changes() -> None:
    t = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    c = MockClock(t)
    assert c.now() == t
    c.time = t.replace(year=2021)
    assert c.now().year == 2021


@pytest.mark.parametrize(
    "cls", [MockLayouts, MockFiles, MockRunner, MockClock, MockSpawned]
)
def test_mocks_start_with_no_recorded_calls(cls: type) -> None:
    assert cls().calls == []
