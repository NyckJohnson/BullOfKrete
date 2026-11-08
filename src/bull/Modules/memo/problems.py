"""The memo's problems: build order, modules, parts and interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from bull.Modules.memo.Contracts import (
    BuildEntry,
    Memo,
    MemoProblem,
    ModuleEntry,
    SideRef,
)

# Journeys and interfaces carry no source line in the contract; their problems use this.
_NO_LINE = 0

_Entry = TypeVar("_Entry", BuildEntry, ModuleEntry)


def memo_problems(
    memo: Memo, known_parts: Sequence[str], max_files: int
) -> list[MemoProblem]:
    """Every problem in `memo`, ordered by line (journey and interface problems at line 0).

    `known_parts` are the app's configured parts; `max_files` is the most files a unit may hold.
    """
    problems: list[MemoProblem] = list(memo.parse_problems)
    builds = _first_by_name(memo.build_order, problems, "build order entry")
    modules = _first_by_name(memo.modules, problems, "module block")
    problems += _build_order_problems(memo.build_order, builds, modules)
    problems += _module_problems(memo, builds, modules, max_files)
    problems += _part_problems(memo, known_parts, modules)
    problems += _interface_problems(memo, known_parts, modules)
    return sorted(problems, key=lambda p: p.line)


def _first_by_name(
    entries: Sequence[_Entry], problems: list[MemoProblem], what: str
) -> dict[str, _Entry]:
    """Entries by lower-cased name; later duplicates are reported and dropped."""
    found: dict[str, _Entry] = {}
    for entry in entries:
        key = entry.name.lower()
        if key in found:
            problems.append(
                MemoProblem(
                    entry.line,
                    f"duplicate {what} `{entry.name}` (also on line {found[key].line})",
                )
            )
        else:
            found[key] = entry
    return found


def _build_order_problems(
    build_order: Sequence[BuildEntry],
    builds: dict[str, BuildEntry],
    modules: dict[str, ModuleEntry],
) -> list[MemoProblem]:
    problems: list[MemoProblem] = []
    position = {
        entry.name.lower(): index
        for index, entry in enumerate(build_order)
        if builds.get(entry.name.lower()) is entry
    }
    for index, entry in enumerate(build_order):
        if builds.get(entry.name.lower()) is not entry:
            continue  # a duplicate, already reported
        if entry.name.lower() not in modules:
            problems.append(
                MemoProblem(
                    entry.line,
                    f"`{entry.name}` is in the build order but has no `### {entry.name}` block",
                )
            )
        for dep in entry.depends:
            dep_index = position.get(dep.lower())
            if dep_index is None:
                problems.append(
                    MemoProblem(
                        entry.line, f"`{entry.name}` depends on unknown module `{dep}`"
                    )
                )
            elif dep_index >= index:
                problems.append(
                    MemoProblem(
                        entry.line,
                        f"`{entry.name}` depends on `{dep}`, which is not earlier "
                        "in the build order",
                    )
                )
    return problems


def _module_problems(
    memo: Memo,
    builds: dict[str, BuildEntry],
    modules: dict[str, ModuleEntry],
    max_files: int,
) -> list[MemoProblem]:
    problems: list[MemoProblem] = []
    for module in memo.modules:
        if modules.get(module.name.lower()) is not module:
            continue  # a duplicate, already reported
        build = builds.get(module.name.lower())
        if build is None:
            problems.append(
                MemoProblem(
                    module.line,
                    f"module `{module.name}` has a block but is not in the build order",
                )
            )
            for dep in module.depends:
                if dep.lower() not in modules:
                    problems.append(
                        MemoProblem(
                            module.line,
                            f"`{module.name}` depends on unknown module `{dep}`",
                        )
                    )
        elif {d.lower() for d in module.depends} != {d.lower() for d in build.depends}:
            problems.append(
                MemoProblem(
                    module.line,
                    f"`{module.name}`: `Depends on: {', '.join(module.depends) or 'none'}` "
                    f"differs from the build order line "
                    f"({', '.join(build.depends) or 'none'})",
                )
            )
        if not module.units:
            problems.append(
                MemoProblem(module.line, f"module `{module.name}` has no `Files` line")
            )
        for number, unit in enumerate(module.units, start=1):
            if len(unit) > max_files:
                problems.append(
                    MemoProblem(
                        module.line,
                        f"`{module.name}` unit {number} has {len(unit)} files "
                        f"(at most {max_files})",
                    )
                )
        listed = {file for unit in module.units for file in unit}
        for slug, files in module.changes.items():
            for file in files:
                if file not in listed:
                    problems.append(
                        MemoProblem(
                            module.line,
                            f"`{module.name}`: `Changes ({slug})` names `{file}`, "
                            "which is not in its `Files`",
                        )
                    )
    return problems


def _part_problems(
    memo: Memo, known_parts: Sequence[str], modules: dict[str, ModuleEntry]
) -> list[MemoProblem]:
    problems: list[MemoProblem] = []
    several = len(set(memo.parts) | set(known_parts)) > 1
    for module in memo.modules:
        if modules.get(module.name.lower()) is not module:
            continue
        if module.part is None:
            if several:
                problems.append(
                    MemoProblem(
                        module.line,
                        f"module `{module.name}` has no `Part` line; the app has "
                        "several parts",
                    )
                )
            continue
        if module.part not in known_parts:
            problems.append(
                MemoProblem(
                    module.line,
                    f"module `{module.name}` names unknown part `{module.part}`",
                )
            )
        for dep in module.depends:
            other = modules.get(dep.lower())
            if (
                other is not None
                and other.part is not None
                and other.part != module.part
            ):
                problems.append(
                    MemoProblem(
                        module.line,
                        f"`{module.part} / {module.name}` depends on "
                        f"`{other.part} / {other.name}` in another part; use an interface",
                    )
                )
    for journey in memo.journeys:
        if journey.part is not None and journey.part not in known_parts:
            problems.append(
                MemoProblem(
                    _NO_LINE,
                    f"journey {journey.number} ({journey.title}) names unknown part "
                    f"`{journey.part}`",
                )
            )
    return problems


def _interface_problems(
    memo: Memo, known_parts: Sequence[str], modules: dict[str, ModuleEntry]
) -> list[MemoProblem]:
    problems: list[MemoProblem] = []
    for interface in memo.interfaces:
        if not interface.format:
            problems.append(
                MemoProblem(
                    _NO_LINE,
                    f"interface `{interface.name}`: `File: {interface.file}` needs "
                    "`(<format>)`",
                )
            )
        sides: list[tuple[str, SideRef]] = [("provider", interface.provider)]
        sides += [("consumer", side) for side in interface.consumers]
        for role, side in sides:
            if not side.part:
                problems.append(
                    MemoProblem(
                        _NO_LINE,
                        f"interface `{interface.name}`: {role} `{side.module}` needs "
                        "`<part> / <Module>`",
                    )
                )
            elif side.part not in known_parts:
                problems.append(
                    MemoProblem(
                        _NO_LINE,
                        f"interface `{interface.name}`: {role} names unknown part "
                        f"`{side.part}`",
                    )
                )
            if side.module.lower() not in modules:
                problems.append(
                    MemoProblem(
                        _NO_LINE,
                        f"interface `{interface.name}`: {role} names unknown module "
                        f"`{side.module}`",
                    )
                )
    return problems
