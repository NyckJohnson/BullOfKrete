"""Tests for `bull.Modules.stack_ios.Contracts`: the contract declares nothing."""

from __future__ import annotations

import importlib


def test_contract_declares_no_public_names() -> None:
    module = importlib.import_module("bull.Modules.stack_ios.Contracts")
    public = {name for name in vars(module) if not name.startswith("_")}
    assert public <= {"annotations"}
