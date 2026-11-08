"""memo contract: the parsed outline memo, its problems and the templates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModuleEntry:
    name: str
    line: int
    part: str | None
    depends: tuple[str, ...]
    units: tuple[tuple[str, ...], ...]
    legacy_files: tuple[str, ...]
    legacy_tests: tuple[str, ...]
    callers: tuple[str, ...]
    reference_tests: tuple[str, ...]
    changes: Mapping[str, tuple[str, ...]]  # slug → files
    contract_changes: Mapping[str, str]  # slug → description


@dataclass(frozen=True)
class BuildEntry:
    name: str
    depends: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class Journey:
    number: int
    title: str
    part: str | None


@dataclass(frozen=True)
class SideRef:
    part: str
    module: str


@dataclass(frozen=True)
class InterfaceEntry:
    name: str
    file: str
    format: str
    provider: SideRef
    consumers: tuple[SideRef, ...]
    contract_changes: Mapping[str, str]


@dataclass(frozen=True)
class LegacySection:
    app_shell: tuple[str, ...]
    app_shell_tests: tuple[str, ...]
    legacy_folders: tuple[str, ...]
    renames: Mapping[str, str]


@dataclass(frozen=True)
class Memo:
    build_order: tuple[BuildEntry, ...]
    modules: tuple[ModuleEntry, ...]
    journeys: tuple[Journey, ...]
    interfaces: tuple[InterfaceEntry, ...]
    parts: tuple[str, ...]
    unmapped_reference_tests: tuple[str, ...]
    legacy: LegacySection | None


@dataclass(frozen=True)
class MemoProblem:
    line: int
    message: str


class MemoReader(Protocol):
    def parse(self, text: str) -> Memo: ...
    def section_items(self, text: str, heading: str) -> list[str]: ...
    def problems(
        self, memo: Memo, known_parts: Sequence[str], max_files: int
    ) -> list[MemoProblem]: ...


class Templates(Protocol):
    def names(self) -> list[str]: ...
    def text(self, name: str) -> str: ...
