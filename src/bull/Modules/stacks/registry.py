"""The stack registry: built-in and installed stacks.

Built-in stacks are folders holding `stack.toml` directly under the built-in roots; installed
stacks live in `<user_data_dir>/stacks/<name>/`. The registry scans the folders on every call,
so a stack installed through any registry is seen at once. Stack folders listed in the
`BULL_EXTRA_STACKS` environment variable (`os.pathsep`-separated, read on every call) are added
too; one wins over an installed stack of the same name, a built-in stack wins over both.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import Maturity, Stack, StackError, StackRegistry
from bull.Modules.stacks.loader import load_readers
from bull.Modules.stacks.manifest import MANIFEST_FILE, SURVEYOR_AGENT, parse_manifest

INSTALLED_DIR = "stacks"
EXTRA_STACKS_ENV = "BULL_EXTRA_STACKS"
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
        return self._load(folder, builtin)

    def install(self, path: Path) -> Stack:
        path = path.resolve()
        # Check the name from the manifest alone first: a refused install must not import the
        # stack's readers, which would replace a built-in stack's package in `sys.modules`.
        name = parse_manifest(path).name
        if name in self._builtin_folders():
            raise StackError(
                f"Cannot install {name!r}: a built-in stack has that name.",
                "Rename the stack (its folder and stack.toml `name`) and install it again.",
            )
        self._load(path, builtin=False)
        target = self._installed_root / name
        staging = self._installed_root / f".{name}.installing"
        backup = self._installed_root / f".{name}.previous"
        try:
            self._installed_root.mkdir(parents=True, exist_ok=True)
            _remove(staging)
            _remove(backup)
            shutil.copytree(path, staging, ignore=shutil.ignore_patterns("__pycache__"))
            _swap_into_place(staging, target, backup)
        except OSError as error:
            raise StackError(
                f"Cannot install {name!r} into {target}: {error}",
                "Check the folder's permissions and free disk space, then install it again.",
            ) from error
        finally:
            _remove_quietly(staging)
        _remove_quietly(backup)
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
        """Every stack folder by name: built-in first, then `BULL_EXTRA_STACKS`, then installed."""
        found: dict[str, tuple[Path, bool]] = {
            name: (folder, True) for name, folder in self._builtin_folders().items()
        }
        for folder in _extra_stack_folders():
            found.setdefault(folder.name, (folder, False))
        for folder in _stack_folders(self._installed_root):
            found.setdefault(folder.name, (folder, False))
        return found


def _extra_stack_folders() -> list[Path]:
    """Stack folders listed in `BULL_EXTRA_STACKS`, in order, resolved.

    Empty entries, missing paths and folders without a `stack.toml` are skipped.
    """
    value = os.environ.get(EXTRA_STACKS_ENV, "")
    folders: list[Path] = []
    for entry in value.split(os.pathsep):
        if not entry:
            continue
        folder = Path(entry).resolve()
        if folder.is_dir() and (folder / MANIFEST_FILE).is_file():
            folders.append(folder)
    return folders


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


def _remove(folder: Path) -> None:
    """Delete `folder` and its contents if it exists; raises `OSError` on failure."""
    if folder.exists():
        shutil.rmtree(folder)


def _remove_quietly(folder: Path) -> None:
    """Best-effort cleanup of a leftover staging or backup folder.

    Used only after the outcome of an install is settled: a folder that cannot be removed is
    hidden (its name starts with `.`) and is ignored by every scan, so it is left behind rather
    than turning a finished install, or the error being reported, into a different error.
    """
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


def _swap_into_place(staging: Path, target: Path, backup: Path) -> None:
    """Move `staging` to `target`, keeping any earlier `target` until the move succeeds.

    The earlier install is renamed to `backup` first and renamed back if the move fails, so a
    failed reinstall leaves the earlier install intact. Raises `OSError` on failure.
    """
    if not target.exists():
        staging.rename(target)
        return
    target.rename(backup)
    try:
        staging.rename(target)
    except OSError:
        backup.rename(target)
        raise
