# Stacks and parts

Design for roadmap item 1: apps made of several parts, each built with its own stack; a self-test for
stacks (`stack test`); and a workflow for adding one (`/new-stack`). Agreed with the user on
2026-10-31. Status: in progress (build plan at the end; PRs 2-4, parts, per-part gates and
`stack test`, are built; PR 5, `/new-stack` and `stacks/_template/`, is built — 2026-11-02:
`stack new`, `stack test --static`, and dropping the `STACK_KIND` gate on journey tests in favor
of whether `gates.sh` defines `stack_ui_tests`. PR 6, the Python CLI stack, is next).

## Goal

- A **stack** (`stacks/<name>/`) holds everything the pipeline knows about one language or toolchain.
  It stays as it is today, plus a few additions (below).
- An **app** is one or more **parts**. Each part has a folder and a stack: for example `client` (ios)
  and `api` (a Python service). Every module belongs to exactly one part, and everything
  stack-specific about a module (gates, coverage, contract scanner, agent rules) comes from its part's
  stack.
- Everything else stays app-wide: the memo, journeys, build order, status, checkpoints, branches, tags,
  the feature cycle, usage pauses and the merge guard.
- Parts that talk to each other do so only through **interfaces**: neutral contract files (such as an
  OpenAPI spec) that both sides are checked against.
- A part's folder is self-contained (its paths are relative to the part folder), so a large part can
  later be split into an app of its own.
- Today's apps are one part with no changes to their files.

## Parts

### Config

Each part has its own settings file, `.pipeline/parts/<part>.sh`:

```sh
STACK="ios"
PART_DIR="client"            # the part's folder, relative to the app folder
APP_PROJECT="App/Tally.xcodeproj"   # the stack's settings, relative to PART_DIR
APP_SOURCE_DIR="App/Tally"
...
```

- The parts are the files in `.pipeline/parts/`; there is no separate list to keep in step.
- Settings load in four layers: `workflow/defaults.sh` → `stacks/<stack>/defaults.sh` →
  `.pipeline/config.sh` (app-wide, e.g. `REVIEW_MODE`) → `.pipeline/parts/<part>.sh`. A per-part
  override goes in the part file.
- **One-part apps** (every app today): `STACK` and the stack settings stay in `.pipeline/config.sh`.
  That counts as one part named `app` with `PART_DIR="."`. Nothing moves until a second part is
  added; `part add` then moves those lines into `.pipeline/parts/app.sh`.
- Part folders must not overlap. A root part (`PART_DIR="."`) is allowed next to others as long as its
  source and test folders don't contain theirs; `part check` reports overlaps.
- Part names are lowercase identifiers (`client`, `api`, `cli`). Module names stay unique across the
  whole app, since snapshots (`docs/api/<Module>.md`) and tags (`module/<Name>`) are app-wide.

### Commands

| Command | What it does |
| --- | --- |
| `ios-pipeline part add <name> <stack> [--dir <folder>]` | Creates the part file from the stack's `config.sh`, merges its `.gitignore` lines, scaffolds its folders under the part folder. Replaces `stack select` for second and later parts (`stack select` keeps working for one-part apps) |
| `ios-pipeline part list` | Parts, their stacks, folders and maturity |
| `ios-pipeline part check` | Overlaps, unknown stacks, missing folders |
| `ios-pipeline stack check|setup|rules ... --part <name>` | The existing commands for one part; `--part` may be left out in a one-part app |

### Memo

- `## Constraints` lists the parts: `- Parts: client (ios), api (python-service)`.
- Each module gets `- Part: <name>` (optional in a one-part app). `status init-modules` stores it, and
  the summary groups modules by part.
- The build order spans parts. A module may depend on a module in another part only through an
  interface (below), never through its `Contracts/` types: languages can't share types.
- Each journey names the part whose UI tests carry it (`- Part: client`), defaulting to the only part
  with UI tests.
- New section `## Interfaces` (below).

### What follows the module's part

