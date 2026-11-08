"""Progress: the next step, the summary, the JSON view and the pipeline's tags."""

from __future__ import annotations

from bull.Modules.status.Contracts import NextStep, Progress


class LiveProgress(Progress):
    def next_step(self) -> NextStep:
        raise NotImplementedError(f"{type(self).__name__}.next_step")

    def summary(self) -> str:
        raise NotImplementedError(f"{type(self).__name__}.summary")

    def as_json(self) -> dict[str, object]:
        raise NotImplementedError(f"{type(self).__name__}.as_json")

    def tags(self) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.tags")
