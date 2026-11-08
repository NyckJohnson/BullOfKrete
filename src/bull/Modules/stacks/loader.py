"""Imports a stack folder's `readers.py`.

The folder is registered as a package named `bull_stack_<name>` (its `__path__` is the stack
folder), and `readers.py` is imported as `bull_stack_<name>.readers`, so it can import sibling
files relatively (`from .helper import x`). Loading the same name again replaces the earlier
package and its submodules, so a reinstalled stack is picked up fresh.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from bull.Modules.stacks.Contracts import OptionalReaders, StackError, StackReaders

READERS_FILE = "readers.py"
PACKAGE_PREFIX = "bull_stack_"
REQUIRED_READERS = ("contract_declarations", "test_results", "uncovered", "check")
_FIX = "Fix the stack's readers.py (see the stack-author guide) and try again."


def load_readers(folder: Path, name: str) -> tuple[StackReaders, OptionalReaders]:
    """Import `folder/readers.py` as package `bull_stack_<name>`.

    Raises `StackError` if the file is missing, fails to import, or lacks a required function.
    """
    path = folder / READERS_FILE
    if not path.is_file():
        raise StackError(f"{folder} has no {READERS_FILE}.", _FIX)

    package_name = PACKAGE_PREFIX + name
    module_name = f"{package_name}.readers"
    _forget(package_name)

    package_spec = importlib.util.spec_from_loader(
        package_name, loader=None, is_package=True
    )
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if package_spec is None or module_spec is None or module_spec.loader is None:
        raise StackError(f"Cannot import {path}.", _FIX)
    package_spec.submodule_search_locations = [str(folder)]
    package = importlib.util.module_from_spec(package_spec)
    sys.modules[package_name] = package

    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    # Any error raised by the stack's own code is reported as a StackError, not raised raw.
    except Exception as error:
        _forget(package_name)
        raise StackError(
            f"Importing {path} failed: {type(error).__name__}: {error}", _FIX
        ) from error
    package.readers = module  # type: ignore[attr-defined]

    missing = [fn for fn in REQUIRED_READERS if not callable(getattr(module, fn, None))]
    if missing:
        _forget(package_name)
        raise StackError(
            f"{path} is missing required function(s): {', '.join(missing)}", _FIX
        )

    optional = OptionalReaders(
        detect=_optional(module, "detect"),
        inventory=_optional(module, "inventory"),
        legacy_declarations=_optional(module, "legacy_declarations"),
        interface_check=_optional(module, "interface_check"),
    )
    return cast(StackReaders, module), optional


def _optional(module: ModuleType, name: str) -> Callable[..., Any] | None:
    """The module's function `name`, or None when it does not define one."""
    value = getattr(module, name, None)
    return cast("Callable[..., Any]", value) if callable(value) else None


def _forget(package_name: str) -> None:
    """Drop an earlier import of the package and all its submodules from `sys.modules`."""
    prefix = package_name + "."
    for key in [k for k in sys.modules if k == package_name or k.startswith(prefix)]:
        del sys.modules[key]
