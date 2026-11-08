"""Mocks of the foundation contracts, for tests and previews."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from bull.Modules.foundation.Contracts import (
    AppLayout,
    Clock,
    Files,
    Layouts,
    RunResult,
    Runner,
    Spawned,
)

SAMPLE_ROOT = Path("/tmp/apps/tally")
SAMPLE_TIME = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def sample_layout(root: Path = SAMPLE_ROOT) -> AppLayout:
    """A layout for `root` following the App folder table."""
    bull = root / ".bull"
    return AppLayout(
        root=root,
        bull_dir=bull,
        config_file=bull / "config.toml",
        parts_dir=bull / "parts",
        status_file=bull / "status.json",
        backlog_file=bull / "backlog.json",
        usage_file=bull / "usage.json",
        events_file=bull / "events.jsonl",
        passes_dir=bull / "passes",
        results_dir=bull / "results",
        plugin_dir=bull / "plugin",
        run_dir=bull / "run",
        memo_file=root / "docs" / "outline.md",
        api_dir=root / "docs" / "api",
        features_dir=root / "docs" / "features",
        interfaces_dir=root / "interfaces",
    )


class MockLayouts(Layouts):
    def __init__(self, root: Path = SAMPLE_ROOT) -> None:
        self.root = root
        self.found: AppLayout | None = sample_layout(root)
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def at(self, root: Path) -> AppLayout:
        self.calls.append(("at", (root,)))
        return sample_layout(root)

    def find(self, start: Path) -> AppLayout | None:
        self.calls.append(("find", (start,)))
        return self.found

    def user_config_dir(self) -> Path:
        self.calls.append(("user_config_dir", ()))
        return Path("/tmp/home/.config/bull")

    def user_data_dir(self) -> Path:
        self.calls.append(("user_data_dir", ()))
        return Path("/tmp/home/.local/share/bull")

    def machine_local_ignores(self) -> list[str]:
        self.calls.append(("machine_local_ignores", ()))
        return [
            ".bull/usage.json",
            ".bull/events.jsonl",
            ".bull/passes/",
            ".bull/results/",
            ".bull/plugin/",
            ".bull/run/",
        ]


class MockFiles(Files):
    """An in-memory file system: `texts` maps paths to their content."""

    def __init__(self) -> None:
        self.texts: dict[Path, str] = {}
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def read_text(self, path: Path) -> str | None:
        self.calls.append(("read_text", (path,)))
        return self.texts.get(path)

    def write_atomic(self, path: Path, text: str) -> None:
        self.calls.append(("write_atomic", (path, text)))
        self.texts[path] = text

    def read_json(self, path: Path) -> object | None:
        self.calls.append(("read_json", (path,)))
        text = self.texts.get(path)
        return None if text is None else json.loads(text)

    def write_json(self, path: Path, data: object) -> None:
        self.calls.append(("write_json", (path, data)))
        self.texts[path] = json.dumps(data, indent=2, sort_keys=True) + "\n"

    def append_line(self, path: Path, line: str) -> None:
        self.calls.append(("append_line", (path, line)))
        self.texts[path] = self.texts.get(path, "") + line + "\n"


class MockSpawned(Spawned):
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.running = True
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def alive(self) -> bool:
        self.calls.append(("alive", ()))
        return self.running

    def stop(self, grace: float = 5.0) -> None:
        self.calls.append(("stop", (grace,)))
        self.running = False


class MockRunner(Runner):
    """Returns `results[argv[0]]` when set, else a successful empty run."""

    def __init__(self) -> None:
        self.results: dict[str, RunResult] = {}
        self.tools: dict[str, Path] = {
            "git": Path("/usr/bin/git"),
            "uv": Path("/opt/homebrew/bin/uv"),
            "claude": Path("/usr/local/bin/claude"),
        }
        self.spawned: list[MockSpawned] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        self.calls.append(("run", (tuple(argv), cwd, env, timeout)))
        if argv and argv[0] in self.results:
            return self.results[argv[0]]
        return RunResult(
            argv=tuple(argv), returncode=0, stdout="", stderr="", seconds=0.01
        )

    def spawn(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
        log: Path | None = None,
    ) -> Spawned:
        self.calls.append(("spawn", (tuple(argv), cwd, env, log)))
        process = MockSpawned(pid=4242 + len(self.spawned))
        self.spawned.append(process)
        return process

    def which(self, tool: str) -> Path | None:
        self.calls.append(("which", (tool,)))
        return self.tools.get(tool)


class MockClock(Clock):
    def __init__(self, time: datetime = SAMPLE_TIME) -> None:
        self.time = time
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def now(self) -> datetime:
        self.calls.append(("now", ()))
        return self.time
