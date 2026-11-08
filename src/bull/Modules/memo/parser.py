"""Parses the outline memo."""

from __future__ import annotations

import re
from collections.abc import Sequence

from bull.Modules.memo.Contracts import (
    BuildEntry,
    InterfaceEntry,
    Journey,
    LegacySection,
    Memo,
    MemoProblem,
    MemoReader,
    ModuleEntry,
    SideRef,
)
from bull.Modules.memo.problems import memo_problems

# A numbered line, the 1-based line number and its text.
_Line = tuple[int, str]

_FENCE = "```"
_SECTION = re.compile(r"^##\s+(.+?)\s*$")
_BLOCK = re.compile(r"^###\s+(.+?)\s*$")
# `- Key: value` or `- Key (slug): value`, at column 0.
_KEY = re.compile(r"^- ([A-Za-z][A-Za-z ]*?)(?: \(([^)]*)\))?:\s*(.*?)\s*$")
_BUILD = re.compile(r"^\s*\d+\.\s+(.+?)\s+\(depends on:\s*(.*?)\)\s*$")
_JOURNEY = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*")
_JOURNEY_PART = re.compile(r"^\s+- Part:\s*(.+?)\s*$")
_FILE_FORMAT = re.compile(r"^(.*?)\s*\(([^)]*)\)$")
_RENAME = re.compile(r"\s*(?:→|->)\s*")


def _numbered_lines(text: str) -> list[_Line]:
    """Every line outside fenced code blocks, with its 1-based number."""
    result: list[_Line] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith(_FENCE):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append((number, line))
    return result


def _sections(text: str) -> dict[str, list[_Line]]:
    """The lines under each `## <heading>` (the first section of a name wins)."""
    sections: dict[str, list[_Line]] = {}
    current: list[_Line] | None = None
    for number, line in _numbered_lines(text):
        match = _SECTION.match(line)
        if match:
            heading = match.group(1)
            if heading in sections:
                current = None
            else:
                current = []
                sections[heading] = current
        elif current is not None:
            current.append((number, line))
    return sections


def _blocks(lines: list[_Line]) -> list[tuple[str, int, list[_Line]]]:
    """The `### <Name>` blocks of a section: name, heading line, body lines."""
    blocks: list[tuple[str, int, list[_Line]]] = []
    for number, line in lines:
        match = _BLOCK.match(line)
        if match:
            blocks.append((match.group(1), number, []))
        elif blocks:
            blocks[-1][2].append((number, line))
    return blocks


def _split(value: str, sep: str = ",") -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(sep) if part.strip())


def _list(value: str) -> tuple[str, ...]:
    """A comma-separated list; `none` means empty."""
    if value.strip().lower() == "none":
        return ()
    return _split(value)


def _split_outside_parens(value: str) -> list[str]:
    """Splits on commas that are not inside parentheses."""
    items: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            items.append(value[start:index])
            start = index + 1
    items.append(value[start:])
    return [item.strip() for item in items if item.strip()]


def _side(value: str) -> SideRef:
    part, slash, module = value.partition("/")
    if not slash:
        return SideRef(part="", module=part.strip())
    return SideRef(part=part.strip(), module=module.strip())


def _keys(lines: list[_Line]) -> list[tuple[str, str | None, str]]:
    """The `- Key (slug): value` lines: key, slug (or None), value."""
    result: list[tuple[str, str | None, str]] = []
    for _, line in lines:
        match = _KEY.match(line)
        if match:
            slug = match.group(2)
            result.append(
                (match.group(1), slug.strip() if slug else None, match.group(3))
            )
    return result


def _module(name: str, line: int, body: list[_Line]) -> ModuleEntry:
    part: str | None = None
    depends: tuple[str, ...] = ()
    units: tuple[tuple[str, ...], ...] = ()
    legacy_files: tuple[str, ...] = ()
    legacy_tests: tuple[str, ...] = ()
    callers: tuple[str, ...] = ()
    reference_tests: tuple[str, ...] = ()
    changes: dict[str, tuple[str, ...]] = {}
    contract_changes: dict[str, str] = {}
    for key, slug, value in _keys(body):
        if slug is not None:
            if key == "Changes":
                changes[slug] = _split(value)
            elif key == "Contract changes":
                contract_changes[slug] = value
        elif key == "Part":
            part = value or None
        elif key == "Depends on":
            depends = _list(value)
        elif key == "Files":
            units = tuple(
                files for files in (_split(u) for u in value.split("|")) if files
            )
        elif key == "Legacy files":
            legacy_files = _split(value)
        elif key == "Legacy tests":
            legacy_tests = _split(value)
        elif key == "Callers to repoint":
            callers = _split(value)
        elif key == "Reference tests":
            reference_tests = _list(value)
    return ModuleEntry(
        name=name,
        line=line,
        part=part,
        depends=depends,
        units=units,
        legacy_files=legacy_files,
        legacy_tests=legacy_tests,
        callers=callers,
        reference_tests=reference_tests,
        changes=changes,
        contract_changes=contract_changes,
    )


