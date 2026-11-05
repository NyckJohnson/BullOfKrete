<!--
This is the discussion record and build checklist for a new stack, created by
`ios-pipeline stack new bash_shell` and filled in by `/new-stack` (stacks/README.md "Adding a stack").
Keep the headings; /new-stack resumes from the checked boxes at the bottom.
-->

# bash_shell stack: design

## Language and tools
- Language and version: **bash 3.2-compatible** bash (not POSIX `sh`: arrays, `[[ ]]`, `local`
  are fine; bash-4+ features — `declare -A`, `mapfile`/`readarray`, `${x,,}`/`${x^^}`, `${x@Q}`,
  `|&`, `;&`, `coproc`, `&>>` — are not). Shebang `#!/usr/bin/env bash`. The built tool runs on a
  stock Mac with nothing installed.
- Package/build tool: none — there is nothing to compile or install. The **build** gate is:
  `bash -n` on every `.sh` file and `bin/*` entrypoint, run with `/bin/bash` (3.2, so 4+-only
  syntax fails here), then `shellcheck -S warning` (errors and warnings only). A shellcheck
  warning is the closest thing bash has to a compiler warning, so it fails the build, not lint
  (same reasoning as `python_cli` putting `mypy` in the build).
- Test framework: `bats-core` (`.bats` files, TAP output).
  - Unit tests run under **bash 3.2**: the gate puts a temp folder holding a `bash` symlink to
    `/bin/bash` (`BASH_COMPAT_BIN`, a default) first on `PATH`, so `bats`'s own `#!/usr/bin/env
    bash` — and therefore every sourced module — runs on 3.2. This run decides pass/fail.
  - Run one module's tests only (`--fast`): `bats tests/<module>/` (3.2 run, no coverage).
  - Run a single failing test by id (`--failed`): id is `<file>::<test name>`, rerun as
    `bats --filter '^<escaped test name>$' <file>`. Ids come from the TAP `not ok N <name>` lines
    mapped back to their file through the `# (in test file <file>, line N)` comment bats prints
    under each failure.
