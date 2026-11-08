"""features contract: the backlog, ideas and the feature cycle."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class ItemState(Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    ACCEPTED = "accepted"
    ABANDONED = "abandoned"
    DROPPED = "dropped"


@dataclass(frozen=True)
class BacklogItem:
    slug: str
    title: str
    description: str
    state: ItemState
    added: datetime
    brief: str


@dataclass(frozen=True)
class Idea:
    title: str
    description: str


@dataclass(frozen=True)
class FeaturePlan:
    reopened: Mapping[str, tuple[int, ...]]
    new_modules: tuple[str, ...]
    contract_changes: tuple[str, ...]
    skeleton_needed: bool


class Backlog(Protocol):
    def items(self) -> list[BacklogItem]: ...
    def add(self, idea: Idea, top: bool = False) -> BacklogItem: ...
    def import_ideas(self, ideas: Sequence[Idea]) -> list[BacklogItem]: ...
    def move(self, slug: str, position: int) -> None: ...
    def drop(self, slug: str) -> None: ...


class IdeaReader(Protocol):
    def read(self, text: str, section: str | None = None) -> list[Idea]: ...
    def slug(self, title: str, taken: Collection[str]) -> str: ...


class FeatureCycle(Protocol):
    def start(self, slug: str | None = None) -> BacklogItem: ...
    def plan(self) -> FeaturePlan: ...
    def accept(self) -> BacklogItem: ...
    def abandon(self) -> BacklogItem: ...
