"""The memo and backlog templates."""

from __future__ import annotations

from bull.Modules.memo.Contracts import Templates


class LiveTemplates(Templates):
    def names(self) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.names")

    def text(self, name: str) -> str:
        raise NotImplementedError(f"{type(self).__name__}.text")
