"""Parses the outline memo."""

from __future__ import annotations

from collections.abc import Sequence

from bull.Modules.memo.Contracts import Memo, MemoProblem, MemoReader


class LiveMemoReader(MemoReader):
    def parse(self, text: str) -> Memo:
        raise NotImplementedError(f"{type(self).__name__}.parse")

    def section_items(self, text: str, heading: str) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.section_items")

    def problems(
        self, memo: Memo, known_parts: Sequence[str], max_files: int
    ) -> list[MemoProblem]:
        raise NotImplementedError(f"{type(self).__name__}.problems")
