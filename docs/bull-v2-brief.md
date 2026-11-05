# BullOfKrete (pipeline v2): brief for `/discuss`

Input for Stage 1 of building pipeline v2 with pipeline v1. Agreed with the user on 2026-11-05.
`/discuss` reads this first, settles the open questions with the human, and carries the rest into
`docs/discussion-notes.md` and then the memo.

## What it is

BullOfKrete is the second version of the agent pipeline: a Claude Code plugin that builds software in
staged steps with specialized subagents, automated gates and human checkpoints. It does what v1 does
(discuss → outline → setup → skeleton → prototype → modules → verify, plus features and adoption), with
code written from first principles and with **no iOS-specific focus**: every platform is a stack, and
iOS is just one of them.

- **Name:** BullOfKrete. **Command:** `bull` (replaces `ios-pipeline`).
- **Stack:** the existing Python stack (plus the shell stack, see open questions). v2 is the real app
  that moves the Python stack from `experimental` to `verified`.

## Decisions already made

| Decision | Reason |
| --- | --- |
| New project, started with `/discuss` (not `/adopt`, not changes in place) | Code from first principles; the rename belongs in the spec from day one; `/adopt` would keep current behavior and let code-writer read the old code; editing v1 in place would change the pipeline that is running the build |
| v1 builds v2 in this separate repo; v1 is frozen to bug fixes from memo approval on | Builder and build stay apart; no features to port twice |
| v1's Markdown is copied in as reference material and reviewed, not reused unread | Keep what is still right, drop what is obsolete or redundant |
| All code is written from the spec through the full Stage 5 loop | Tests from the spec, gates, review and coverage triage, as for any app |
| v1's test suite is used as **reference tests** (below), never copied | Regression net without steering the new code |
| `/adopt` is in v2.0 | |
| Building a stack goes through stages and subagents, like an app (below) | A stack's gates decide what "done" means for everything built with it |
| No v1 compatibility in the core | Only three v1 apps exist; they are migrated by hand (`bull-v1-migration.md` in the project) |
| v2 designs its own formats (config, status, memo lines, snapshots) | They are chosen on their own merits, not to match v1 |

## Reference material in this repo

- `reference/v1-docs/`: every Markdown file from v1 (README, orchestrator, workflow guide, roadmap,
  `docs/adopt.md`, `docs/stacks.md`, `stacks/README.md`, stack rules and setup guides, agent and command
  files). `/discuss` and `/outline` read them. Each one is kept, merged, rewritten or dropped, and the
  memo records which.
- `reference/v1-tests/`: v1's `tests/` suite. Only the reference-test scan reads it (below).
- `reference/` is deleted at the end of Stage 6.

## Reference tests

v1's tests are checked against v2's tests without being copied, much like the scan during an adoption.

1. The memo gives each module a `Reference tests:` line naming the v1 test files or cases that cover the
   same behavior. Unmapped v1 tests are listed under `## Unmapped reference tests`, each with a reason.
2. After a module's last unit and before coverage triage, the orchestrator runs **legacy-test-scanner**
   with the spec, the module's new tests and its reference tests. It compares behavior, not names:
   `ios-pipeline status` and `bull status` are the same behavior.
3. Findings: `covered` → nothing; `missed` → test-writer writes the test **from the spec**;
   `contradicts` or `not-in-spec` → the human decides, and the decision goes in the decisions log.
4. test-writer and code-writer never read `reference/`.

Consider making this a v2 feature (useful for any rewrite).

## Requirements

### Stack-neutral core
- Nothing outside `stacks/<name>/` names a language, toolchain or platform. Known v1 leaks to remove:
  the "no `STACK` line means iOS" rule; the test-protection hook matching `Tests/`; Xcode, Swift and
  simulator wording in the commands, the orchestrator and agent files; `App/` in file tables; "XCUITest"
  where "journey/UI test" is meant; the command name.
- Generic terms from v1 stay generic: contracts, mocks, composition root, clean-state launch option,
  final switch to full strictness, UI technology per screen.
- iOS is a stack folder held to the same stack self-test as every other stack.

### Stacks built like apps
v1's design (`docs/stacks.md`) runs `/new-stack` as a project command outside the stages. In v2,
building a stack follows the same staged loop with subagents, gates and checkpoints:

