# iOS Agent Pipeline

A Claude Code plugin that builds an app in six sequential stages.
Each module is a folder in the app's source (no separate packages). Stages:
discuss → outline → (setup) → skeleton → UI prototype → modules → full-app verification.
Everything language- or platform-specific lives in a **stack** (`stacks/<name>/`); the app's stack
is chosen during `/discuss`. **iOS** (SwiftUI, Swift 6) is the only stack so far.
One orchestrator session drives specialized subagents, one at a time, with
automated gates, human checkpoints, and automatic pausing near your plan's usage limit.

Install the pipeline **once**. Each app lives in its own folder and git repo anywhere
on your Mac; the pipeline works on whichever app you open. Every app always uses the
installed version, so updating the pipeline updates all of them.

## Requirements

- **Claude Code**, signed in with your Claude Pro (or Max) subscription
- **git** and **python3**
- What the app's stack needs (`ios-pipeline stacks` lists it). For **iOS**: macOS with **Xcode 26** or
  later (Swift 6 toolchain, iOS simulators installed; it also provides git and python3) and
  **SwiftLint** (`brew install swiftlint`).

Before running anything long:
- Make sure no `ANTHROPIC_API_KEY` environment variable is set (`echo $ANTHROPIC_API_KEY`
  should print nothing), or Claude Code bills that key instead of your plan.
- Leave **extra usage** off in your Claude settings, so hitting a limit pauses instead of charging.

## Install the pipeline (once)

1. **Clone it** to a path without spaces:
   ```sh
   git clone https://github.com/NyckJohnson/ios-agent-pipeline ~/Developer/ios-agent-pipeline
   ```
2. **Put the `ios-pipeline` command on your PATH**:
   ```sh
   ln -s ~/Developer/ios-agent-pipeline/bin/ios-pipeline /usr/local/bin/ios-pipeline
   ```
   (Or add `~/Developer/ios-agent-pipeline/bin` to `PATH` in `~/.zshrc`.)
   Check with `ios-pipeline home`.

To update later: `git -C ~/Developer/ios-agent-pipeline pull`. Apps pick it up in their
next session. If you move the pipeline folder, run `ios-pipeline init <app>` in each app
to relink it.

## Start a new app

1. **Create the app folder**:
   ```sh
   ios-pipeline init ~/Developer/Tally
   ```
   This creates the folder and its git repo with `.pipeline/config.sh`, `.pipeline/status.json`,
   `docs/api/`, a `.gitignore`, a `CLAUDE.md` that imports the pipeline's orchestrator
   instructions, and `.claude/settings.json` (status line, permissions). It is safe to rerun:
   it never overwrites the app's own files. Commit everything.
2. **Open the app**: `ios-pipeline open ~/Developer/Tally` (or `ios-pipeline open` from inside it).
   This starts Claude Code in the app folder with the pipeline loaded as a plugin; extra arguments
   go to `claude` (e.g. `ios-pipeline open ~/Developer/Tally --continue`).
   - Accept the workspace trust prompt; hooks only run in a trusted folder.
   - Approve the import of the pipeline's `orchestrator.md` when Claude Code asks: it lives outside
     the app folder.
3. **Check the plumbing** (one-time, about two minutes):
   - Send any short message. The status line should show `5h N% · 7d N%`, and
     `.pipeline/usage.json` should appear. If it shows `usage n/a`, your Claude Code
     version isn't sending rate limits; the pipeline still works but can only stop
     at the hard limit.
   - Run `/hooks` and confirm the pipeline's SessionStart and PreToolUse hooks are listed.
4. **Begin**: `/discuss <your app idea>`. The discussion includes choosing the stack.
   After the outline is approved, `/setup` walks you through the stack's manual steps (for iOS:
   creating the Xcode project, its build settings, and filling in `.pipeline/config.sh`) and checks
   them with `ios-pipeline stack check` before `/skeleton`.

Always open apps with `ios-pipeline open`. A plain `claude` in the app folder starts without the
pipeline's commands, agents and hooks.

Apps set up before stacks existed keep working: an app config without a `STACK` line but with
the Xcode settings counts as iOS. Rerun `ios-pipeline init <app>` once to update its permissions.

## Adopt an existing app

An app built without the pipeline (by hand or with other tools) can be brought under it with `/adopt`.
Its code is rebuilt module by module behind journey tests until nothing legacy is left; then it is an
ordinary pipeline app and new work goes through `/feature`. Your trunk stays untouched until the end:
the adoption runs on `adopt/main`.

