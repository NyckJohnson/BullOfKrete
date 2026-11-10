"""`coverage-exempt` markers in a source file."""

from __future__ import annotations

import re
from pathlib import Path

from bull.Modules.coverage.Contracts import Exemption, MarkerScan

# A file marker counts only within this many leading lines.
_FILE_MARKER_LINES = 10


def _marker_pattern(comment: str) -> re.Pattern[str]:
    # `<comment> coverage-exempt[-begin|-end|-file][: <reason>]`, to the end of the line.
    return re.compile(
        re.escape(comment)
        + r"\s*coverage-exempt(?P<kind>-begin|-end|-file)?(?![\w-])(?P<colon>:)?(?P<reason>.*)$"
    )


def scan_markers(path: Path, comment: str) -> MarkerScan:
    """Scan `path` for `coverage-exempt` markers written after the comment prefix `comment`.

    Invalid markers (missing reason, unclosed begin, stray end) exempt nothing and are reported
    as `<path>:<line>: <problem>`. A file marker after line 10 is not a marker. Raises `OSError`
    if the file cannot be read.
    """
    return scan_markers_with_file_lines(path, comment)[0]


def scan_markers_with_file_lines(
    path: Path, comment: str
) -> tuple[MarkerScan, tuple[int, ...]]:
    """`scan_markers`, plus the 1-based lines of the valid file markers (the `Exemption`s with
    `lines=None`), which the triage report needs to flag an unnecessary file marker. Raises
    `OSError` if the file cannot be read.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    pattern = _marker_pattern(comment)
    exemptions: list[Exemption] = []
    invalid: list[str] = []
    file_lines: list[int] = []
    # Open block: (begin line, reason or None when the begin itself was invalid).
    open_block: tuple[int, str | None] | None = None

    for number, line in enumerate(text.splitlines(), start=1):
        match = pattern.search(line)
        if match is None:
            continue
        kind = match.group("kind")
        reason = match.group("reason").strip() if match.group("colon") else ""

        if kind == "-end":
            if open_block is None:
                invalid.append(f"{path}:{number}: coverage-exempt-end without a begin")
                continue
            begin, block_reason = open_block
            open_block = None
            if block_reason is not None:
                exemptions.append(
                    Exemption(path, tuple(range(begin, number + 1)), block_reason)
                )
        elif kind == "-begin":
            if open_block is not None:
                invalid.append(
                    f"{path}:{number}: coverage-exempt-begin inside an open block"
                )
                continue
            if not reason:
                invalid.append(
                    f"{path}:{number}: coverage-exempt-begin marker is missing a reason"
                )
                open_block = (number, None)
            else:
                open_block = (number, reason)
        elif kind == "-file":
            if number > _FILE_MARKER_LINES:
                continue
            if not reason:
                invalid.append(
                    f"{path}:{number}: coverage-exempt-file marker is missing a reason"
                )
            else:
                exemptions.append(Exemption(path, None, reason))
                file_lines.append(number)
        elif not reason:
            invalid.append(
                f"{path}:{number}: coverage-exempt marker is missing a reason"
            )
        else:
            exemptions.append(Exemption(path, (number,), reason))

    if open_block is not None:
        begin, block_reason = open_block
        if block_reason is not None:
            invalid.append(f"{path}:{begin}: coverage-exempt-begin is never closed")

    scan = MarkerScan(exemptions=tuple(exemptions), invalid=tuple(invalid))
    return scan, tuple(file_lines)
