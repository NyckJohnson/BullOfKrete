"""The plugin's Markdown files, read from this module's folder."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.plugin_text.Contracts import AgentDoc, PluginFile, PluginText

_ORCHESTRATOR = "orchestrator.md"
_FOLDERS = ("commands", "agents")
_AGENT_KEYS = ("name", "description", "tools")


class LivePluginText(PluginText):
    """Reads the plugin's Markdown from `root` (default: this module's own folder).

    Only `orchestrator.md`, `commands/*.md` and `agents/*.md` count as plugin files.
    Raises `BullError` naming the file for a missing `orchestrator.md`, an unreadable
    file, or an agent file with bad frontmatter.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else Path(__file__).parent

    def files(self) -> list[PluginFile]:
        self._require_orchestrator()
        return [PluginFile(rel, self._read(rel)) for rel in self._paths()]

    def agents(self) -> list[AgentDoc]:
        docs: list[AgentDoc] = []
        for rel in self._paths():
            if rel.startswith("agents/"):
                docs.append(_parse_agent(rel, self._read(rel)))
        return docs

    def orchestrator(self) -> str:
        self._require_orchestrator()
        return self._read(_ORCHESTRATOR)

    def _require_orchestrator(self) -> None:
        """Raises `BullError` naming `orchestrator.md` when it is missing from the root."""
        if not (self._root / _ORCHESTRATOR).is_file():
            raise BullError(
                f"{_ORCHESTRATOR} is missing from the plugin folder {self._root}",
                "Reinstall bull so the plugin files are complete.",
            )

    def _paths(self) -> list[str]:
        """Plugin file paths, POSIX and relative to the root, sorted."""
        paths: list[str] = []
        if (self._root / _ORCHESTRATOR).is_file():
            paths.append(_ORCHESTRATOR)
        for folder in _FOLDERS:
            directory = self._root / folder
            if directory.is_dir():
                paths.extend(
                    f"{folder}/{p.name}" for p in directory.glob("*.md") if p.is_file()
                )
        return sorted(paths)

    def _read(self, rel: str) -> str:
        # newline="" keeps the file's text exactly as written.
        try:
            with open(self._root / rel, encoding="utf-8", newline="") as handle:
                return handle.read()
        except (OSError, UnicodeDecodeError) as error:
            raise BullError(
                f"Cannot read plugin file {rel}: {error}",
                "Reinstall bull so the plugin files are intact.",
            ) from error


def _parse_agent(rel: str, text: str) -> AgentDoc:
    """Builds an `AgentDoc` from an agent file's frontmatter; `rel` is `agents/<file>`."""
    front = _frontmatter(text)
    if front is None:
        raise BullError(
            f"{rel} has no frontmatter (a first line `---` closed by `---`)"
        )
    for key in _AGENT_KEYS:
        if key not in front:
            raise BullError(f"{rel} frontmatter is missing `{key}`")
    name = front["name"]
    expected = Path(rel).stem
    if name != expected:
        raise BullError(
            f"{rel} has name `{name}`, which differs from its file name `{expected}`"
        )
    tools = tuple(t.strip() for t in front["tools"].split(",") if t.strip())
    return AgentDoc(name, front["description"], tools, f"models.{name}")


def _frontmatter(text: str) -> dict[str, str] | None:
    """The `key: value` pairs between a first line `---` and the next `---` line, or None.

    Values are trimmed and lose one pair of surrounding `"` or `'`; lines without `:` are ignored.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values
        key, sep, value = line.partition(":")
        if sep:
            values[key.strip()] = _unquote(value.strip())
    return None


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value