1. `ios-pipeline init <the app's repo>` (it works on an existing repo and keeps your `.gitignore`,
   `CLAUDE.md` and Claude settings), commit, then `ios-pipeline open <the app's repo>`.
2. `/adopt`. It detects the project (`ios-pipeline stack detect`), says what blocks an adoption
   (for iOS: CocoaPods, Carthage, Objective-C, submodules) and what setup must fix, then discusses the
   app with you and queues the features you plan.
3. It surveys the code, proposes modules and writes a memo describing the app as it behaves today, for
   you to approve; walks you through the setup (synchronized folders, test targets); writes journey
   tests against the current app and fixes the bugs they find; then adopts every module and switches the
   project to Swift 6.

`docs/adopt.md` has the design: what changes per stage, how legacy code and old tests are handled,
and UIKit apps (screens stay UIKit, with tested view models).

## Commands

Plugin commands are namespaced: if `/discuss` isn't recognised, use `/ios-pipeline:discuss`, and so on.

| Command | Stage | What happens | Ends with |
| --- | --- | --- | --- |
| `/discuss <idea>` | 1 | Conversation about purpose, stack, journeys, constraints | Notes in `docs/discussion-notes.md`; stack selected |
| `/outline` | 2 | Writes `docs/outline.md`, checks readiness | **You approve** → tag `outline-approved` |
| `/setup` | (2→3) | Walks you through the stack's manual project steps; `stack check` must pass | tag `setup` |
| `/skeleton` | 3 | Module folders, models, protocols, stubs, mocks | Gates pass → tag `skeleton` |
| `/prototype` | 4 | Real screens on mocks; you try it on a device | **You approve the flow** → tag `ui-approved` |
| `/build` | 5 | Modules one at a time: tests → code → gates → review → coverage triage → merge | Tag per module |
| `/verify` | 6 | One XCUITest per journey, whole-app review, your device test and feedback | **You accept** → tag `app-accepted`; offers deferred features |
| `/adopt` | 1–6 | Brings an existing app under the pipeline on `adopt/main`, module by module | **You accept** → merged, tag `adopted` |
| `/feature [idea \| file]` | after 6 | Queues ideas; builds the next one through stages 1–6 on its own branch | **You accept** → merged, tag `feature/<slug>/accepted` |
| `/pipeline-resume` | any | Picks up after a pause or in a fresh session (named so it doesn't clash with Claude Code's own `/resume`) | |
| `/pipeline-status` | any | Progress and plan usage | |

It's fine to `/clear` or open a new session between stages: run `/pipeline-resume` and
the orchestrator rebuilds its picture from the files.

## Adding features after acceptance

Once the app is accepted, new work goes through `/feature`. Ideas wait in a backlog (in
`.pipeline/status.json`, each with a brief in `docs/features/<slug>.md`) and are built one at a time.

- **Queue one idea**: `/feature Streak reminders: notify at 8 pm`, or in a terminal
  `ios-pipeline feature add "Streak reminders: notify at 8 pm"`.
- **Queue a file of ideas**: `/feature ~/Desktop/ideas.md`, or `ios-pipeline feature import <file>`
  (`--dry-run` to preview). One `## Title` section per feature, or one top-level list item per feature;
  `ios-pipeline template backlog` prints an example. Importing again skips ideas already queued.
- **Manage the backlog**: `ios-pipeline feature list | move <slug> <position> | drop <slug>`.
- **Build the next one**: `/feature` with no argument.

Ideas can be queued at any time; building starts only after `app-accepted`. Ideas put off during
`/discuss` are kept in the memo's `Later features` (and `Out of scope`) sections. When you accept
the first version, `/verify` asks you to test on a device, sorts your feedback into fixes now and
features for later, then offers those deferred ideas for the backlog
(`ios-pipeline feature import docs/outline.md --section "Later features"`). Each feature runs on
`feature/<slug>/main` (its modules on `feature/<slug>/module/<Name>`) and merges to `main` when you
accept it, so an abandoned feature never touches `main`. The memo marks what it changes with
`Changes (<slug>):` and `Contract changes (<slug>):` lines in the affected modules; approving the memo
approves those contract changes, and only the units holding changed files are rebuilt. Every journey's
UI test runs again before you accept.

Apps set up before this version: rerun `ios-pipeline init <app>` once, so the app's permissions
include `ios-pipeline feature`.

