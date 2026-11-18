# Python CLI stack: design

How the `python_cli` stack builds, tests and checks a Python command-line tool. `bull stack rules
<agent>` prints the agents' rules (`rules.md`); `bull stack setup` prints the manual steps
(`setup.md`).

## Language and tools

- Python 3.11 or newer. `from __future__ import annotations` at the top of every source file.
- `uv` creates the venv, installs dependencies and runs every tool (`uv run …`); it fetches a
  matching Python itself.
- `pyproject.toml` at the part root, built with `hatchling`; the console script is
  `<package> = "<package>.cli:main"`.
- Tests: pytest. `bull gates <module> --fast` runs `pytest tests/<module>`. A test's id is its
  pytest node id, `tests/<module>/test_x.py::test_name`; that is the id bull stores and
  `bull gates --failed` reruns.
- Coverage: coverage.py through `pytest --cov` (the `pytest-cov` plugin), written as `coverage json`
  and read back from it.
- Lint: `ruff check` and `ruff format --check`.
- Types: `mypy --strict` runs inside the build step, so a type error fails the build, not lint.
- Requires: `uv` (`[[stack.requires]]` in `stack.toml`).

## Contracts

A module's contract is `Modules/<module>/Contracts/__init__.py`. `readers.contract_declarations`
reads it with Python's `ast`, a real parser: decorators, multi-line signatures and docstrings are
handled, and formatting never changes the result. It lists, in file order:

- top-level public classes with their bases and decorators (`@dataclass`, `Protocol`);
- their public methods as `def name(args) -> ret`, prefixed with `@property`, `@classmethod`,
  `@staticmethod` or `@abstractmethod` when decorated so;
- dataclass fields as `name: type`, and enum members;
- public functions and type aliases.

Names starting with `_` are private and skipped.

## Modules

```
src/<package>/
  cli.py                      the console script (app shell, not a module)
  Modules/<module>/
    Contracts/__init__.py     the contract
    mocks/__init__.py         Mock<Protocol> classes for other modules' tests
    <file>.py                 the implementation
tests/
  <module>/test_<file>.py     unit tests
  journey/test_<command>.py   journey tests
```

`Modules` and `Contracts` are capitalized by bull's module convention (the same for every stack);
they import as `<package>.Modules.<other>.Contracts`. The ruff `N` (naming) rules are off for
that reason. `mocks` is lowercase: that is this stack's choice, and nothing reads it by a fixed
path. Mocks are left out of coverage (`coverage.exclude` default `["*/mocks/*", "*/Views/*"]`).

`source_glob = "*.py"`, `test_glob = ["test_*.py", "*_test.py"]`.

## Kind

`tool`. Journey tests run the installed console script as a real subprocess in a temp folder and
check its exit code, its output and the files it writes. They never call `cli.main()` in-process,
which would miss packaging and entry-point mistakes.

## Human setup

Once per app: install `uv`, write `pyproject.toml` from the template in `setup.md`, create the
package's `__init__.py` and `cli.py`, set the `package` setting, and run `uv sync`. `bull stack
check` then verifies that `uv` is on PATH, `pyproject.toml` is present, the package imports, and
the app's Python is 3.11 or newer.

## Adoption support

None for now: no `detect`, `inventory` or `legacy_declarations`. There is no existing Python app
to adopt yet, and detection built without one would only guess.

## Interfaces and running

- Interfaces: `[interfaces] formats = ["json-schema"]`, checked by `schema_check.py` (stdlib only)
  through `readers.interface_check`. The side's `Contracts/__init__.py` must declare a dataclass
  named after the schema's `title`, one field per property with the matching type (`string` →
  `str`, `integer` → `int`, `number` → `float`, `boolean` → `bool`, `array` → `list[...]`; a
  property not in `required` is `X | None`). Each mismatch is one item naming the field and the
  role (provider or consumer).
- Running: no `[run]` section. The stack builds a tool, not a service.

## Decisions log

- 2026-11-03: Python 3.11 floor, `uv` for every tool, `hatchling` as the build backend; adoption
  support deferred until there is a Python app to adopt.
- 2026-11-03: contracts are read with `ast`, not a line scanner, so formatting can't change them.
- 2026-11-03: `mypy --strict` runs in the build step, since a type error is a build failure.
- 2026-11-03: capitalized `Modules`/`Contracts` folders (bull's convention); ruff's `N` rules off.
- 2026-11-17: rebuilt for bull v2: gates in `gates.py`, readers in `readers.py`, json-schema
  interfaces, `pytest-cov` added to the `pyproject.toml` template, `shellcheck` dropped.
