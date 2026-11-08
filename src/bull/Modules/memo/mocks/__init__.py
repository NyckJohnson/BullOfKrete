"""Mocks of the memo contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Sequence

from bull.Modules.memo.Contracts import (
    BuildEntry,
    Journey,
    Memo,
    MemoProblem,
    MemoReader,
    ModuleEntry,
    Templates,
)


def sample_memo() -> Memo:
    """The two-module `tally` memo of journey 2: `Store`, then `Counter` depending on it."""
    store = ModuleEntry(
        name="Store",
        line=40,
        part=None,
        depends=(),
        units=(("Contracts/store.fx", "store.fx"),),
        legacy_files=(),
        legacy_tests=(),
        callers=(),
        reference_tests=(),
        changes={},
        contract_changes={},
    )
    counter = ModuleEntry(
        name="Counter",
        line=52,
        part=None,
        depends=("Store",),
        units=(("Contracts/counter.fx", "counter.fx"), ("cli.fx",)),
        legacy_files=(),
        legacy_tests=(),
        callers=(),
        reference_tests=(),
        changes={},
        contract_changes={},
    )
    return Memo(
        build_order=(
            BuildEntry("Store", (), 30),
            BuildEntry("Counter", ("Store",), 31),
        ),
        modules=(store, counter),
        journeys=(Journey(1, "Count things", None),),
        interfaces=(),
        parts=(),
        unmapped_reference_tests=(),
        legacy=None,
    )


class MockMemoReader(MemoReader):
    """Returns `memo` for any text; `found_problems` from `problems`."""

    def __init__(self) -> None:
        self.memo = sample_memo()
        self.items: dict[str, list[str]] = {
            "Later features": ["Dark mode: a darker theme."]
        }
        self.found_problems: list[MemoProblem] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def parse(self, text: str) -> Memo:
        self.calls.append(("parse", (text,)))
        return self.memo

    def section_items(self, text: str, heading: str) -> list[str]:
        self.calls.append(("section_items", (text, heading)))
        return list(self.items.get(heading, []))

    def problems(
        self, memo: Memo, known_parts: Sequence[str], max_files: int
    ) -> list[MemoProblem]:
        self.calls.append(("problems", (memo, tuple(known_parts), max_files)))
        return list(self.found_problems)


class MockTemplates(Templates):
    def __init__(self) -> None:
        self.texts: dict[str, str] = {
            "outline": "# <App> outline\n\n## Purpose\n",
            "backlog": "# Backlog\n\n- <Title>: <description>\n",
        }
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def names(self) -> list[str]:
        self.calls.append(("names", ()))
        return sorted(self.texts)

    def text(self, name: str) -> str:
        self.calls.append(("text", (name,)))
        return self.texts[name]
