"""bull's own settings keys (the config.toml table)."""

from __future__ import annotations

import re

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import Layer, Setting, SettingType, SettingValue

_ALL = frozenset({Layer.BULL, Layer.STACK, Layer.USER, Layer.APP, Layer.PART})
_USER_APP = frozenset({Layer.BULL, Layer.USER, Layer.APP})

BULL_SCHEMA: tuple[Setting, ...] = (
    Setting(
        key="base_branch",
        type=SettingType.STR,
        default="main",
        description="Branch that modules merge into",
        layers=_USER_APP,
    ),
    Setting(
        key="review_mode",
        type=SettingType.CHOICE,
        default="combined",
        description="Review in one combined pass or one pass per category",
        choices=("combined", "split"),
        layers=_ALL,
    ),
    Setting(
        key="max_attempts",
        type=SettingType.INT,
        default=3,
        description="Attempts per work unit before it is blocked",
        minimum=1,
        layers=_ALL,
    ),
    Setting(
        key="max_files_per_unit",
        type=SettingType.INT,
        default=4,
        description="Most files in one work unit",
        minimum=1,
        layers=_ALL,
    ),
    Setting(
        key="usage.pause_5h",
        type=SettingType.INT,
        default=85,
        description="Pause when the 5-hour plan usage reaches this percent",
        minimum=1,
        maximum=100,
        layers=_USER_APP,
    ),
    Setting(
        key="usage.pause_weekly",
        type=SettingType.INT,
        default=95,
        description="Pause when the weekly plan usage reaches this percent",
        minimum=1,
        maximum=100,
        layers=_USER_APP,
    ),
    Setting(
        key="coverage.exclude",
        type=SettingType.STR_LIST,
        default=None,
        description="Globs of files left out of coverage (set by the stack)",
        layers=frozenset({Layer.STACK, Layer.APP, Layer.PART}),
    ),
    Setting(
        key="coverage.exclude_extra",
        type=SettingType.STR_LIST,
        default=(),
        description="Extra globs left out of coverage, added to coverage.exclude",
        layers=frozenset({Layer.BULL, Layer.APP, Layer.PART}),
    ),
    Setting(
        key="reference_dir",
        type=SettingType.STR,
        default="reference",
        description="Read-only folder of reference material",
        layers=frozenset({Layer.BULL, Layer.APP}),
    ),
    Setting(
        key="bookkeeping_paths",
        type=SettingType.STR_LIST,
        default=(".bull/", "docs/"),
        description="Paths whose changes alone never need a gate run",
        layers=frozenset({Layer.BULL, Layer.APP}),
    ),
    Setting(
        key="stack",
        type=SettingType.STR,
        default=None,
        description="Stack of the app (one-part) or of the part",
        layers=frozenset({Layer.APP, Layer.PART}),
    ),
    Setting(
        key="dir",
        type=SettingType.STR,
        default=".",
        description="Folder of the part, relative to the app root",
        layers=frozenset({Layer.BULL, Layer.PART}),
    ),
)

_MODELS_PREFIX = "models."
_SONNET_AGENTS = frozenset(
    {
        "test-writer",
        "reviewer",
        "coverage-analyst",
        "journey-test-writer",
        "surveyor",
        "legacy-test-scanner",
    }
)
_BY_KEY = {s.key: s for s in BULL_SCHEMA}
_INT_TEXT = re.compile(r"[+-]?[0-9]+")


def _model_setting(agent: str) -> Setting:
    return Setting(
        key=_MODELS_PREFIX + agent,
        type=SettingType.STR,
        default="sonnet" if agent in _SONNET_AGENTS else "inherit",
        description=f"Model the {agent} agent runs on",
        layers=_USER_APP,
    )


def find_setting(key: str) -> Setting | None:
    """The bull setting for `key`, or None when bull has no such key.

    Any `models.<agent>` key (one non-empty, undotted agent name) is a setting.
    """
    found = _BY_KEY.get(key)
    if found is not None:
        return found
    if key.startswith(_MODELS_PREFIX):
        agent = key[len(_MODELS_PREFIX) :]
        if agent and "." not in agent:
            return _model_setting(agent)
    return None


def _int_message(setting: Setting) -> str:
    low, high = setting.minimum, setting.maximum
    if low is not None and high is not None:
        return f"{setting.key} must be an integer from {low} to {high}"
    if low is not None:
        return f"{setting.key} must be an integer ≥ {low}"
    if high is not None:
        return f"{setting.key} must be an integer ≤ {high}"
    return f"{setting.key} must be an integer"


def _parse_int(setting: Setting, raw: str) -> int:
    text = raw.strip()
    if not _INT_TEXT.fullmatch(text):
        raise BullError(_int_message(setting))
    value = int(text)
    if (setting.minimum is not None and value < setting.minimum) or (
        setting.maximum is not None and value > setting.maximum
    ):
        raise BullError(_int_message(setting))
    return value


def parse_value(setting: Setting, raw: str) -> SettingValue:
    """Parse command-line text into a value of `setting`'s type.

    Ints must be whole numbers within the setting's range, bools `true` or `false`,
    choices one of the setting's choices; lists are comma-separated (blank items dropped).

    Raises:
        BullError: the text isn't a valid value; the message names the key and what it expects.
    """
    if setting.type is SettingType.INT:
        return _parse_int(setting, raw)
    if setting.type is SettingType.BOOL:
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise BullError(f"{setting.key} must be true or false")
    if setting.type is SettingType.CHOICE:
        if raw in setting.choices:
            return raw
        raise BullError(f"{setting.key} must be one of: {', '.join(setting.choices)}")
    if setting.type is SettingType.STR_LIST:
        return tuple(item.strip() for item in raw.split(",") if item.strip())
    return raw
