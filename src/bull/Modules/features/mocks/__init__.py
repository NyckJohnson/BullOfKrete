"""Mocks of the features contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import replace
from datetime import UTC, datetime

from bull.Modules.features.Contracts import (
    Backlog,
    BacklogItem,
    FeatureCycle,
    FeaturePlan,
    Idea,
    IdeaReader,
    ItemState,
)

SAMPLE_TIME = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)


def sample_item(slug: str = "reset-button", title: str = "Reset button") -> BacklogItem:
    return BacklogItem(
        slug=slug,
        title=title,
        description="A button that sets the counter back to zero.",
        state=ItemState.QUEUED,
        added=SAMPLE_TIME,
        brief=f"docs/features/{slug}.md",
    )


def _slug(title: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in title.lower()).split())[
        :40
    ]


class MockBacklog(Backlog):
    def __init__(self) -> None:
        self.backlog: list[BacklogItem] = [
            sample_item("reset-button", "Reset button"),
            sample_item("dark-mode", "Dark mode"),
        ]
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def items(self) -> list[BacklogItem]:
        self.calls.append(("items", ()))
        return list(self.backlog)

    def add(self, idea: Idea, top: bool = False) -> BacklogItem:
        self.calls.append(("add", (idea, top)))
        item = replace(
            sample_item(_slug(idea.title), idea.title), description=idea.description
        )
        if top:
            self.backlog.insert(0, item)
        else:
            self.backlog.append(item)
        return item

    def import_ideas(self, ideas: Sequence[Idea]) -> list[BacklogItem]:
        self.calls.append(("import_ideas", (tuple(ideas),)))
        taken = {item.slug for item in self.backlog}
        added: list[BacklogItem] = []
        for idea in ideas:
            if _slug(idea.title) not in taken:
                added.append(self.add(idea))
        return added

    def move(self, slug: str, position: int) -> None:
        self.calls.append(("move", (slug, position)))
        item = next(i for i in self.backlog if i.slug == slug)
        self.backlog.remove(item)
        self.backlog.insert(position - 1, item)

    def drop(self, slug: str) -> None:
        self.calls.append(("drop", (slug,)))
        self.backlog = [
            replace(i, state=ItemState.DROPPED) if i.slug == slug else i
            for i in self.backlog
        ]


class MockIdeaReader(IdeaReader):
    def __init__(self) -> None:
        self.ideas: list[Idea] = [
            Idea("Reset button", "A button that sets the counter back to zero."),
            Idea("Dark mode", "A darker theme."),
            Idea("Export", "Write the counts to a CSV file."),
        ]
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def read(self, text: str, section: str | None = None) -> list[Idea]:
        self.calls.append(("read", (text, section)))
        return list(self.ideas)

    def slug(self, title: str, taken: Collection[str]) -> str:
        self.calls.append(("slug", (title, tuple(taken))))
        base = _slug(title)
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        return slug


class MockFeatureCycle(FeatureCycle):
    def __init__(self) -> None:
        self.item = sample_item()
        self.feature_plan = FeaturePlan(
            reopened={"Counter": (1,)},
            new_modules=(),
            contract_changes=("Counter",),
            skeleton_needed=True,
        )
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def start(self, slug: str | None = None) -> BacklogItem:
        self.calls.append(("start", (slug,)))
        self.item = replace(self.item, state=ItemState.ACTIVE)
        return self.item

    def plan(self) -> FeaturePlan:
        self.calls.append(("plan", ()))
        return self.feature_plan

    def accept(self) -> BacklogItem:
        self.calls.append(("accept", ()))
        self.item = replace(self.item, state=ItemState.ACCEPTED)
        return self.item

    def abandon(self) -> BacklogItem:
        self.calls.append(("abandon", ()))
        self.item = replace(self.item, state=ItemState.ABANDONED)
        return self.item
