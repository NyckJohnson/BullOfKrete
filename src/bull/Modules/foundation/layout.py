"""The app's file layout: the one place paths are built."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout, Layouts


class LiveLayouts(Layouts):
    def at(self, root: Path) -> AppLayout:
        raise NotImplementedError(f"{type(self).__name__}.at")

    def find(self, start: Path) -> AppLayout | None:
        raise NotImplementedError(f"{type(self).__name__}.find")

    def user_config_dir(self) -> Path:
        raise NotImplementedError(f"{type(self).__name__}.user_config_dir")

    def user_data_dir(self) -> Path:
        raise NotImplementedError(f"{type(self).__name__}.user_data_dir")

    def machine_local_ignores(self) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.machine_local_ignores")
