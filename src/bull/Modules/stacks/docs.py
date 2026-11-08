"""A stack's `rules.md` and `setup.md` sections."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.stacks.Contracts import Stack, StackError

_COMMON = "common"
_OUTLINE = "outline"


def rules(stack: Stack, agent: str) -> str:
    """`## common` plus `## <agent>` from the stack's `rules.md`; `outline` is that section only.

    Headings match case-insensitively. Raises StackError when the agent has no section.
    """
    wanted = agent.strip()
    if not wanted:
        raise StackError(
            "no agent named for `stack rules`",
            "name an agent, e.g. `bull stack rules code-writer`",
        )
    text = _read(stack, "rules.md")
    sections = _sections(text)
    body = sections.get(wanted.casefold())
    if body is None:
        known = ", ".join(_headings(text)) or "none"
        raise StackError(
            f"stack `{stack.manifest.name}` has no rules for agent `{agent}`",
            f"add a `## {agent}` section to {stack.home / 'rules.md'} (sections: {known})",
        )
    if wanted.casefold() == _OUTLINE:
        return body
    common = sections.get(_COMMON)
    if common is None or wanted.casefold() == _COMMON:
        return body
    return f"{common.rstrip()}\n\n{body}"


def setup_guide(stack: Stack, section: str | None = None) -> str:
    """The whole `setup.md`, or only its `## <section>` (matched case-insensitively).

    Raises StackError when the section does not exist.
    """
    text = _read(stack, "setup.md")
    if section is None:
        return text
    body = _sections(text).get(section.strip().casefold())
    if body is None:
        known = ", ".join(_headings(text)) or "none"
        raise StackError(
            f"stack `{stack.manifest.name}` has no setup section `{section}`",
            f"sections in {stack.home / 'setup.md'}: {known}",
        )
    return body


def _read(stack: Stack, name: str) -> str:
    path: Path = stack.home / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise StackError(
            f"stack `{stack.manifest.name}` has no {name}", f"create {path}"
        ) from e
    except (OSError, UnicodeDecodeError) as e:
        raise StackError(f"cannot read {path}: {e}") from e


def _heading(line: str) -> str | None:
    """The heading text of a `## ` line (not `###`), else None."""
    if line.startswith("## "):
        return line[3:].strip()
    return None


def _scan(text: str) -> list[tuple[str, str | None]]:
    """Each line (ends kept) with its `## ` heading text, or None.

    Lines inside a fenced code block (opened by ``` or ~~~, closed by a line of the same
    character at least as long) are never headings.
    """
    out: list[tuple[str, str | None]] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        stripped = bare.lstrip()
        if fence is not None:
            if stripped.startswith(fence) and not stripped.strip(fence[0]).strip():
                fence = None
            out.append((line, None))
            continue
        marker = _fence_marker(stripped)
        if marker is not None:
            fence = marker
            out.append((line, None))
            continue
        out.append((line, _heading(bare)))
    return out


def _fence_marker(stripped: str) -> str | None:
    """The opening fence (a run of 3+ backticks or tildes) a line starts with, else None."""
    for char in ("`", "~"):
        if stripped.startswith(char * 3):
            return char * (len(stripped) - len(stripped.lstrip(char)))
    return None


def _headings(text: str) -> list[str]:
    return [h for _, h in _scan(text) if h is not None]


def _sections(text: str) -> dict[str, str]:
    """Each `## ` section (heading line included, up to the next `## `), keyed by casefolded heading.

    The first section with a given heading wins.
    """
    found: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []

    def close() -> None:
        if name is not None and name.casefold() not in found:
            found[name.casefold()] = "".join(lines).rstrip() + "\n"

    for line, heading in _scan(text):
        if heading is not None:
            close()
            name, lines = heading, [line]
        elif name is not None:
            lines.append(line)
    close()
    return found
