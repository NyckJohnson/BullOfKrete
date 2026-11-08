"""The stack registry: built-in and installed stacks.

Built-in stacks are folders holding `stack.toml` directly under the built-in roots; installed
stacks live in `<user_data_dir>/stacks/<name>/`. The registry scans the folders on every call,
so a stack installed through any registry is seen at once.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import Maturity, Stack, StackError, StackRegistry
from bull.Modules.stacks.loader import load_readers
from bull.Modules.stacks.manifest import MANIFEST_FILE, SURVEYOR_AGENT, parse_manifest

INSTALLED_DIR = "stacks"
_TEMPLATE_FOLDER = "_template"


class LiveStackRegistry(StackRegistry):
    """Finds stacks under the built-in roots and the user's installed-stacks folder."""

    def __init__(self, builtin_roots: Sequence[Path], user_data_dir: Path) -> None:
        self._builtin_roots = tuple(builtin_roots)
        self._installed_root = user_data_dir / INSTALLED_DIR

    def all(self, include_test: bool = False) -> list[Stack]:
        stacks = [
            self._load(folder, builtin) for folder, builtin in self._folders().values()
        ]
        if not include_test:
            stacks = [s for s in stacks if s.manifest.maturity is not Maturity.TEST]
        return sorted(stacks, key=lambda s: s.manifest.name)

    def get(self, name: str) -> Stack:
        folders = self._folders()
        found = folders.get(name)
        if found is None:
            known = ", ".join(sorted(folders)) or "none"
            raise StackError(
                f"Unknown stack {name!r}. Known stacks: {known}.",
                "Run `bull stacks --all` to list them, or `bull stack install <folder>`.",
            )
        folder, builtin = found
        return self._load(folder, builtin)

    def load_path(self, path: Path) -> Stack:
        folder = path.resolve()
        builtin = any(folder.parent == root.resolve() for root in self._builtin_roots)
        return self._load(path, builtin)

    def install(self, path: Path) -> Stack:
        source = self._load(path, builtin=False)
        name = source.manifest.name
        if name in self._builtin_folders():
            raise StackError(
                f"Cannot install {name!r}: a built-in stack has that name.",
                "Rename the stack (its folder and stack.toml `name`) and install it again.",
            )
        target = self._installed_root / name
        staging = self._installed_root / f".{name}.installing"
        self._installed_root.mkdir(parents=True, exist_ok=True)
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(path, staging, ignore=shutil.ignore_patterns("__pycache__"))
        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)
        return self._load(target, builtin=False)

    # -- helpers -----------------------------------------------------------------------------

    def _load(self, folder: Path, builtin: bool) -> Stack:
        """Parse the manifest, import the readers and apply the checks that need both."""
        manifest = parse_manifest(folder)
        readers, optional = load_readers(folder, manifest.name)
        if optional.detect is not None and SURVEYOR_AGENT not in manifest.agents:
            raise StackError(
                f"{folder / MANIFEST_FILE} has problems:\n"
                f"- stack.agents: missing required agent {SURVEYOR_AGENT!r} "
                "(needed because readers.py defines detect)",
                'Add "surveyor" to stack.agents (and its rules), or remove detect.',
            )
        return Stack(
            manifest=manifest,
            home=folder,
            builtin=builtin,
            readers=readers,
            optional=optional,
        )

    def _builtin_folders(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for root in self._builtin_roots:
            for folder in _stack_folders(root):
                found.setdefault(folder.name, folder)
        return found

    def _folders(self) -> dict[str, tuple[Path, bool]]:
        """Every stack folder by name; a built-in stack wins over an installed one."""
        found: dict[str, tuple[Path, bool]] = {
            name: (folder, True) for name, folder in self._builtin_folders().items()
        }
        for folder in _stack_folders(self._installed_root):
            found.setdefault(folder.name, (folder, False))
        return found


def _stack_folders(root: Path) -> list[Path]:
    """Folders directly under `root` that hold a `stack.toml`, sorted; none if `root` is absent."""
    if not root.is_dir():
        return []
    return sorted(
        child
        for child in root.iterdir()
        if child.is_dir()
        and not child.name.startswith(".")
        and child.name != _TEMPLATE_FOLDER
        and (child / MANIFEST_FILE).is_file()
    )
