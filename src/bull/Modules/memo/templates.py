"""The memo and backlog templates."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.memo.Contracts import Templates

# The template files ship inside the package, next to this file.
_FOLDER = Path(__file__).parent / "templates"
_NAMES = ("backlog", "outline")


class LiveTemplates(Templates):
    """Reads the shipped `templates/<name>.md` files."""

    def names(self) -> list[str]:
        return sorted(_NAMES)

    def text(self, name: str) -> str:
        """The template's text, unchanged; raises `BullError` for an unknown name."""
        if name not in _NAMES:
            shown = ", ".join(self.names())
            raise BullError(f"No template named {name!r}.", fix=f"Use one of: {shown}.")
        return (_FOLDER / f"{name}.md").read_text(encoding="utf-8")
