"""json-schema interface check for python_cli contracts (stdlib only).

One side of an interface (provider or consumer) passes when its module's `Contracts/__init__.py`
declares a `@dataclass` named after the schema's `title`, with exactly one field per schema
property and the matching type:

    string → str, integer → int, number → float, boolean → bool, array → list[<items>]

A property not listed in `required` must be declared `X | None` (or `Optional[X]`); a required
one must not. The contract file is read with `ast`, never imported, so formatting and comments
don't matter and nothing in the app runs.

Bad input never raises: a missing or unparsable file, a schema that isn't a JSON object with a
`title` and a `properties` object, or an unsupported format each give one failing `Finding`.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

FORMAT = "json-schema"
"""The one interface format this checker reads."""

_SCALARS = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
_LIST_NAMES = frozenset({"list", "List"})
_OPTIONAL_NAMES = frozenset({"Optional"})
_UNION_NAMES = frozenset({"Union"})
_CLASSVAR_NAMES = frozenset({"ClassVar"})


@dataclass(frozen=True)
class Finding:
    """One line of the check: `ok`, what was checked (`item`) and how to fix a failure."""

    ok: bool
    item: str
    fix: str


class _BadInput(Exception):
    """A file or schema the check can't use; its message is the failing item's text."""

    def __init__(self, item: str, fix: str) -> None:
        super().__init__(item)
        self.item = item
        self.fix = fix


# --- schema --------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Property:
    name: str
    type: str | None
    """The Python type the property maps to (`str`, `list[int]`, …); None when unsupported."""
    schema_type: str
    required: bool


def _python_type(spec: object) -> str | None:
    """The Python type for one property schema, or None when its type isn't supported."""
    if not isinstance(spec, dict):
        return None
    kind = spec.get("type")
    if isinstance(kind, str) and kind in _SCALARS:
        return _SCALARS[kind]
    if kind == "array":
        items = spec.get("items")
        if items is None:
            return "list"
        inner = _python_type(items)
        return f"list[{inner}]" if inner else None
    return None


def _describe(spec: object) -> str:
    if isinstance(spec, dict):
        kind = spec.get("type")
        if kind == "array" and isinstance(spec.get("items"), dict):
            return f"array of {_describe(spec['items'])}"
        if isinstance(kind, str):
            return kind
    return "no type"


def _load_schema(path: Path) -> tuple[str, list[_Property]]:
    """The schema's title and properties, in file order; raises `_BadInput`."""
    fix = f"fix the interface file {path.name}: a JSON object with `title` and `properties`"
    try:
        data = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError) as exc:
        raise _BadInput(f"interface file {path.name} is readable", f"{exc}") from exc
    except json.JSONDecodeError as exc:
        raise _BadInput(
            f"interface file {path.name} is valid JSON", f"{fix} ({exc})"
        ) from exc
    if not isinstance(data, dict):
        raise _BadInput(f"interface file {path.name} is a JSON object", fix)
    title = data.get("title")
    if not isinstance(title, str) or not title.isidentifier():
        raise _BadInput(
            f"interface file {path.name} has a `title` that is a Python class name", fix
        )
    properties = data.get("properties", {})
    if not isinstance(properties, dict):
        raise _BadInput(f"interface file {path.name} has a `properties` object", fix)
    required_list = data.get("required", [])
    required = (
        {r for r in required_list if isinstance(r, str)}
        if isinstance(required_list, list)
        else set()
    )
    props = [
        _Property(
            name=str(name),
            type=_python_type(spec),
            schema_type=_describe(spec),
            required=name in required,
        )
        for name, spec in properties.items()
    ]
    return title, props


# --- contract ------------------------------------------------------------------------------


def _last_name(node: ast.expr) -> str:
    """`dataclass` for `dataclass`, `dataclasses.dataclass` and either one called."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _find_class(path: Path, title: str) -> ast.ClassDef | None:
    """The top-level class named `title` in the contract file; raises `_BadInput`."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise _BadInput(
            f"contract file {path} is readable",
            f"create it with a `@dataclass class {title}` ({exc.__class__.__name__})",
        ) from exc
    try:
        tree = ast.parse(text, filename=str(path))
    except (SyntaxError, ValueError) as exc:
        raise _BadInput(
            f"contract file {path} parses", f"fix the syntax error: {exc}"
        ) from exc
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == title:
            return node
    return None


