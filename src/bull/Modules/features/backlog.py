"""The feature backlog in `.bull/backlog.json`."""

from __future__ import annotations

from collections.abc import Sequence

from bull.Modules.features.Contracts import Backlog, BacklogItem, Idea


class LiveBacklog(Backlog):
    def items(self) -> list[BacklogItem]:
        raise NotImplementedError(f"{type(self).__name__}.items")

    def add(self, idea: Idea, top: bool = False) -> BacklogItem:
        raise NotImplementedError(f"{type(self).__name__}.add")

    def import_ideas(self, ideas: Sequence[Idea]) -> list[BacklogItem]:
        raise NotImplementedError(f"{type(self).__name__}.import_ideas")

    def move(self, slug: str, position: int) -> None:
        raise NotImplementedError(f"{type(self).__name__}.move")

    def drop(self, slug: str) -> None:
        raise NotImplementedError(f"{type(self).__name__}.drop")
