"""The app's file layout: the one place paths are built."""

from __future__ import annotations

import os
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout, Layouts

_BULL = ".bull"
_STATUS = "status.json"
_APP_NAME = "bull"

# Machine-local `.gitignore` lines, in the order the memo's App folder table lists them.
_MACHINE_LOCAL_IGNORES = (
    ".bull/usage.json",
    ".bull/events.jsonl",
    ".bull/passes/",
    ".bull/results/",
    ".bull/plugin/",
    ".bull/run/",
)


def _xdg_dir(variable: str, fallback: Path) -> Path:
    """`$<variable>/bull` when the variable holds an absolute path, else `fallback/bull`."""
    value = os.environ.get(variable, "")
    if value and Path(value).is_absolute():
        return Path(value) / _APP_NAME
    return fallback / _APP_NAME


class LiveLayouts(Layouts):
    def at(self, root: Path) -> AppLayout:
        root = root.resolve()
        bull = root / _BULL
        docs = root / "docs"
        return AppLayout(
            root=root,
            bull_dir=bull,
            config_file=bull / "config.toml",
            parts_dir=bull / "parts",
            status_file=bull / _STATUS,
            backlog_file=bull / "backlog.json",
            usage_file=bull / "usage.json",
            events_file=bull / "events.jsonl",
            passes_dir=bull / "passes",
            results_dir=bull / "results",
            plugin_dir=bull / "plugin",
            run_dir=bull / "run",
            memo_file=docs / "outline.md",
            api_dir=docs / "api",
            features_dir=docs / "features",
            interfaces_dir=root / "interfaces",
        )

    def find(self, start: Path) -> AppLayout | None:
        start = start.resolve()
        for folder in (start, *start.parents):
            if (folder / _BULL / _STATUS).is_file():
                return self.at(folder)
        return None

    def user_config_dir(self) -> Path:
        return _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")

    def user_data_dir(self) -> Path:
        return _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share")

    def machine_local_ignores(self) -> list[str]:
        return list(_MACHINE_LOCAL_IGNORES)