def _annotation(node: ast.expr) -> ast.expr:
    """A string annotation (`"int"`) parsed into an expression; any other node unchanged."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return node
    return node


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _union_members(node: ast.expr) -> list[ast.expr]:
    """`A | B | None` and `Union[A, B, None]` flattened; any other node as a one-item list."""
    node = _annotation(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return [*_union_members(node.left), *_union_members(node.right)]
    if isinstance(node, ast.Subscript) and _last_name(node.value) in _UNION_NAMES:
        args = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        return [m for a in args for m in _union_members(a)]
    if isinstance(node, ast.Subscript) and _last_name(node.value) in _OPTIONAL_NAMES:
        return [*_union_members(node.slice), ast.Constant(value=None)]
    return [node]


def _type_text(node: ast.expr) -> str | None:
    """A non-optional annotation normalized to the checker's spelling (`list[int]`), or None."""
    node = _annotation(node)
    if isinstance(node, ast.Name | ast.Attribute):
        name = _last_name(node)
        return "list" if name in _LIST_NAMES else name
    if isinstance(node, ast.Subscript) and _last_name(node.value) in _LIST_NAMES:
        inner = _type_text(node.slice)
        return f"list[{inner}]" if inner else None
    return None


def _split_optional(node: ast.expr) -> tuple[str | None, bool]:
    """The annotation's base type text and whether it allows None."""
    members = _union_members(node)
    optional = any(_is_none(m) for m in members)
    rest = [m for m in members if not _is_none(m)]
    if len(rest) != 1:
        return None, optional
    return _type_text(rest[0]), optional


def _fields(cls: ast.ClassDef) -> dict[str, ast.expr]:
    """The class's annotated fields (ClassVar ones skipped), in source order."""
    out: dict[str, ast.expr] = {}
    for node in cls.body:
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        ann = _annotation(node.annotation)
        base = ann.value if isinstance(ann, ast.Subscript) else ann
        if _last_name(base) in _CLASSVAR_NAMES:
            continue
        out[node.target.id] = node.annotation
    return out


# --- check ---------------------------------------------------------------------------------


def _compare(
    role: str, title: str, props: list[_Property], fields: dict[str, ast.expr]
) -> list[Finding]:
    where = f"{role} `{title}`"
    out: list[Finding] = []
    names = {p.name for p in props}
    for prop in props:
        expected = f"{prop.type} | None" if not prop.required else prop.type
        if prop.type is None:
            out.append(
                Finding(
                    ok=False,
                    item=f"{where} field `{prop.name}`: unsupported type ({prop.schema_type})",
                    fix="use string, integer, number, boolean or array in the interface file",
                )
            )
            continue
        ann = fields.get(prop.name)
        if ann is None:
            out.append(
                Finding(
                    ok=False,
                    item=f"{where} is missing field `{prop.name}` from the schema",
                    fix=f"add `{prop.name}: {expected}` to `{title}`",
                )
            )
            continue
        actual, optional = _split_optional(ann)
        shown = ast.unparse(ann)
        if actual != prop.type:
            out.append(
                Finding(
                    ok=False,
                    item=f"{where} field `{prop.name}` is `{shown}`; "
                    f"the schema says {prop.schema_type}",
                    fix=f"declare `{prop.name}: {expected}`",
                )
            )
        elif optional and prop.required:
            out.append(
                Finding(
                    ok=False,
                    item=f"{where} field `{prop.name}` is optional (`{shown}`) "
                    "but the schema requires it",
                    fix=f"declare `{prop.name}: {expected}`, or drop it from `required`",
                )
            )
        elif not optional and not prop.required:
            out.append(
                Finding(
                    ok=False,
                    item=f"{where} field `{prop.name}` is required (`{shown}`) "
                    "but the schema doesn't require it",
                    fix=f"declare `{prop.name}: {expected}`, or add it to `required`",
                )
            )
    for name in fields:
        if name not in names:
            out.append(
                Finding(
                    ok=False,
                    item=f"{where} has field `{name}` not in the schema",
                    fix=f"remove `{name}` from `{title}`, or add it to the interface file",
                )
            )
    return out


def check(contract: Path, schema: Path, format: str, role: str) -> list[Finding]:
    """Check one side's contract file against an interface file.

    `role` is the side's lowercase role name (`provider` or `consumer`); every failing item
    names it, and names the field when one is at fault. Returns one passing item when the
    dataclass matches, else one failing item per problem. Never raises for bad input.
    """
    if format != FORMAT:
        return [
            Finding(
                ok=False,
                item=f"interface format `{format}` is not supported",
                fix=f"the python_cli stack checks `{FORMAT}` interfaces only",
            )
        ]
    try:
        title, props = _load_schema(schema)
        cls = _find_class(contract, title)
    except _BadInput as bad:
        return [Finding(ok=False, item=f"{role}: {bad.item}", fix=bad.fix)]
    if cls is None:
        return [
            Finding(
                ok=False,
                item=f"{role} contract declares a dataclass `{title}`",
                fix=f"add `@dataclass class {title}` to {contract.name} in Contracts/",
            )
        ]
    if not any(_last_name(d) == "dataclass" for d in cls.decorator_list):
        return [
            Finding(
                ok=False,
                item=f"{role} `{title}` is a dataclass",
                fix=f"decorate `{title}` with `@dataclass` (or `@dataclass(frozen=True)`)",
            )
        ]
    problems = _compare(role, title, props, _fields(cls))
    if problems:
        return problems
    return [
        Finding(ok=True, item=f"{role} `{title}` matches {schema.name}", fix=""),
    ]
