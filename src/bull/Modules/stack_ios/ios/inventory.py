"""Inventory of an adopted project's types and references.

For each `.swift` file under the `source_dir` setting (sorted by path): the types it declares at
file level (protocol, struct, enum, class, actor) and the types of the other files it mentions.
Comments and string literals are dropped first (`swift_scan`'s cleaner), and a mention counts only
as a whole identifier, so `BetaHelper` never references `Beta`. Not a Swift parser: it is a map for
the adoption survey, not a dependency graph the build relies on.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from . import swift_scan

_TYPE_RE = re.compile(
    r"(?<![\w.])(?:protocol|struct|enum|class|actor)\s+`?([A-Za-z_]\w*)"
)
_IDENT_RE = re.compile(r"(?<![\w$])[A-Za-z_]\w*")


def inventory(root: Path, settings: Mapping[str, object]) -> str:
    """Markdown inventory of the types and references of the `.swift` files under `source_dir`.

    `source_dir` is relative to `root`. Folders starting with `.` are skipped. The output depends
    only on the files' contents and paths, never on the order they were created in. Raises
    `OSError` if a file cannot be read.
    """
    source = settings.get("source_dir")
    source_rel = source if isinstance(source, str) else ""
    lines = ["# Type inventory", ""]
    if not source_rel:
        lines.append("`source_dir` is not set: no Swift files to list.")
        return "\n".join(lines) + "\n"
    folder = root / source_rel
    lines += [f"Source folder: `{source_rel}`", ""]

    files: dict[str, tuple[list[str], set[str]]] = {}
    for path in _swift_files(folder):
        text = path.read_text(encoding="utf-8", errors="replace")
        cleaned, _ = swift_scan._clean(text)  # comments dropped, strings set aside
        files[path.relative_to(folder).as_posix()] = (
            _top_level_types(cleaned),
            set(_IDENT_RE.findall(cleaned)),
        )
    if not files:
        lines.append("No Swift files found.")
        return "\n".join(lines) + "\n"

    declared_in: dict[str, list[str]] = {}
    for rel, (types, _) in files.items():
        for name in types:
            declared_in.setdefault(name, []).append(rel)

    for rel in sorted(files):
        types, words = files[rel]
        own = set(types)
        refs = sorted(n for n in declared_in if n in words and n not in own)
        lines.append(f"## {rel}")
        lines.append("")
        lines.append(f"- Types: {', '.join(types) if types else '(none)'}")
        if refs:
            shown = ", ".join(f"{n} ({', '.join(declared_in[n])})" for n in refs)
            lines.append(f"- References: {shown}")
        else:
            lines.append("- References: (none)")
        lines.append("")
    return "\n".join(lines)


def _swift_files(folder: Path) -> list[Path]:
    """Sorted `.swift` files under `folder`, leaving out folders that start with `.`."""
    if not folder.is_dir():
        return []
    found = []
    for path in folder.rglob("*.swift"):
        relative = path.relative_to(folder)
        if path.is_file() and not any(p.startswith(".") for p in relative.parts[:-1]):
            found.append(path)
    return sorted(found, key=lambda p: p.relative_to(folder).as_posix())


def _top_level_types(cleaned: str) -> list[str]:
    """Names of the types declared at brace depth 0 of `cleaned`, in file order, no repeats."""
    level: list[str] = []
    depth = 0
    for char in cleaned:
        if char == "{":
            depth += 1
            level.append(" ")
        elif char == "}":
            depth = max(0, depth - 1)
            level.append(" ")
        else:
            level.append(char if depth == 0 else " ")
    names: list[str] = []
    for match in _TYPE_RE.finditer("".join(level)):
        if match.group(1) not in names:
            names.append(match.group(1))
    return names
