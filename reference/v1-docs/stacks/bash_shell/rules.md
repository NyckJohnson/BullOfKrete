# bash_shell stack rules

Read with `ios-pipeline stack rules <agent>`: it prints the common section plus the agent's own.

## common
- Language: bash, **3.2-compatible** (macOS's `/bin/bash`). Arrays, `[[ ]]`, `local`, `$(...)`,
  `$((...))` are fine. Not allowed (bash 4+): `declare -A`/`local -A` (associative arrays),
  `mapfile`/`readarray`, `${x,,}`/`${x^^}`, `${x@Q}`, `|&`, `;&`/`;;&`, `coproc`, `&>>`,
  negative array indexes, `declare -n`, `$EPOCHSECONDS`. Unit tests and journeys run under
  `/bin/bash` 3.2, so any of these fails the gates.
- `"${arr[@]}"` on an empty array is an "unbound variable" error under `set -u` in bash 3.2: guard
  with `${arr[@]+"${arr[@]}"}`, or check `${#arr[@]}` first.
- Layout: the entrypoint is `bin/<APP_NAME>` (executable, `#!/usr/bin/env bash`, `set -euo
  pipefail`). Modules are `<APP_SOURCE_DIR>/Modules/<module>/` (literal `Modules` and
  `Contracts`, capitalized: the pipeline's shared convention). Module names are lowercase
  `snake_case`. Every library file ends in `.sh`, has no shebang and no `set -e`/`set -u` of its
  own, and runs nothing when sourced: only function definitions, `readonly` constants, and
  `source` lines.
- Naming: public functions `<module>::<verb>` (`counter::increment`); private helpers
  `_<module>::<verb>`; module-level variables `<MODULE>_<NAME>` in capitals; locals lowercase and
  always declared `local`.
- A module's contract is `Modules/<module>/Contracts/<module>.sh`: one stub per public function,
  each with a `# usage: <module>::<fn> <args> -> <result>` comment directly above it (continue a
  long one on `#   ...` lines), plus `readonly` constants (exit codes, fixed values). Only that
  file is the contract (`ios-pipeline api` reads it); everything else may change freely.
- `<module>.sh` starts by sourcing its own contract
  (`source "$(dirname "${BASH_SOURCE[0]}")/Contracts/<module>.sh"`, with a `# shellcheck
  source=Contracts/<module>.sh` line above), then redefines every stub. Mocks
  (`mocks/<module>.sh`) do the same with canned behaviour.
- A constant in a contract is `readonly`, so a contract must be sourced at most once per shell:
  start any contract that has constants with
  `[[ -n "${<MODULE>_CONTRACT_LOADED:-}" ]] && return 0; <MODULE>_CONTRACT_LOADED=1`.
- A module may source another module's `Contracts/` (or, in tests, `mocks/`) file only, and only
  modules its memo entry lists as dependencies. The entrypoint sources each module's real
  `<module>.sh`.
- Functions return data on stdout, errors on stderr, status as the exit code. No global variables
  as return values (they're lost in `$(...)`).
- Quote every expansion (`"$var"`, `"$(cmd)"`, `"${arr[@]}"`) unless word splitting is the
  point, and then say so in a `# shellcheck disable=SC2086 # <why>` comment.
- Build gate = `bash -n` under 3.2 + `shellcheck -S warning`: a shellcheck warning is a build
  failure. Lint = full shellcheck (style level) + `shfmt` (2-space indent, `-ci -bn`).
- Tests: bats-core. `tests/<module>/<file>.bats` per implementation file; journeys in
  `tests/journey/<command>.bats`.

## outline
- Contracts in the memo are fenced as ```bash, one `# usage:` line per public function, plus any
  `readonly` constants: exactly what `Contracts/<module>.sh` will hold.
- Data models: bash has no records. A model is a documented line format (tab-separated fields in a
  fixed order, stated in the memo, with a `readonly` constant per field index if callers need it)
  or a file format. Name the format in the memo; don't invent nested structures.
- `Files:` lines use `.sh` names, e.g. `counter.sh | mocks/counter.sh`.
- The tool's commands are under "## Commands" (iOS's "User journeys"); each one names the module
  function the entrypoint calls for it.
- Exit codes: 0 success, 1 general failure, 2 usage error; anything else is a `readonly`
  constant in the contract that owns it (sysexits numbers, 64–78, are a good source).
- External commands the tool needs beyond macOS's base system are listed under Constraints
  (`Third-party:`); prefer what macOS ships (BSD `sed`/`awk`/`date`: no GNU-only flags such as
  `sed -i` without a suffix argument, `date -d`, `readlink -f`, `grep -P`).

## skeleton-builder
- `Contracts/<module>.sh` exactly as the memo: each stub body is
  `echo "<module>::<fn>: not implemented" >&2` then `return 70`.
- `<module>.sh`: sources the contract, then redefines each function with the same stub body
  plus ` (skeleton)` in the message, so tests can run against it.
- `mocks/<module>.sh`: sources the contract, defines `MOCK_<MODULE>_*` variables for canned
  return values and call counts, and redefines each function to use them. Note in its header
  that call counts only survive a direct call, not one inside `$(...)`.
- `bin/<APP_NAME>`: sources each module's `<module>.sh` from `$<NAME>_HOME/lib/Modules/...`,
  defines `main` that dispatches on `$1` to the memo's Commands (usage error, exit 2, for
  anything else), and ends with `main "$@"`.
- One placeholder test per implementation file, `tests/<module>/<file>.bats`, with a `setup()`
  that sources the module and one `@test "placeholder" { : }` (bats counts it, so the module
  clears "no tests ran" from the start).
- Contracts and mocks are excluded from coverage (stub bodies never run by design): no
  `coverage-exempt` markers for them.
- Feature mode: a stub for a new requirement says `not implemented (feature <slug>)`.
- If a tool is missing (gates report it), don't fix the environment; list the setup.md steps
  under `MANUAL STEPS FOR HUMAN`.

## test-writer
- `setup()` sources the module under test by a path relative to the test file
  (`source "$BATS_TEST_DIRNAME/../../lib/Modules/<module>/<module>.sh"`, with a `# shellcheck
  source=` line), and the mocks of any dependency *after* it.
- Test names describe behaviour: `@test "increment adds one"`. Names are unique within a file
  (`--failed` reruns a test by its name).
- Call through `run` and assert with `[ ... ]` (single brackets) on `$status`, `$output`,
  `${lines[@]}`. **Never `[[ ]]` as an assertion**: under bash 3.2 a failing `[[ ]]` that isn't
  the test's last line does not fail the test. No bats helper libraries (bats-assert etc.)
  unless the memo adds them.
- `run` merges stderr into `$output`; use `run --separate-stderr` (then `$stderr`) when a test
  checks one stream only.
- Files go in `$BATS_TEST_TMPDIR` — never a fixed path, never the repo's folders. Tests that
  change the current folder `cd` into `$BATS_TEST_TMPDIR`.
- Cover every function in the contract, including its error exits, and test that the real
  implementation replaces each stub (its output never contains `not implemented`).
- `--fast` runs `bats tests/<module>/` alone: no test may depend on another module's tests.

## code-writer
- Implement every stub `Contracts/<module>.sh` declares, in `<module>.sh`, keeping each
  function's arguments, stdout and exit codes exactly as its `# usage:` line says.
- Depend only on other modules' contract functions; never source their `<module>.sh` from a
  library file (the entrypoint does that) and never their `mocks/`.
- Validate arguments at the top of each public function; on bad input write `<module>::<fn>:
  <what's wrong>` to stderr and return the contract's error code.
- Check every command that can fail (`cmd || return`, or `if ! cmd; then ...`): library code
  can't rely on `set -e`, which is off inside `if`/`||`/`$(...)` contexts and in callers' tests.
- `local` every variable, and assign command output on its own line (`local x; x="$(cmd)"`) so
  the command's status isn't masked.
- Temp files from `mktemp`, removed with a `trap` in the entrypoint (or the function's caller),
  never fixed names in `/tmp`.
- No `eval`, no building commands as strings; arrays for argument lists. Secrets from
  environment variables or a file outside the repo; never echoed or logged.
- BSD tools only (macOS's base system): no GNU-only flags (see `## outline`).

## reviewer
- Bash 3.2 compatibility: any feature `## common` lists as bash 4+ is a blocker even if a test
  happens not to reach it.
- Error handling: an unchecked command whose failure would leave wrong output or state; an error
  message on stdout instead of stderr; an exit code not in the contract.
- Safety: unquoted expansions of user input or paths, `eval`, `rm -rf "$var/"` with a possibly
  empty `$var`, temp files without cleanup, secrets in output.
- Contract design: a `# usage:` line that doesn't say what's printed and which codes are
  returned; a public function that only makes sense for one caller.
- A library file that runs code when sourced, or sets shell options, is a blocker.
- Style nits shellcheck or shfmt would catch are not findings.

## ui-test-writer
- One file per command, `tests/journey/<command>.bats`, test names after the command's
  behaviour: `@test "count prints the new count"`.
- Run the real entrypoint as a subprocess: `run "$BATS_TEST_DIRNAME/../../bin/<APP_NAME>" <args>`
  after `cd "$BATS_TEST_TMPDIR"` — never source it or call module functions directly.
- Assert on exit code, stdout/stderr and files written, with `[ ... ]` (as in `## test-writer`);
  don't assert on incidental wording.
- Set up any environment variables or input files inside the test; never depend on the
  developer's machine (`$HOME` contents, installed extras). Override `HOME` to
  `$BATS_TEST_TMPDIR` if the tool reads or writes there.
- Journeys run under `/bin/bash` 3.2 too.

## coverage-analyst
- Coverage comes from bash's own xtrace (the stack's `coverage_trace.bash`). A multi-line command
  (`\` continuations, open quotes, `$( … )`, heredocs, trailing `&&`/`||`/`|`) is one unit,
  reported at its first line; lines that are only keywords (`then`, `fi`, `done`, `}`, `;;`), function
  headers, and bare case patterns are not code.
- Exemption markers are bash comments: `# coverage-exempt: <reason>` at the end of a line, or
  `# coverage-exempt-begin: <reason>` … `# coverage-exempt-end` around a block.
- `Contracts/` and `mocks/` are excluded from coverage already. A file under "Files without
  coverage data" was never sourced by any test: classify it `missed`.
- Typical infeasible code: a guard for a missing external command that is always installed in
  the test environment, a branch for another OS (`uname` checks).