- Coverage tool and data format: **the stack's own xtrace hook** (kcov was the first choice; see
  the decisions log). A second `bats` run under Homebrew bash (5.x) with
  `BASH_ENV=stacks/bash_shell/coverage_trace.bash`: every bash the tests start turns on `set -x`
  with `PS4='+${BASH_SOURCE[0]}:${LINENO}:'` into a trace file (`BASH_XTRACEFD`, bash 4.1+).
  gates.sh reduces the trace to unique `<file>:<line>` pairs of `.sh` files
  (`COVERAGE_DATA`). xtrace only says what ran, so coverage.py decides what *could* run with a
  conservative line scanner: a multi-line command (`\` continuations, open quotes and parens,
  heredocs, trailing `&&`/`||`/`|`) is one unit, covered if any of its lines was traced (bash
  reports most at their first line, a multi-line `$( … )` at its last); keyword-only lines,
  function headers and bare case patterns are not code. A file no traced line came from is
  "no data". This second run only collects coverage; its pass/fail is ignored (the 3.2 run already
  judged the tests). `mocks/` and `Contracts/` are excluded from coverage (`COVERAGE_EXCLUDE_REGEX`):
  mocks are exercised by their consumers, and contract stubs never run by design.
- Lint tool(s): `shellcheck` at full strength (`-S style`, plus the optional checks
  `quote-safe-variables`, `check-unassigned-uppercase`, `avoid-nullary-conditions`,
  `deprecate-which`; final list in `lint/.shellcheckrc`). Default
  config in `stacks/bash_shell/lint/.shellcheckrc`, overridable by the app's own.
- Format tool: `shfmt -d -i 2 -ci -bn` (diff = fail); `SHFMT_GATE="0"` turns it off, like
  `RUFF_FORMAT_GATE`. Flags come from an `.editorconfig` if the app has one.

## Contracts
A contract is a module's `Contracts/<module>.sh`: the module's public functions declared as
**stubs** that fail loudly (`echo "<module>::<fn>: not implemented" >&2; return 70`), each
preceded by a `# usage:` comment line giving its signature, plus `readonly` constants that are
part of the interface (exit codes, enum-like values, record field orders). Example:

```bash
# usage: counter::increment <name> -> stdout: the new count; exit 0, or COUNTER_E_EMPTY_NAME
counter::increment() { echo "counter::increment: not implemented" >&2; return 70; }
readonly COUNTER_E_EMPTY_NAME=2
```

The module's `<module>.sh` sources its contract then redefines every stub; `mocks/<module>.sh`
does the same with canned behaviour, for other modules' tests. Bash has no interface construct, so
"implements the contract" is checked by a test (every contract function is redefined by the real
file), written by the test-writer per the rules.

`contract.py` is a **line scanner** (bash has no parser Python can call, and the contract file's
shape is constrained by the rules): for each `name() {` / `function name {` it emits
`name: <usage text>`; for each `readonly NAME=value` / `declare -r NAME=value` it emits
`NAME=value`. Names starting with `_` are private and skipped. So a changed usage line, a renamed or
removed function, or a changed constant is a contract change.

## Modules
Public functions are named `<module>::<function>` (Google Shell Style Guide); private helpers
`_<module>::<function>`; module-level variables `<MODULE>_*`. Layout (`Modules/` and `Contracts/`
names are fixed by the shared driver):

```
bin/<app>                         # entrypoint: resolves its own dir, sources lib, dispatches
lib/                              # APP_SOURCE_DIR
    Modules/
        <module>/
            Contracts/<module>.sh # stubs + usage lines + readonly constants
            <module>.sh           # implementation (sources its contract, redefines stubs)
            mocks/<module>.sh     # canned implementation for other modules' tests
tests/                            # APP_TEST_DIR
    <module>/<module>.bats
    journey/*.bats                # end-to-end runs of bin/<app>
```

No library file runs anything at source time (only function/constant definitions), so tests can
source it; `set -euo pipefail` lives in `bin/<app>`, not in library files.

## Kind
`STACK_KIND="tool"`. It has a journey layer: `stack_ui_tests` runs `bats tests/journey/`
(under bash 3.2), which invokes `bin/<app>` as a subprocess in a temp folder with real
arguments and asserts on exit code, stdout/stderr and files written.

## Human setup
`brew install bats-core shellcheck shfmt bash` (Homebrew `bash` is only for coverage tracing;
the app itself targets `/bin/bash` 3.2). `stack check` confirms each is on `PATH`, `/bin/bash`
exists, a bash ≥ 4.1 is available for coverage, `bin/<app>` exists and is executable, and
`lib/Modules/` exists. No project file to write — `stack select` scaffolds `bin lib tests`.

## Adoption support
**Left for later**, as for `python_cli`: no existing bash app to adopt yet.

## Decisions log
- 2026-11-04: bash 3.2-compatible target, bats-core, kcov, `module::function` naming — chosen by
  the user (AskUserQuestion; 3.2 over the recommended 5.x, the rest as recommended).
- 2026-11-04: because kcov needs bash 4.1+, unit tests run twice: under `/bin/bash` 3.2 for
  pass/fail (which, with the coverage gate making every line run, also catches bash-4 features),
  then under kcov with Homebrew bash for coverage only.
- 2026-11-04: build gate = `bash -n` (3.2) + `shellcheck -S warning`; lint = full shellcheck +
  shfmt. Contracts are stub functions with `# usage:` lines, read by a line scanner.
- 2026-11-05: **kcov dropped** for a stack-built xtrace tracer — chosen by the user. On this Mac
  (kcov 43, arm64 macOS) kcov's `BASH_XTRACEFD` and DEBUG modes fail at startup ("Failed to
  exchange stderr for pipe", even on a 10-line script; `--bash-parser` pointing at Homebrew bash
  fails the same way), and its one working mode (stderr tracing under `/bin/bash` 3.2) loops
  forever under bats, which reads its own trace back. The tracer (`coverage_trace.bash` +
  coverage.py's command scanner) was checked against a corpus of bash constructs before adoption.
- 2026-11-05: shellcheck checks `.sh` files as bash (`-s bash`; they have no shebang), `.bats`
  files in bats' dialect minus SC2154 (shellcheck doesn't know `BATS_TEST_DIRNAME` and friends),
  entrypoints by shebang. Dotfiles in `bin/` (the scaffold's `.gitkeep`) aren't entrypoints.

---

## Build checklist
(`/new-stack` reads these to know where to resume)

- [x] Design discussed and approved by the human
- [x] `stack new` scaffold exists (`stack.sh`, this file)
- [x] Fixture and `cases.json` written; `ios-pipeline stack test bash_shell --static` passes
- [x] `gates.sh`, `contract.py`, `coverage.py`, `check.py`, `setup.md` written; `ios-pipeline stack test bash_shell` passes every case
- [ ] `rules.md` written and reviewed by the human
- [ ] Added to `stacks/README.md` as `experimental`; pipeline unit tests pass; PR opened
