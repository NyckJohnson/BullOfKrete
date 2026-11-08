"""Loads and validates the user, app and part settings files."""

from __future__ import annotations

from collections.abc import Callable

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.settings.Contracts import Settings, SettingsLoader, StackLayer


class LiveSettingsLoader(SettingsLoader):
    def load(
        self, app: AppLayout | None, stack_layer: Callable[[str], StackLayer]
    ) -> Settings:
        raise NotImplementedError(f"{type(self).__name__}.load")
