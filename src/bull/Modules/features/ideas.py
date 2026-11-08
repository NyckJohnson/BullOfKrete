"""Reads ideas from Markdown and makes slugs."""

from __future__ import annotations

import re
from collections.abc import Collection

from bull.Modules.features.Contracts import Idea, IdeaReader
from bull.Modules.foundation.Contracts import BullError

_MAX_SLUG = 40
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_CHECKED = re.compile(r"\[[xX]\](\s|$)")
_UNCHECKED = re.compile(r"^\[ \](\s|$)")


def _heading(line: str) -> tuple[int, str] | None:
    """`(level, text)` for a level-1 or level-2 ATX heading, else None."""
    for level, marker in ((2, "## "), (1, "# ")):
        if line.startswith(marker):
            return level, line[len(marker) :].strip()
    return None


def _list_items(lines: list[str]) -> list[Idea]:
    """One idea per top-level `- Title: description` item (split at the first colon).

    An indented line right under an item continues its description (joined with a
    newline); `- [x] …` items are skipped and `- [ ] B` is read as `- B`.
    """
    ideas: list[Idea] = []
    title: str | None = None
    parts: list[str] = []

    def flush() -> None:
        if title:
            ideas.append(Idea(title, "\n".join(p for p in parts if p)))

    for line in lines:
        if line.startswith("- "):
            flush()
            title, parts = None, []
            text = line[2:].strip()
            if _CHECKED.match(text):
                continue
            text = _UNCHECKED.sub("", text, count=1).strip()
            head, sep, description = text.partition(":")
            title = head.strip() if sep else text
            parts = [description.strip()] if sep else []
        elif title is not None and line[:1] in (" ", "\t") and line.strip():
            parts.append(line.strip())
        else:
            flush()
            title, parts = None, []
    flush()
    return ideas


def _sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """The `## Title` sections with their body lines; a level-1 heading ends a section."""
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in lines:
        heading = _heading(line)
        if heading is not None:
            level, title = heading
            if level == 2:
                current = []
                sections.append((title, current))
            else:
                current = None
        elif current is not None:
            current.append(line)
    return sections


class LiveIdeaReader(IdeaReader):
    def read(self, text: str, section: str | None = None) -> list[Idea]:
        lines = text.splitlines()
        sections = _sections(lines)
        if section is not None:
            return [
                idea
                for title, body in sections
                if title.casefold() == section.casefold()
                for idea in _list_items(body)
            ]
        if sections:
            return [
                Idea(title, "\n".join(body).strip())
                for title, body in sections
                if title
            ]
        return _list_items(lines)

    def slug(self, title: str, taken: Collection[str]) -> str:
        """Lowercase, runs of non-alphanumerics → `-`, at most 40 characters cut at a
        `-` (hard cut when there is none); `-2`, `-3`, … while taken.

        Raises `BullError` when the title has no letters or digits.
        """
        base = _NON_ALNUM.sub("-", title.lower()).strip("-")
        if not base:
            raise BullError(
                f"Can't make a slug from {title!r}.",
                "Give the idea a title with letters or digits.",
            )
        if len(base) > _MAX_SLUG:
            head = base[: _MAX_SLUG + 1]
            cut = head.rfind("-")
            base = head[:cut] if cut > 0 else base[:_MAX_SLUG]
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        return slug