def _interface(name: str, body: list[_Line]) -> InterfaceEntry:
    file = ""
    file_format = ""
    provider = SideRef(part="", module="")
    consumers: tuple[SideRef, ...] = ()
    contract_changes: dict[str, str] = {}
    for key, slug, value in _keys(body):
        if slug is not None:
            if key == "Contract changes":
                contract_changes[slug] = value
        elif key == "File":
            match = _FILE_FORMAT.match(value)
            if match:
                file, file_format = match.group(1).strip(), match.group(2).strip()
            else:
                file = value
        elif key == "Provider":
            provider = _side(value)
        elif key == "Consumers":
            consumers = tuple(_side(item) for item in _split(value))
    return InterfaceEntry(
        name=name,
        file=file,
        format=file_format,
        provider=provider,
        consumers=consumers,
        contract_changes=contract_changes,
    )


def _build_order(lines: list[_Line]) -> tuple[BuildEntry, ...]:
    entries: list[BuildEntry] = []
    for number, line in lines:
        match = _BUILD.match(line)
        if match:
            entries.append(
                BuildEntry(
                    name=match.group(1), depends=_list(match.group(2)), line=number
                )
            )
    return tuple(entries)


def _journeys(lines: list[_Line]) -> tuple[Journey, ...]:
    """Numbered `**Title**` lines; an indented `- Part:` belongs to the one above."""
    found: list[tuple[int, str, str | None]] = []
    for _, line in lines:
        match = _JOURNEY.match(line)
        if match:
            found.append((int(match.group(1)), match.group(2).strip(), None))
            continue
        part = _JOURNEY_PART.match(line)
        if part and found and found[-1][2] is None:
            number, title, _ = found[-1]
            found[-1] = (number, title, part.group(1))
    return tuple(Journey(number=n, title=t, part=p) for n, t, p in found)


def _parts(lines: list[_Line]) -> tuple[str, ...]:
    for key, slug, value in _keys(lines):
        if key == "Parts" and slug is None:
            return tuple(
                item.split("(", 1)[0].strip() for item in _split_outside_parens(value)
            )
    return ()


def _legacy(lines: list[_Line]) -> LegacySection:
    app_shell: tuple[str, ...] = ()
    app_shell_tests: tuple[str, ...] = ()
    legacy_folders: tuple[str, ...] = ()
    renames: dict[str, str] = {}
    for key, slug, value in _keys(lines):
        if slug is not None:
            continue
        if key == "App shell":
            app_shell = _split(value)
        elif key == "App shell tests":
            app_shell_tests = _split(value)
        elif key == "Legacy folders":
            legacy_folders = _split(value)
        elif key == "Renames":
            for item in _split(value):
                old, *new = _RENAME.split(item, maxsplit=1)
                if new:
                    renames[old.strip()] = new[0].strip()
    return LegacySection(
        app_shell=app_shell,
        app_shell_tests=app_shell_tests,
        legacy_folders=legacy_folders,
        renames=renames,
    )


def _items(lines: list[_Line]) -> list[str]:
    """Top-level `- ` items; indented continuation lines are joined, nested items dropped."""
    items: list[list[str]] = []
    current: list[str] | None = None
    nested = False
    for _, line in lines:
        if line.startswith("- "):
            current = [line[2:].strip()]
            items.append(current)
            nested = False
        elif not line.strip():
            continue
        elif line[0].isspace():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")) or re.match(r"\d+\.\s", stripped):
                nested = True
            elif current is not None and not nested:
                current.append(stripped)
        else:
            current = None
            nested = False
    return [" ".join(parts) for parts in items]


class LiveMemoReader(MemoReader):
    """Reads `docs/outline.md` text into a `Memo` and checks it for problems."""

    def parse(self, text: str) -> Memo:
        sections = _sections(text)
        legacy_lines = sections.get("Legacy code")
        return Memo(
            build_order=_build_order(sections.get("Build order", [])),
            modules=tuple(
                _module(name, line, body)
                for name, line, body in _blocks(sections.get("Modules", []))
            ),
            journeys=_journeys(sections.get("User journeys", [])),
            interfaces=tuple(
                _interface(name, body)
                for name, _, body in _blocks(sections.get("Interfaces", []))
            ),
            parts=_parts(sections.get("Constraints", [])),
            unmapped_reference_tests=tuple(
                _items(sections.get("Unmapped reference tests", []))
            ),
            legacy=_legacy(legacy_lines) if legacy_lines is not None else None,
        )

    def section_items(self, text: str, heading: str) -> list[str]:
        return _items(_sections(text).get(heading, []))

    def problems(
        self, memo: Memo, known_parts: Sequence[str], max_files: int
    ) -> list[MemoProblem]:
        return memo_problems(memo, known_parts, max_files)
