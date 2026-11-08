"""settings contract: layered, validated settings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout, BullError

SettingValue = int | bool | str | tuple[str, ...]


class SettingType(Enum):
    INT = "int"
    BOOL = "bool"
    STR = "str"
    CHOICE = "choice"
    STR_LIST = "list"


class Layer(Enum):
    BULL = "bull default"
    STACK = "stack"
    USER = "user"
    APP = "app"
    PART = "part"


@dataclass(frozen=True)
class Setting:
    key: str
    type: SettingType
    default: SettingValue | None
    description: str
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    layers: frozenset[Layer] = frozenset(Layer)


@dataclass(frozen=True)
class Resolved:
    key: str
    value: SettingValue
    layer: Layer
    source: Path | None


@dataclass(frozen=True)
class ConfigProblem:
    file: Path
    line: int
    key: str
    message: str


class ConfigError(BullError):
    problems: list[ConfigProblem]


@dataclass(frozen=True)
class StackLayer:
    """A stack's own settings (schema) and its defaults for any key."""

    schema: tuple[Setting, ...]
    values: Mapping[str, SettingValue]


class Settings(Protocol):
    def schema(self) -> list[Setting]: ...
    def get(self, key: str, part: str | None = None) -> SettingValue: ...
    def show(self, part: str | None = None) -> list[Resolved]: ...
    def set(
        self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None
    ) -> Resolved: ...


class SettingsLoader(Protocol):
    def load(
        self, app: AppLayout | None, stack_layer: Callable[[str], StackLayer]
    ) -> Settings: ...
