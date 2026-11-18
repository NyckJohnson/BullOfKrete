"""Inventory of an adopted project's types and references."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def inventory(root: Path, settings: Mapping[str, object]) -> str:
    """Markdown inventory of the project's types and references (unit 4)."""
    raise NotImplementedError("inventory.inventory")
