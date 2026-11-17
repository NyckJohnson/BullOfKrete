"""The `fixture` stack's readers: the functions bull imports from this folder.

The fixture language (see `rules.md`): in a `*.fx` file every non-blank line not starting with `#`
is a code line; `pub <decl>` declares a contract item, `pub Legacy<Name>` a legacy declaration,
and `field <name>: <type>` an interface field. Gate results come from `tool.py`:
`<results>/tests.json` (`{"count", "failed"}`) and `<results>/coverage.json` (part-root-relative
posix path → executed line numbers).
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import (
    CheckItem,
    CoverageData,
    Detection,
    Role,
    TestRun,
)

_SOURCE_GLOB = "*.fx"
_FIXTURE_TOML = "fixture.toml"
_SCHEMA_TYPES = ("string", "integer", "boolean")


class _SchemaError(Exception):
    """An interface file that cannot be read as a JSON schema with `properties`."""


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """(1-based number, stripped text) for each code line: non-blank, not a `#` comment."""
    out: list[tuple[int, str]] = []
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        text = raw.strip()
        if text and not text.startswith("#"):
            out.append((number, text))
    return out


def _pub_names(path: Path) -> list[str]:
    """The text after `pub ` on each `pub` line of one file."""
    names: list[str] = []
    for _, text in _code_lines(path):
        word, _, rest = text.partition(" ")
        rest = rest.strip()
        if word == "pub" and rest:
            names.append(rest)
    return names


def contract_declarations(path: Path) -> list[str]:
    """The contract declarations of one `.fx` file: the text after `pub ` on each `pub` line."""
    return _pub_names(path)


def legacy_declarations(path: Path) -> list[str]:
    """Every `pub Legacy<Name>` declaration in the `*.fx` files under the part root `path`."""
    found: list[str] = []
    for source in sorted(path.rglob(_SOURCE_GLOB)):
        if source.is_file():
            found.extend(n for n in _pub_names(source) if n.startswith("Legacy"))
    return found


def test_results(results: Path) -> TestRun | None:
    """The last test run from `<results>/tests.json`; None when it is missing or unreadable."""
    path = results / "tests.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    count = data.get("count")
    failed = data.get("failed")
    if not isinstance(count, int) or not isinstance(failed, list):
        return None
    return TestRun(count=count, failed=tuple(str(f) for f in failed))


def _covered(results: Path) -> dict[str, set[int]]:
    """`coverage.json` as path → executed lines; empty when missing or malformed."""
    path = results / "coverage.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, set[int]] = {}
    for key, lines in data.items():
        if isinstance(lines, list):
            out[str(key)] = {n for n in lines if isinstance(n, int)}
    return out


def uncovered(part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData:
    """Code lines minus executed lines, per source; a file with no code lines has no data.

    Keys are the given source paths; files with every code line covered are omitted. A file
    missing from `coverage.json` is entirely uncovered.
    """
    covered = _covered(results)
    missing: dict[Path, tuple[int, ...]] = {}
    no_data: list[Path] = []
    for source in sources:
        lines = [number for number, _ in _code_lines(source)]
        if not lines:
            no_data.append(source)
            continue
        try:
            key = source.relative_to(part_root).as_posix()
        except ValueError:
            key = source.as_posix()
        hit = covered.get(key, set())
        left = tuple(n for n in lines if n not in hit)
        if left:
            missing[source] = left
    return CoverageData(uncovered=missing, no_data=tuple(no_data))


def check(
    part_root: Path, settings: Mapping[str, object], adopting: bool
) -> list[CheckItem]:
    """The part's setup: `fixture.toml` exists, parses, and does not say `ok = false`."""
    path = part_root / _FIXTURE_TOML
    if not path.is_file():
        return [
            CheckItem(
                ok=False,
                item="fixture.toml present at the part root",
                fix="create an empty fixture.toml in the part folder (see `stack setup`)",
            )
        ]
    items = [CheckItem(ok=True, item="fixture.toml present at the part root", fix="")]
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        items.append(
            CheckItem(
                ok=False,
                item="fixture.toml is valid TOML",
                fix=f"fix fixture.toml: {exc}",
            )
        )
        return items
    if data.get("ok") is False:
        items.append(
            CheckItem(
                ok=False,
                item="fixture.toml says not ok",
                fix="set `ok = true` in fixture.toml (or remove the line)",
            )
        )
    return items