The `ios-pipeline` command also wraps the scripts, for use in a terminal or by the orchestrator:
`ios-pipeline gates <Module> [--fast]`, `ios-pipeline gates --failed`, `ios-pipeline gates --after-merge <branch>`, `ios-pipeline status summary`, `ios-pipeline api <Module> --check`,
`ios-pipeline template outline`, `ios-pipeline status ref base`, `ios-pipeline stacks`,
`ios-pipeline stack check|setup|rules <agent> [--part <part>]`, `ios-pipeline part list|add <name> <stack>|check` (apps with several parts; see `docs/stacks.md`), `ios-pipeline stack detect [--apply <stack>]` (for adopting an existing app; see `docs/adopt.md`). Run `ios-pipeline help` for the list.

## What's where

The pipeline (installed once):

```
.claude-plugin/plugin.json    Plugin manifest
.claude/commands/new-stack.md Adds a new stack (stacks/README.md "Adding a stack"); pipeline repo only,
                              not part of the plugin, refuses inside an app
commands/                     One command per stage
agents/                       skeleton-builder, screen-builder, test-writer, code-writer,
                              reviewer, coverage-analyst, ui-test-writer, surveyor,
                              legacy-test-scanner
hooks/hooks.json              usage guard, merge guard, test protection, session start
bin/ios-pipeline              init, open, and wrappers for the scripts
orchestrator.md               Orchestrator rules (imported by each app's CLAUDE.md)
stacks/<stack>/               Everything stack-specific: gate steps, contract scanner, coverage
                              reader, setup guide and check, agent rules, lint configs, defaults
                              (stacks/README.md describes a stack folder)
stacks/ios/                   iOS: xcodebuild in Swift 6 with warnings as errors, Swift Testing,
                              XCUITest, SwiftLint, swift-format
stacks/_template/             DESIGN.md checklist and cases.json shape for a new stack (data only;
                              ios-pipeline stack new scaffolds from it; every code file is authored
                              fresh for the new language, never copied)
workflow/defaults.sh          Defaults for every app: thresholds, review mode, usage pauses
workflow/gates.sh             The gate driver: which gates run, --fast, --failed, pass recording; calls the stack
workflow/merge_check.py       Whether the gate run after a module merge can be skipped (gates --after-merge)
workflow/stack_support.py     ios-pipeline stacks / stack: select, new, rules, setup, check, detect, inventory
workflow/stack_test.py        ios-pipeline stack test: a stack's gates against its fixture, or --static
                              (its shape only, no toolchain) for a stack still being built
workflow/status.py            Reads and changes the app's .pipeline/status.json (incl. the feature backlog)
workflow/features.py          Backlog file parsing, slugs, the memo's per-feature change lines
workflow/public_api.py        Generates docs/api/<Module>.md from the module's Contracts/ folder (stack scanner);
                              any change = contract change
workflow/coverage.py          Lists uncovered lines from the stack's coverage data, honouring exempt markers
workflow/statusline.py        Shows usage and writes the app's .pipeline/usage.json
workflow/init_app.py          Creates or relinks an app folder (ios-pipeline init)
workflow/hooks/               Hook scripts
workflow/templates/           Outline memo and backlog templates (status.py parses both) and new-app files
```

Each app (its own repo):

```
CLAUDE.md                     Imports the pipeline's orchestrator.md; add app notes below the block
.claude/settings.json         Status line, permissions (written by ios-pipeline init)
.pipeline/config.sh           App project, scheme, folders; overrides of workflow/defaults.sh
.pipeline/status.json         Stage, module and work-unit progress
docs/outline.md               The memo for this app
docs/api/                     Generated contract snapshots
docs/features/                One brief per feature idea (created when it is queued)
App/                          The Xcode project (iOS stack; created during /setup)
```

`CLAUDE.md` and `.claude/settings.json` hold the absolute path to the pipeline, so an app
folder is tied to the Mac it was set up on. On another Mac, install the pipeline and run
`ios-pipeline init <app>` there.

## How the safeguards work

- **Usage pause**: the status line saves your 5-hour and weekly usage. The orchestrator
  checks it before every step, and a hook blocks any subagent launch over the thresholds
  in `workflow/defaults.sh` (85% / 95% by default).
- **Contract changes**: `docs/api/<Module>.md` is a snapshot of each module's `Contracts/`
  folder (its protocols and data models). If code changes it, the `api` gate fails and the orchestrator must ask you.
- **Tests stay honest**: test-writer works from the spec without seeing the code;
  a hook stops code-writer from editing tests.
- **No unverified merges**: a hook blocks `git merge` of a branch whose head hasn't
  passed a full gate run (`gates <Module>`, `gates --all` or `gates --after-merge`, without `--fast` or
  `--skip-coverage`) on a clean tree. It reads compound commands (`&&`, `;`, pipes, redirections).