| Today (one stack) | With parts |
| --- | --- |
| `gates <Module>` uses the app's stack | Uses the module's part's stack, run from its part folder |
| `gates --all` | Per part: setup gate, build and tests once, then its modules; then interfaces; then journeys |
| `api`, `coverage` | Scanner, glob and comment syntax of the module's stack |
| `stack rules <agent>` | Briefs gain `PART: <name> (<stack>)`; each agent reads its part's rules. The whole-app review in `/verify` gets every part's rules |
| `/setup` and `stack check` | Once per part; `setup` is tagged when every part passes. A feature that adds a part runs `/setup` for that part only |
| Test protection hook (matches `Tests/` today, which is iOS-specific) | Blocks code-writer edits inside any part's `APP_TEST_DIR` or matching a stack's `STACK_TEST_GLOB` |
| Failed test ids (`--failed`) | Kept per part (`.pipeline/results/failed-tests-<part>.txt`); `--failed` reruns each part's own |

The merge guard needs no change: it records a pass per commit, whichever parts ran.

### How the gate driver runs parts

Each stack's `gates.sh` defines functions with the same names (`stack_build_test`, …), so two stacks
can't be sourced into one shell. `workflow/gates.sh` becomes a driver that runs each part's gates in a
subshell (`in_part` in `workflow/gates.sh`) with that part's settings and stack, `cd`'d into the part
folder, and adds up the results. Stack functions get `PART`, `PART_ROOT` and the existing
variables (`ROOT` stays the app folder). For a one-part app at `.` the child does exactly what
`gates.sh` does today.

## Interfaces between parts

*Designed now; built along with the first stack that runs as a service (see build plan).*

An interface is a file in the app's `interfaces/` folder, in a neutral format, written before code
like any contract. Its memo entry:

```markdown
## Interfaces
### TallyAPI
- File: interfaces/tally-api.yaml (openapi-3.1)
- Provider: api / Sync
- Consumers: client / SyncClient
```

- **Interface first.** The file is the source of truth (schema-first, not consumer-driven contracts
  such as Pact): the memo is approved before any code exists, so the contract can't come from consumer
  tests. Pact-style tests remain an option for a stack's consumer check.
- **Approval.** The interface file is a contract: it gets a snapshot (`docs/api/interfaces/<Name>.md`)
  and the `api` gate fails when it changes, under golden rule 5 (`Contract changes (<slug>):` in a
  feature memo pre-approves it, as for module contracts).
- **Each side is checked by its own stack.** A stack with interface support supplies `interface.py`:
  - `FORMATS`: the formats it understands (e.g. `openapi-3.1`, `json-schema`);
  - `check(part_root, config, interface, role, module)` → `[(ok, item, fix)]`, where `role` is
    `provider` or `consumer`. How it checks is up to the stack: a provider might compare the schema its
    server generates with the file, or replay the file's examples against it; a consumer might generate
    its client types from the file into the module's `Contracts/` and check they are current.
  - A new `interface` gate runs the check for each module that provides or consumes an interface, so
    drift fails on whichever side drifted.
- **Mocks.** Consumer tests use mocks built from the interface (the stack decides how), so a consumer
  module can be built before its provider exists. Build order still puts providers first by default.
- Parts that don't talk to each other (say, a CLI tool beside an app) need no interfaces.

## Running parts together

*Designed now; built with the first service stack.*

A journey can cross parts: "sign up" goes through the iOS screens and the backend. A stack whose part
can run as a process (a service) supplies three functions in its `gates.sh`:

| Function | Does |
| --- | --- |
| `stack_run_start` | Starts the part locally on a port the driver passes in (`PART_PORT`), with clean state |
| `stack_run_ready` | Returns 0 once it accepts requests (polled, with a timeout) |
| `stack_run_stop` | Stops it and cleans up |

- Before a part's UI tests run, the driver starts every part its modules reach through interfaces (in
  build order), waits for ready, passes their addresses to the UI part (`PART_URL_<part>`; the stack
  turns that into a launch argument or environment variable), and stops them afterwards, even on
  failure.
- `stack test` gains cases for these (starts, becomes ready, stops cleanly, leaves no process).
- Until this exists, multi-part apps can only have parts that don't call each other, and the
  first-acceptance device test is the check for anything else.

## Stack interface changes

What a stack folder gains (the rest of `stacks/README.md` stays):

