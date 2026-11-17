"""The app's provider files: `.claude/settings.json` and the `CLAUDE.md` block."""

from __future__ import annotations

import json
from pathlib import Path

from bull.Modules.foundation.Contracts import AppLayout, FileFormatError

_STATUS_LINE = {"type": "command", "command": "bull statusline"}
_ALLOW = ("Bash(bull:*)", "Bash(git:*)")
_ENV = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}

_BEGIN = "<!-- bull:begin -->"
_END = "<!-- bull:end -->"
_BLOCK = f"{_BEGIN}\n@.bull/plugin/orchestrator.md\n{_END}"


def app_files(app: AppLayout) -> dict[Path, str]:
    """The text `.claude/settings.json` and `CLAUDE.md` should hold; writes nothing.

    Both are merged into the files already in the app, keeping the user's content.
    Raises `FileFormatError` when the existing settings file is not a JSON object
    (or its `permissions`/`env` have the wrong shape), rather than overwrite it.
    """
    settings_path = app.root / ".claude" / "settings.json"
    claude_md = app.root / "CLAUDE.md"
    return {
        settings_path: _settings(settings_path),
        claude_md: _claude_md(_read(claude_md)),
    }


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _settings(path: Path) -> str:
    """bull's settings merged into the existing file at `path`, as JSON text."""
    text = _read(path)
    data: object = {}
    if text is not None and text.strip():
        try:
            data = json.loads(text)
        except ValueError as error:
            raise FileFormatError(
                f"{path} is not valid JSON: {error}", "fix or remove the file"
            ) from error
    if not isinstance(data, dict):
        raise FileFormatError(f"{path} must hold a JSON object", "fix the file")

    status_line = data.get("statusLine")
    data["statusLine"] = {
        **(status_line if isinstance(status_line, dict) else {}),
        **_STATUS_LINE,
    }

    permissions = _section(data, "permissions", path)
    allow = permissions.setdefault("allow", [])
    if not isinstance(allow, list):
        raise FileFormatError(
            f"{path}: permissions.allow must be a list", "fix the file"
        )
    allow.extend(rule for rule in _ALLOW if rule not in allow)

    _section(data, "env", path).update(_ENV)
    return json.dumps(data, indent=2) + "\n"


def _section(data: dict[str, object], key: str, path: Path) -> dict[str, object]:
    section = data.setdefault(key, {})
    if not isinstance(section, dict):
        raise FileFormatError(f"{path}: {key} must be a JSON object", "fix the file")
    return section


def _claude_md(text: str | None) -> str:
    """`text` with bull's marked block replaced, or appended when it has none."""
    if not text:
        return _BLOCK + "\n"
    begin = text.find(_BEGIN)
    end = text.find(_END, begin) if begin >= 0 else -1
    if begin >= 0 and end >= 0:
        return text[:begin] + _BLOCK + text[end + len(_END) :]
    separator = "\n" if text.endswith("\n") else "\n\n"
    return text + separator + _BLOCK + "\n"
