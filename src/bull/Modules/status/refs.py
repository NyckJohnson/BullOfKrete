"""Branch and tag names for the current mode."""

from __future__ import annotations

from bull.Modules.status.Contracts import Refs


class LiveRefs(Refs):
    def trunk(self) -> str:
        raise NotImplementedError(f"{type(self).__name__}.trunk")

    def base(self) -> str:
        raise NotImplementedError(f"{type(self).__name__}.base")

    def module_branch(self, module: str) -> str:
        raise NotImplementedError(f"{type(self).__name__}.module_branch")

    def tag(self, label: str) -> str:
        raise NotImplementedError(f"{type(self).__name__}.tag")

    def module_for_branch(self, branch: str) -> str | None:
        raise NotImplementedError(f"{type(self).__name__}.module_for_branch")