| App build | Stack build |
| --- | --- |
| `/discuss` | Settle language, build, test, `--fast`/`--failed`, coverage, lint, the contract reader, module layout, kind (`app`/`service`/`tool`), interfaces, running, setup and adoption support. ✋ The human approves `DESIGN.md` |
| Skeleton | Scaffold `stacks/<name>/` from `stacks/_template/` |
| Tests first (test-writer) | Fixture app and `cases.json` first: the self-test defines done |
| Code (code-writer), one unit at a time | Gate functions, contract scanner, coverage reader, `check`, setup guide, `detect` (optional) |
| Gates | `bull stack test <name>`: every case that applies gives its verdict; "not run" fails |
| Review | Reviewer, then ✋ the human reviews `rules.md` |
| Accept | Marked `experimental`; `verified` after one real app is accepted |

To settle in `/discuss`: where a stack is built (in the bull repo, never inside an app session), how its
status and checkpoints are tracked, and whether it gets tags and branches like modules.

### Carried over as concepts (formats may change)
- Six stages, four checkpoints, one subagent at a time, only the orchestrator talks to the human and
  edits the memo and status.
- Files are the memory: memo, status file, git. Commit after every step; resume from files.
- Contracts as generated snapshots; any change stops for approval (or is pre-approved by a feature memo).
- Tests written from the spec without seeing code; code-writer cannot edit tests.
- Gates, coverage triage with `coverage-exempt` markers, reviewer categories, 3 attempts per unit,
  work units sized by `MAX_FILES_PER_UNIT`, `partial` returns.
- Merge guard (recorded full gate pass on a clean tree), usage pause (status line, threshold hook).
- Feature backlog and cycle on per-feature branches; `/adopt` on `adopt/main`.
- Parts: an app is one or more parts, each with its own stack; interfaces between parts (designed in
  `docs/stacks.md`).
- Checkpoint tags, per-module tags and branches.

### New in v2
- **Format versions**: a `format` version in the status file and config, and `bull migrate` for
  future v2.x changes.
- **Machine-readable output**: `bull status --json` (and the backlog, usage, tags) so a later GUI is a
  thin reader (roadmap item 3).
- **Install and open**: `bull init`, `bull open`, the plugin namespace `/bull:…`.

### From the roadmap: decide in scope for v2.0 or later
- Time tracking events (item 4): at least leave a place for an event log.
- Settings layers and validation (item 5).
- Provider seam for AI-agnostic runs (item 6): at least keep Claude Code specifics in one place.
- Store readiness as an optional stack hook (item 7).
- Token report (item 8) and automatic orchestrator restarts at module boundaries.
- Quieter iOS test runs (item 2): belongs to the iOS stack, not the core.

## Journeys (draft)

1. Install bull and init a new app.
2. Build a small app end to end (discuss → accept) with a fake or Python stack.
3. Pause on usage and resume in a fresh session.
4. Queue features from a file and build one to acceptance; abandon another.
5. Adopt an existing app.
6. Add a stack through the staged stack workflow and pass `bull stack test`.
7. An app with two parts.
8. A contract change stops the pipeline until approved.
9. An unverified merge is blocked.

## Out of scope

- Reading v1 app files or v1 formats automatically (migration is manual, three apps).
- Changes to v1 beyond bug fixes.
- Adopting a multi-part app, splitting a part into its own app, interfaces shared between apps (as in
  `docs/stacks.md`).

## Open questions for `/discuss`

1. One part (Python, with shellcheck for scripts) or two parts (Python and shell stacks)?
2. Are the existing stacks (Python, shell, iOS) ported as they are, or rebuilt through v2's stack
   workflow? Rebuilding at least one is the stack workflow's first real test.
3. Which roadmap items are in v2.0?
4. Where bull installs, and how it updates.
5. Does the status file stay JSON? One file or several?
6. Plugin name and slash-command namespace.

## Done when

- Every journey's end-to-end test passes; every module passed its gates, review and reference-test scan.
- `reference/` is empty and deleted; the legacy decisions are in the decisions log.
- The three v1 apps are migrated (`bull-v1-migration.md`) and pass `bull gates --all`.
- The Python stack is marked `verified`.