- **Coverage triage**: every uncovered line must be tested, marked exempt (checked by the
  reviewer), or raised with you. Markers, in the stack's comment syntax (`//` for Swift):
  - `coverage-exempt: <reason>` at the end of a line;
  - `coverage-exempt-begin: <reason>` … `coverage-exempt-end` around a block;
  - `coverage-exempt-file: <reason>` near the top of a **declaration-only** file (protocols, plain
    enums, stored-property structs, constants). Xcode records no coverage for such files; without
    the marker they fail as "files without coverage data", the same as real code that never ran.
    The skeleton-builder adds it to declaration-only contract files.
- **Foreground subagents**: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in the app's
  `.claude/settings.json` makes every subagent finish before the next step, keeping the
  pipeline strictly sequential.
- **Features stay off `main`** until you accept them; the merge guard covers feature merges too.
- **Adopting an app** (`docs/adopt.md`): until Stage 6, legacy code only has to build and pass its
  tests; module code and its tests must be warning-free, and full gate runs add the journey UI tests.
- **Scoped to apps**: every hook does nothing in a folder without `.pipeline/config.sh`.

## Tuning

- Pipeline-wide settings are in `workflow/defaults.sh`, stack settings in `stacks/<stack>/defaults.sh`.
  To change one for a single app, copy its line into that app's `.pipeline/config.sh`.
- `BASE_BRANCH` (default `main`): the app's trunk, for repos whose main branch has another name.
- `REVIEW_MODE="combined"` (one review pass) or `"split"` (one per category).
- `MAX_ATTEMPTS` (3) per work unit, and `MAX_FILES_PER_UNIT` (4): the outline splits larger
  modules into units with `|` on the memo's `Files:` line.
- Each agent's `model:` line in `agents/*.md`. The test, review, coverage and
  UI-test agents default to `sonnet` to stretch your plan; the builders inherit your main model.
- `COVERAGE_EXCLUDE_REGEX` decides which files skip coverage (SwiftUI views and mocks by default).
  To skip more in one app, set `COVERAGE_EXCLUDE_EXTRA` (added to the default) instead of replacing it.
- Config values may be `KEY="value"` or `KEY='value'`; the scripts don't expand `$VARIABLES` and
  print a warning for any line bash would read differently.
- iOS: `gates` retries a test run once when the simulator reports it is busy.
- Lint rules (iOS): `stacks/ios/lint/` for every app; a `.swiftlint.yml` or `.swift-format` at an app's
  root replaces the default for that app.

## Known limits (read before your first app)

- The scripts are covered by unit tests (`python3 -m unittest discover -s tests`), but the iOS
  gates themselves need a Mac; real apps still find the occasional rough edge.
- `public_api.py` is a line-based scanner, not a compiler. Unusual formatting can slip
  past it; the reviewer's spec-and-API category is the backstop.
- Modules are folders in one Swift module: the compiler does not enforce boundaries. Agent
  briefs limit what each subagent sees, and the reviewer checks that files use other modules
  only through their `Contracts/` types.
- A normal gates run executes the whole unit test target once (coverage is then filtered per
  module), so it gets slower as the app grows. `gates.sh <Module> --fast` runs only that module's
  test suites (found by `struct/class …Tests` names) and is used while iterating; the final run
  before each merge is always the full one. `gates --failed` reruns only the tests that failed in the
  last run (a fixing aid; it never records a pass). After a merge, `gates --after-merge <branch>` records
  the pass without rerunning when the merge holds exactly the code gated on the branch, and runs
  `--all` otherwise; after a stage's last module the orchestrator runs `--all` once.
- While adopting, `gates <Module>` skips the other modules' unit tests: modules are adopted in build
  order, so nothing adopted depends on the module yet. Its own tests, the legacy tests and the journey
  tests still run, and `gates --all` after the last module runs every test.
- iOS gates run on your Mac only (they need Xcode and simulators).
- `ios-pipeline stack test <stack>` checks a stack's gates give the right verdicts against a small
  fixture app (a clean pass, a failing test, a warning, a lint error, a contract change, an uncovered
  line, …). The iOS fixture's Xcode project is made once by hand: `stacks/ios/fixture/SETUP.md`.
- Only listed stacks can be built; the orchestrator won't improvise tooling for others.
  Adding stacks is on the roadmap (`ROADMAP.md`).
- Apps always use the installed pipeline. Restoring an old tag in an app restores its memo,
  status and code, but not the pipeline version that built it.
