"""Reads ideas from Markdown and makes slugs."""

from __future__ import annotations

from collections.abc import Collection

from bull.Modules.features.Contracts import Idea, IdeaReader


class LiveIdeaReader(IdeaReader):
    def read(self, text: str, section: str | None = None) -> list[Idea]:
        raise NotImplementedError(f"{type(self).__name__}.read")

    def slug(self, title: str, taken: Collection[str]) -> str:
        raise NotImplementedError(f"{type(self).__name__}.slug")
