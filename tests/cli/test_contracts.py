"""Tests for the cli contract module: it declares nothing."""

from __future__ import annotations

import importlib
import inspect
import types

_MODULE = "bull.Modules.cli.Contracts"


def _public_names(mod: types.ModuleType) -> list[str]:
    return [n for n in vars(mod) if not n.startswith("_")]


def test_contract_module_imports() -> None:
    assert isinstance(importlib.import_module(_MODULE), types.ModuleType)


def test_contract_module_declares_no_public_names() -> None:
    mod = importlib.import_module(_MODULE)
    declared = [
        n
        for n in _public_names(mod)
        if getattr(getattr(mod, n), "__module__", None) == _MODULE
    ]
    assert declared == []


def test_contract_module_defines_no_classes_or_functions() -> None:
    mod = importlib.import_module(_MODULE)
    members = [
        n
        for n, obj in vars(mod).items()
        if (inspect.isclass(obj) or inspect.isfunction(obj))
        and getattr(obj, "__module__", None) == _MODULE
    ]
    assert members == []
