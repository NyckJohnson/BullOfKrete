"""The feature backlog in `.bull/backlog.json`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from bull.Modules.features.briefs import write_brief
from bull.Modules.features.Contracts import (
    Backlog,
    BacklogItem,
    Idea,
    IdeaReader,
    ItemState,
)
from bull.Modules.foundation.Contracts import (
    AppLayout,
    BullError,
    Clock,
    FileFormatError,
    Files,
)

_FORMAT = 1
_TIME = "%Y-%m-%dT%H:%M:%SZ"


def _to_json(item: BacklogItem) -> dict[str, str]:
    return {
        "slug": item.slug,
        "title": item.title,
        "description": item.description,
        "state": item.state.value,
        "added": item.added.astimezone(UTC).strftime(_TIME),
        "brief": item.brief,
    }


def _from_json(raw: object, where: str) -> BacklogItem:
    """Parses one item; raises `FileFormatError` naming the file when it is malformed."""
    try:
        if not isinstance(raw, dict):
            raise TypeError("item is not an object")
        fields: dict[str, Any] = raw
        values = {
            k: fields[k]
            for k in ("slug", "title", "description", "state", "added", "brief")
        }
        if not all(isinstance(v, str) for v in values.values()):
            raise TypeError("item fields must be strings")
        return BacklogItem(
            slug=values["slug"],
            title=values["title"],
            description=values["description"],
            state=ItemState(values["state"]),
            added=datetime.strptime(values["added"], _TIME).replace(tzinfo=UTC),
            brief=values["brief"],
        )
    except (KeyError, TypeError, ValueError) as e:
        raise FileFormatError(f"{where}: invalid backlog item: {e}") from e


class LiveBacklog(Backlog):
    """The queue in `app.backlog_file`; adding an item also writes its brief."""

    def __init__(
        self, app: AppLayout, files: Files, clock: Clock, ideas: IdeaReader
    ) -> None:
        self._app = app
        self._files = files
        self._clock = clock
        self._ideas = ideas

    def _load(self) -> list[BacklogItem]:
        path = self._app.backlog_file
        data = self._files.read_json(path)
        if data is None:
            return []
        if not isinstance(data, dict) or data.get("format") != _FORMAT:
            raise FileFormatError(f"{path}: expected a format {_FORMAT} backlog")
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            raise FileFormatError(f"{path}: `items` must be a list")
        return [_from_json(raw, str(path)) for raw in raw_items]

    def _save(self, items: Sequence[BacklogItem]) -> None:
        self._files.write_json(
            self._app.backlog_file,
            {"format": _FORMAT, "items": [_to_json(i) for i in items]},
        )

    def _new_item(self, idea: Idea, taken: Sequence[BacklogItem]) -> BacklogItem:
        slug = self._ideas.slug(idea.title, {i.slug for i in taken})
        brief = write_brief(self._app, self._files, slug, idea)
        added = self._clock.now().astimezone(UTC).replace(microsecond=0)
        return BacklogItem(
            slug, idea.title, idea.description, ItemState.QUEUED, added, brief
        )

    def items(self) -> list[BacklogItem]:
        return self._load()

    def add(self, idea: Idea, top: bool = False) -> BacklogItem:
        items = self._load()
        item = self._new_item(idea, items)
        if top:
            items.insert(0, item)
        else:
            items.append(item)
        self._save(items)
        return item

    def import_ideas(self, ideas: Sequence[Idea]) -> list[BacklogItem]:
        """Adds each idea whose slug or (case-insensitive) title isn't in the backlog yet,
        in any state; ideas earlier in `ideas` count too."""
        items = self._load()
        added: list[BacklogItem] = []
        for idea in ideas:
            slugs = {i.slug for i in items}
            titles = {i.title.casefold() for i in items}
            if (
                idea.title.casefold() in titles
                or self._ideas.slug(idea.title, ()) in slugs
            ):
                continue
            item = self._new_item(idea, items)
            items.append(item)
            added.append(item)
        if added:
            self._save(items)
        return added

    def move(self, slug: str, position: int) -> None:
        """Moves a queued item to `position` (1-based, counting queued items only); the
        other items keep their places in the file. Raises `BullError` when `slug` isn't
        queued or `position` is outside 1…(number of queued items)."""
        items = self._load()
        queued = [i for i in items if i.state is ItemState.QUEUED]
        item = next((i for i in queued if i.slug == slug), None)
        if item is None:
            raise BullError(f"No queued feature {slug!r}.", "Run `bull feature list`.")
        if not 1 <= position <= len(queued):
            raise BullError(
                f"Position {position} is out of range.",
                f"Give a position from 1 to {len(queued)}.",
            )
        queued.remove(item)
        queued.insert(position - 1, item)
        # Refill the queued slots in their new order; other items stay where they are.
        reordered = iter(queued)
        self._save(
            [next(reordered) if i.state is ItemState.QUEUED else i for i in items]
        )

    def drop(self, slug: str) -> None:
        """Marks a queued item `dropped`; its brief file is kept. Raises `BullError` when
        `slug` isn't queued."""
        items = self._load()
        if not any(i.slug == slug and i.state is ItemState.QUEUED for i in items):
            raise BullError(f"No queued feature {slug!r}.", "Run `bull feature list`.")
        self._save(
            [
                BacklogItem(
                    i.slug, i.title, i.description, ItemState.DROPPED, i.added, i.brief
                )
                if i.slug == slug
                else i
                for i in items
            ]
        )
