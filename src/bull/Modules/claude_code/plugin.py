"""The Claude Code provider: plugin rendering and the provider seam's entry points."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from bull.Modules.claude_code import launch
from bull.Modules.claude_code.Contracts import HookOutput, Provider, StatusLineInput
from bull.Modules.claude_code.hooks_json import hooks_json
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.plugin_text.Contracts import PluginText
from bull.Modules.settings.Contracts import Settings
from bull.Modules.stacks.Contracts import CheckItem

_PLUGIN_NAME = "bull"
_INHERIT = "inherit"
_FENCE = "---"


class LiveProvider(Provider):
    """Claude Code as bull's provider; plugin text comes from `plugin_text`."""

    def __init__(self, plugin_text: PluginText) -> None:
        self.name = "claude"
        self._text = plugin_text

    def render_plugin(self, dest: Path, settings: Settings, version: str) -> Path:
        """Render the whole plugin into `dest`, replacing whatever was there.

        The plugin is built in a sibling temporary folder and then swapped into place,
        so `dest` never holds a half-written plugin. Raises `ValueError` if a plugin
        file's path is absolute or leaves the plugin folder; errors from `settings`
        propagate unchanged.
        """
        files = self._render_files(settings, version)
        dest.parent.mkdir(parents=True, exist_ok=True)
        build = Path(tempfile.mkdtemp(prefix=f".{dest.name}-new-", dir=dest.parent))
        try:
            for rel, text in files.items():
                target = build / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            _swap_in(build, dest)
        except BaseException:
            shutil.rmtree(build, ignore_errors=True)
            raise
        return dest

    def _render_files(
        self, settings: Settings, version: str
    ) -> dict[PurePosixPath, str]:
        files: dict[PurePosixPath, str] = {}
        for plugin_file in self._text.files():
            rel = _relative(plugin_file.path)
            text = plugin_file.text
            if len(rel.parts) == 2 and rel.parts[0] == "agents" and rel.suffix == ".md":
                model = settings.get(f"models.{rel.stem}", None)
                text = _with_model(text, str(model))
            files[rel] = text
        manifest = {"name": _PLUGIN_NAME, "version": version}
        files[PurePosixPath(".claude-plugin/plugin.json")] = (
            json.dumps(manifest, indent=2) + "\n"
        )
        files[PurePosixPath("hooks/hooks.json")] = hooks_json()
        files[PurePosixPath("orchestrator.md")] = self._text.orchestrator()
        return files

    def launch_argv(self, app: AppLayout, extra: Sequence[str]) -> list[str]:
        return launch.launch_argv(app, extra)

    def tool_check(self) -> CheckItem:
        return launch.tool_check()

    def parse_hook(self, kind: HookKind, raw: str) -> HookEvent:
        raise NotImplementedError(f"{type(self).__name__}.parse_hook")

    def hook_output(self, kind: HookKind, decision: HookDecision) -> HookOutput:
        raise NotImplementedError(f"{type(self).__name__}.hook_output")

    def parse_statusline(self, raw: str) -> StatusLineInput:
        raise NotImplementedError(f"{type(self).__name__}.parse_statusline")

    def app_files(self, app: AppLayout) -> dict[Path, str]:
        raise NotImplementedError(f"{type(self).__name__}.app_files")


def _relative(path: str) -> PurePosixPath:
    rel = PurePosixPath(path)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise ValueError(f"plugin file path must stay inside the plugin: {path!r}")
    return rel


def _with_model(text: str, model: str) -> str:
    """`text` with `model: <model>` as the frontmatter's last line.

    Any existing `model:` line is dropped first. With `inherit`, or when `text` has no
    frontmatter, the text is returned unchanged.
    """
    if model == _INHERIT:
        return text
    lines = text.split("\n")
    if not lines or lines[0] != _FENCE:
        return text
    try:
        end = lines.index(_FENCE, 1)
    except ValueError:
        return text
    front = [line for line in lines[1:end] if not line.startswith("model:")]
    return "\n".join([_FENCE, *front, f"model: {model}", *lines[end:]])


def _swap_in(build: Path, dest: Path) -> None:
    """Replace `dest` with `build` by renames, then delete the old folder."""
    if not dest.exists() and not dest.is_symlink():
        build.rename(dest)
        return
    old = Path(tempfile.mkdtemp(prefix=f".{dest.name}-old-", dir=dest.parent))
    old.rmdir()
    dest.rename(old)
    try:
        build.rename(dest)
    except OSError:
        old.rename(dest)
        raise
    if old.is_dir() and not old.is_symlink():
        shutil.rmtree(old)
    else:
        old.unlink()