| Where | What | Needed |
| --- | --- | --- |
| `stack.sh` | `STACK_MATURITY="experimental"` or `"verified"` | Every stack (ios: `verified`) |
| `stack.sh` | `STACK_TEST_GLOB`: test files, for the test protection hook | Every stack |
| `stack.sh` | `STACK_KIND`: `app`, `service` (can run) or `tool` (informational; whether journeys actually run is decided by defining `stack_ui_tests` in `gates.sh`, not by this value — PR 5) | Every stack |
| `fixture/` and `cases.json` | The stack's self-test (below) | Every stack |
| `interface.py` | Interface formats and checks | Stacks whose parts talk to others |
| `gates.sh` | `stack_run_start/ready/stop` | `service` stacks |

## Stack self-test (`ios-pipeline stack test <name>`)

A stack's gates decide when a module is "done", so a gate that passes everything is the worst bug a
stack can have. `stack test` runs the stack against a small project with known answers.

- `stacks/<name>/fixture/` is a tiny one-part app in that stack: one or two modules with contracts,
  tests and a journey, passing every gate.
- `cases.json` lists cases. Each one applies an overlay (files to add, replace or delete) to a fresh
  copy of the fixture in a temp folder with its own git repo, runs a pipeline command, and states the
  expected verdict and the gate that must report it:

  | Case | Command | Expect |
  | --- | --- | --- |
  | clean | `gates <M>` | pass, and a recorded pass |
  | failing test | `gates <M>` | fail: tests, with the test id in `FAILED_TESTS` |
  | rerun | `gates --failed` after the above | runs only that test |
  | build warning | `gates <M>` | fail: build |
  | lint error | `gates <M>` | fail: lint |
  | contract change | `gates <M>` | fail: api |
  | uncovered line | `gates <M>` | fail: coverage, naming the line |
  | exemption | `gates <M>` | pass (the marker is honored) |
  | fast | `gates <M> --fast` | runs only that module's tests, no pass recorded |
  | setup broken | `stack check` | the check names the item |
  | journey failing | `gates --app-ui-tests` | fail: UI tests (stacks that define `stack_ui_tests`) |
  | interface drift | `gates <M>` | fail: interface (stacks with `interface.py`) |
  | run lifecycle | driver start/ready/stop | ready, then no process left (`service` stacks) |
  | adopt mode | as above with `ADOPT_MODE=1` | legacy warnings ignored, module warnings fail (stacks with `detect.py`) |

- A stack passes only when every case that applies gives its expected verdict. A case whose tools are
  missing is reported as **not run**, never as passed; `stack test` exits non-zero if anything was not
  run, so a stack can't reach `verified` on a machine without its toolchain.
- The iOS fixture is a real Xcode project, made once by hand (`stacks/ios/fixture/SETUP.md`), so its
  `stack test` runs only on a Mac. Its adopt-mode case is left for later: it needs an adoption's setup.
- The fixture is stored in folders (`project/`, `source/`, `tests/`, …) that `cases.json`'s `layout`
  maps into a fresh app, so it holds no `.pipeline/` folder of its own; `stack select` and `config`
  set the app up as a real one would be.
- Separately, the pipeline's own unit tests use a fake stack (`FAKE_STACK` in `tests/helpers.py`, shell
  functions that pass or fail on demand), so the part driver, interfaces and run lifecycle are tested
  on any machine.

### Maturity

- New stacks start `experimental`. One real app built and accepted with it, with a clean `stack test`,
  makes it `verified` (the human flips the line).
- `/discuss` offers verified stacks and mentions experimental ones only when asked or when nothing
  verified fits.

## Adding a stack (`/new-stack <name>`)

Run in the **pipeline repo**, never in an app session: it is a project command
(`.claude/commands/new-stack.md` in the pipeline repo), not part of the plugin, so app sessions don't
see it. It refuses to run in a folder with `.pipeline/config.sh`.

1. **Discuss** what the stack builds and settle each piece: language and version; package and build
   tool; test framework and how to run one module's tests (`--fast`) and single tests (`--failed`);
   coverage tool and its data format; lint and format tools; what a contract is in the language and how
   to read it (a real parser where one is available, rather than a line scanner); how modules map to
   folders; kind (`app` / `service` / `tool`), and, if relevant, UI tests, interface formats and
   running; the human's setup steps; adoption support (optional, usually later). Notes go to
   `stacks/<name>/DESIGN.md`. ✋ The human approves.
