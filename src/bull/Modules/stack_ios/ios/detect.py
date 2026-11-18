"""Detects an existing Xcode project for adoption."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.stacks.Contracts import Detection


def detect(root: Path) -> Detection:
    """How well an existing Xcode project under `root` fits the stack (unit 4)."""
    raise NotImplementedError("detect.detect")