def detect(root: Path) -> Detection:
    """Recognise a fixture project: confidence 0.9 with both `fixture.toml` and `*.fx` files."""
    has_toml = (root / _FIXTURE_TOML).is_file()
    has_sources = any(p.is_file() for p in root.rglob(_SOURCE_GLOB))
    if has_toml and has_sources:
        confidence, summary = 0.9, "fixture project: fixture.toml and *.fx sources"
    elif has_toml:
        confidence, summary = 0.3, "fixture.toml but no *.fx sources"
    elif has_sources:
        confidence, summary = 0.3, "*.fx sources but no fixture.toml"
    else:
        confidence, summary = 0.0, "no fixture project here"
    return Detection(
        confidence=confidence,
        summary=summary,
        settings={"source_dir": "src", "test_dir": "tests"} if confidence else {},
        issues=(),
    )


def _schema_fields(interface: Path) -> dict[str, str]:
    """The schema's `properties` as name → type; raises _SchemaError when unusable."""
    try:
        data = json.loads(interface.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise _SchemaError(f"cannot read {interface.name}: {exc}") from exc
    props = data.get("properties") if isinstance(data, dict) else None
    if not isinstance(props, dict):
        raise _SchemaError(f"{interface.name} has no `properties` object")
    out: dict[str, str] = {}
    for name, spec in props.items():
        kind = spec.get("type") if isinstance(spec, dict) else None
        out[str(name)] = kind if isinstance(kind, str) else ""
    return out


def _module_fields(contracts: Path) -> dict[str, str]:
    """`field <name>: <type>` lines in the module's `Contracts/*.fx`, as name → type."""
    out: dict[str, str] = {}
    if not contracts.is_dir():
        return out
    for path in sorted(contracts.glob(_SOURCE_GLOB)):
        for _, text in _code_lines(path):
            word, _, rest = text.partition(" ")
            if word != "field":
                continue
            name, _, kind = rest.partition(":")
            if name.strip():
                out[name.strip()] = kind.strip()
    return out


def interface_check(
    part_root: Path,
    settings: Mapping[str, object],
    interface: Path,
    format: str,
    role: Role,
    module: str,
) -> list[CheckItem]:
    """Compare a module's `field` lines with a JSON schema's `properties` names and types.

    Fields are read from `<part_root>/<source_dir>/Modules/<module>/Contracts/*.fx`
    (`source_dir` from settings, default `src`). Every mismatch is one failing item; a full
    match gives one passing item.
    """
    side = role.value
    if format != "json-schema":
        return [
            CheckItem(
                ok=False,
                item=f"interface format `{format}` is not supported",
                fix="the fixture stack reads json-schema interfaces only",
            )
        ]
    try:
        schema = _schema_fields(interface)
    except _SchemaError as exc:
        return [CheckItem(ok=False, item=str(exc), fix="fix the interface file")]
    source = settings.get("source_dir")
    source_dir = source if isinstance(source, str) and source else "src"
    contracts = part_root / source_dir / "Modules" / module / "Contracts"
    fields = _module_fields(contracts)
    where = f"{source_dir}/Modules/{module}/Contracts/"
    items: list[CheckItem] = []
    for name in sorted(fields.keys() - schema.keys()):
        items.append(
            CheckItem(
                ok=False,
                item=f"{side} has field `{name}` not in the schema",
                fix=f"remove `field {name}` from {where} or add it to {interface.name}",
            )
        )
    for name in sorted(schema.keys() - fields.keys()):
        items.append(
            CheckItem(
                ok=False,
                item=f"{side} lacks field `{name}` from the schema",
                fix=f"add `field {name}: {schema[name]}` to {where}",
            )
        )
    for name in sorted(fields.keys() & schema.keys()):
        want = schema[name]
        if want not in _SCHEMA_TYPES:
            items.append(
                CheckItem(
                    ok=False,
                    item=f"schema field `{name}` has unsupported type `{want}`",
                    fix=f"use one of {', '.join(_SCHEMA_TYPES)} in {interface.name}",
                )
            )
        elif fields[name] != want:
            items.append(
                CheckItem(
                    ok=False,
                    item=f"{side} field `{name}` is `{fields[name]}`, the schema says `{want}`",
                    fix=f"change it to `field {name}: {want}` in {where}",
                )
            )
    if not items:
        items.append(
            CheckItem(ok=True, item=f"{side} fields match {interface.name}", fix="")
        )
    return items