2. **Scaffold**: `ios-pipeline stack new <name>` writes a minimal `stack.sh` (`TODO` placeholders)
   and copies in `_template/DESIGN.md`. Nothing else is copied — every other file is authored fresh
   for this language from `stacks/README.md`'s interface spec, the same way `skeleton-builder`
   writes a module's files from the memo rather than copying another module's. `stacks/ios/` is a
   reference for the *shape*, never something to scaffold from: copying and relabeling another
   stack's files risks carrying over assumptions (a simulator, a specific build tool) that don't
   hold for the new one.
3. **Fixture and cases first**: the fixture app and `cases.json`, before the gate scripts, so the
   self-test defines done for the stack, as tests do for a module. `stack test <name> --static`
   checks the shape (required files, manifest filled in, `cases.json`'s required ids, `gates.sh`'s
   required functions) without needing the toolchain, so this step is checkable before step 4 exists.
4. **Write the stack** (gates, scanners, check, setup guide) until `stack test <name>` (the real
   run, against the toolchain) passes every case.
5. **Rules** (`rules.md`, one section per agent plus `## outline`). ✋ The human reviews them: they shape
   every line the agents will write.
6. Add the stack to `stacks/README.md` as `experimental`; run the pipeline's unit tests; commit on a
   branch for a PR.

The steps of building a stack are not run through the app pipeline's stages: they edit the pipeline
itself, which app sessions never do.

## First stack: Python CLI tool

The first stack built with `/new-stack`; its details are settled in that workflow's step 1. Starting
proposal:

- Kind `tool`. A package under `src/<package>/` with modules as subpackages
  (`src/<package>/modules/<module>/`, each with `contracts/`, `mocks/` and implementation); tests in
  `tests/<module>/`; one `pyproject.toml`.
- Contracts: `typing.Protocol` classes, dataclasses and enums in `contracts/`, read with Python's `ast`.
- Gates: pytest with coverage (`coverage json`), `--fast` as `pytest tests/<module>`; ruff for lint and
  format; mypy in strict mode as part of the build gate; shellcheck for shell scripts.
- Journeys: end-to-end tests that run the installed command in a temp folder (the CLI's "UI tests").
- Setup: a Python version and a virtual environment; the tool (`uv` or plain `venv` + pip) is decided in
  step 1.
- It is the stack pipeline v2 is built with (roadmap item 1), which is what makes it `verified`.

## Not covered (yet)

- **Adopting a multi-part app**: `/adopt` stays one-part (detection at the app root). Adopting each part
  in turn is later work.
- **Splitting a part into its own app**: kept possible (self-contained part folders, interfaces as
  files), with no command yet.
- **Several apps sharing an interface** (an interface whose provider is another app): later; it needs a
  way to point at another repo's file.
- **Renaming `ios-pipeline`**: the roadmap says to rename it when a second stack lands. The name is
  still open; it can be done separately, with the old name kept as an alias.

## Build plan

| PR | Contents |
| --- | --- |
| 1 | This design; roadmap updated |
| 2 | Parts: `.pipeline/parts/`, four-layer config, `part add/list/check`, `--part` on `stack` commands, `Part:` lines in the memo and status, one-part compatibility; the fake test stack |
| 3 | Gate driver per part (a subshell per part in `gates.sh`), coverage, `api` and the test protection hook per part, `STACK_TEST_GLOB`/`STACK_KIND`/`STACK_MATURITY`, briefs and commands (`discuss`, `outline`, `setup`, `build`, `verify`, `feature`) |
| 4 | `stack test` with `cases.json`; the iOS fixture and cases (checked on a Mac) |
| 5 | `/new-stack` and `stacks/_template/` (`DESIGN.md`, `cases.json` shape only — no code to copy); `ios-pipeline stack new <name>` and `stack test --static`; journeys gated on `gates.sh` defining `stack_ui_tests` instead of `STACK_KIND` |
| 6 | The Python CLI stack, built with `/new-stack` |
| later | With the first `service` stack: `## Interfaces`, `interface.py` and the `interface` gate, `stack_run_*`, journeys across parts |
