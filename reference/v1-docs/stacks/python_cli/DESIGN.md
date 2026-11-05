<!--
This is the discussion record and build checklist for a new stack, created by
`ios-pipeline stack new python_cli` and filled in by `/new-stack` (stacks/README.md "Adding a stack").
Keep the headings; /new-stack resumes from the checked boxes at the bottom.
-->

# python_cli stack: design

## Language and tools
- Language and version: Python 3.11+.
- Package/build tool: `uv` (one tool for the venv, installing dependencies, and running commands —
  no separate "install Python" step for the human; `uv` can fetch a matching Python itself).
  `pyproject.toml` with the `hatchling` build backend (minimal config for a `src/` layout).
- Test framework: `pytest`.
  - Run one module's tests only (`--fast`): `pytest tests/<module>/`.
  - Run a single failing test by id (`--failed`): `pytest "<nodeid>"` (pytest's own node id —
    `tests/<module>/test_file.py::test_name` — is what gets written to `FAILED_TESTS`).
- Coverage tool and data format: `coverage.py` via `pytest --cov`, read back with `coverage json`
  (machine-readable per-file executed/missing line numbers — the Python-native equivalent of
  iOS's `xccov`).
- Lint tool(s): `ruff check` (lint) — covers most of what SwiftLint does for iOS, in one fast tool.
- Format tool: `ruff format --check`.
- Type checking: `mypy --strict`, run as part of the **build** gate (`stack_build_test`), not a
  separate lint step — an untyped/mistyped contract is a build error here, the same way a Swift
  compiler error is, not a style nit.
- Shell scripts: if a module happens to ship a `.sh` file, `shellcheck` runs on it inside
  `stack_lint` alongside `ruff`; most modules won't have any, so this rarely fires.

## Contracts
A contract is a module's `contracts/__init__.py`: `typing.Protocol` classes (the interfaces other
modules depend on), `@dataclass`es and `Enum`s (the shared data types) — the Python equivalent of
Swift's protocols-plus-models `Contracts/` folder.

`contract.py` uses Python's own `ast` module — a **real parser**, not a line scanner like iOS's.
Python ships `ast` in the standard library and it trivially handles decorators, multi-line
signatures, nested classes and docstrings correctly, so there's no reason to approximate with
regex the way iOS's scanner has to for Swift. `extract(path)` walks the module's top-level
`ClassDef`/`FunctionDef`/`Assign`(for `TypeAlias`) nodes, skips anything starting with `_`, and
renders each as a normalized signature string (class name + bases, each method's `def name(args) ->
ret:`, each dataclass field's `name: type`, each enum member) — so a change to a method's
signature, a field's type, or an added/removed public member shows up as a contract change, the
same granularity iOS's scanner aims for.

## Modules
Mirrors the language's own normal layout, with two folder names that aren't this stack's choice —
they're fixed by the stack-neutral driver, same as iOS:
- `workflow/gates.sh`'s shared `module_src`/`module_tests`/`module_names` helpers hardcode the
  module folder as literal `Modules/` directly under `APP_SOURCE_DIR`.
- `workflow/public_api.py` (the `ios-pipeline api` command, stack-neutral) reads a module's
  contract from literal `Modules/<module>/Contracts/` — `stacks/README.md`'s spec for
  `contract.py` says the same ("every non-private declaration in one `Contracts/` file").

```
src/<package>/             # APP_SOURCE_DIR
    Modules/
        <module>/
            Contracts/__init__.py   # Protocols, dataclasses, enums — the module's public contract
            mocks/__init__.py       # Mock implementations of this module's Protocols, for other modules' tests
            <module>.py             # the real implementation (plus more .py files if it grows)
tests/                     # APP_TEST_DIR
    <module>/
        test_<module>.py
```

`src/<package>/` is a normal installable package (`pyproject.toml`'s `[project] name`); `Modules`
and `Contracts` are subpackages under it (capitalized to satisfy the shared driver — directory
names, not an identifier style the code itself follows), so
`from <package>.Modules.other.Contracts import OtherStore` works without any extra path wiring.
Lint (`ruff check`) does not enable the `pep8-naming` (`N`) rule set, so these required capitalized
directory names don't trip a naming lint on every file inside them. `mocks/` stays lowercase —
nothing in the shared driver reads it by a fixed path, so it's this stack's own, idiomatic choice.

## Kind
`STACK_KIND="tool"`. It has a journey layer: `stack_ui_tests` runs the installed console-script
end-to-end in a fresh temp directory — invoking it as a subprocess with real arguments, and
asserting on its exit code, stdout/stderr and any files it wrote. That's this stack's "UI test":
there's no screen, but there is a user-facing surface (the CLI) worth testing as a whole, the same
way XCUITest exercises iOS's screens as a whole.

## Human setup
Install `uv` (one command, documented at its own site), then paste `setup.md`'s few-line
`pyproject.toml` template, filling in the package name — the whole manual step, a world smaller
than Xcode's. (`stack select` itself only makes empty folders and merges `.gitignore`/config
lines — generic across every stack — so it can't write `pyproject.toml`'s content; that part
stays a short setup.md step, same model as iOS's project creation, just far shorter since it's
plain text, not a GUI flow.) `stack check` confirms `uv` is on `PATH`, `pyproject.toml` exists and
its package is importable, and `uv run python --version` reports 3.11+.

## Adoption support
**Left for later.** No `detect.py`/`inventory.py` in this PR — there's no existing Python app to
adopt yet, and building detection against an app that doesn't exist risks guessing wrong about
what a real one looks like. Add them in a follow-up once pipeline v2 (or another real app) exists
to adopt, or once `/adopt` needs to target a Python project.

## Decisions log
- 2026-11-03: Python 3.11+ floor, `uv` for env/packaging, `hatchling` build backend, adoption
  support deferred — agreed with the user (AskUserQuestion, all four recommended options chosen).
- 2026-11-03: contracts as a real `ast`-based parser rather than a line scanner, since Python's
  `ast` module makes that the easier and more robust choice, unlike Swift, where the pipeline has
  no built-in parser to call.
- 2026-11-03: `mypy --strict` runs inside the build gate, not lint, since a type error is closer in
  kind to a compiler error than a style violation.
- 2026-11-03: discovered `workflow/gates.sh` and `workflow/public_api.py` hardcode the folder
  names `Modules/` and `Contracts/` (capitalized) under `APP_SOURCE_DIR` — not a per-stack
  choice. Keeping those literal names as subpackages, and leaving `pep8-naming` (`N`) out of the
  ruff rule set so it doesn't flag the required capitalization.

---

## Build checklist
(`/new-stack` reads these to know where to resume)

- [x] Design discussed and approved by the human
- [x] `stack new` scaffold exists (`stack.sh`, this file)
- [x] Fixture and `cases.json` written; `ios-pipeline stack test python_cli --static` passes
- [x] `gates.sh`, `contract.py`, `coverage.py`, `check.py`, `setup.md` written; `ios-pipeline stack test python_cli` passes every case
- [x] `rules.md` written and reviewed by the human
- [x] Added to `stacks/README.md` as `experimental`; pipeline unit tests pass; PR opened
