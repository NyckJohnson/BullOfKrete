"""The feature cycle: start, plan, accept and abandon."""

from __future__ import annotations

from bull.Modules.features.Contracts import BacklogItem, FeatureCycle, FeaturePlan


class LiveFeatureCycle(FeatureCycle):
    def start(self, slug: str | None = None) -> BacklogItem:
        raise NotImplementedError(f"{type(self).__name__}.start")

    def plan(self) -> FeaturePlan:
        raise NotImplementedError(f"{type(self).__name__}.plan")

    def accept(self) -> BacklogItem:
        raise NotImplementedError(f"{type(self).__name__}.accept")

    def abandon(self) -> BacklogItem:
        raise NotImplementedError(f"{type(self).__name__}.abandon")
