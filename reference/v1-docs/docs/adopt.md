# Adopting an existing app (`/adopt`)

Design for roadmap item 1: bring an app built outside the pipeline under it. Agreed with the user on
2026-10-23/24. Status: in progress (built in several PRs, listed at the end).

## Goal

An adopted app ends up indistinguishable from a pipeline-built one: every file in modules with
contracts, tests written from a spec, all gates passing in Swift 6 mode, and new work through
`/feature`. The motivation is the pipeline's quality control, so **every module is adopted**; nothing
stays legacy.

`/adopt` mirrors the six stages, adapted to an app that already exists.

| Stage | `/adopt` | Ends with |
| --- | --- | --- |
| 1. Detect + discuss | Detect the project, report setup issues with fixes, flag unsupported dependencies; discuss the app; queue planned features | Notes, `.pipeline/config.sh` |
| 2. Survey + memo | Scripted inventory, read-only surveyor passes, full memo of current behavior | ✋ `outline-approved` |
| (setup) | Synchronized folders, test targets, build settings; `stack check --adopt` | `setup` |
| 3. Baseline | `-uiTesting`, identifiers, journey UI tests, fix bugs found, old tests green, device check | ✋ `baseline` |
| 4. Scaffold | Rename clashing legacy types to `Legacy…`; write contracts and mocks | `scaffold` |
| 5. Adopt modules | Every module, in build order: the Stage 5 loop plus legacy-test scan and a repoint-callers unit | `module/<Name>` |
| 6. Verify | Legacy-empty check, Swift 6 switch, journeys, review, device test | ✋ `adopted` |

Checkpoint and module tags carry the `adopt/` prefix during the adoption (`adopt/baseline`,
`adopt/module/Core`); the final tag is `adopted` on the trunk.

## Stack-neutral

The process (stages, checkpoints, branches, switch-over units, the legacy check) is the same for every
stack; the generic instructions speak of a **clean-state launch option**, a **composition root**, a
**final switch** to full strictness, and each screen's **UI technology**. The stack defines those terms
and supplies detection, inventory, the adopt-mode gates and setup check, the setup steps and the agents'
rules (`stacks/README.md`, "Adoption"). iOS details below (Swift 5/6, UIKit, `-uiTesting`,
`AppDependencies`, Xcode) are the iOS stack's answers.

## Git

- The app must be the root of its own repo; a subfolder of a larger repo (monorepo) is not supported.
- `BASE_BRANCH` (default `main`) names the trunk, so `master` or `develop` work everywhere, not only
  in adoptions.
- `ios-pipeline status adopt start` runs on a clean trunk. All adoption work happens on `adopt/main`
  (modules on `adopt/module/<Name>`), like a feature, so the trunk stays shippable and the human can keep
  committing to it. `status adopt finish` (after verify) marks the app accepted; the orchestrator
  then merges `adopt/main` into the trunk (merge guard applies) and tags `adopted`.
  `status adopt abandon` leaves the trunk untouched and carries queued features over.
- Detection reports: git submodules (unsupported, like CocoaPods), existing branches or tags that
  clash with pipeline names (`module/*`, `feature/*`, `adopt/*`), and git hooks that will run on
  every pipeline commit.
- The pipeline never pushes; the human pushes when they want.

## Legacy code

- Legacy code **stays where it is** until its module is adopted. `Modules/` is added inside the app's
  source folder. Legacy is defined by exclusion: everything in the source folder outside `Modules/`
  and the app-shell allowlist. (A `LEGACY_PATHS` override exists only if exclusion isn't enough.)
- Moving files without editing `.pbxproj` needs synchronized folders, so converting groups to folders
  is a required setup step.
- The **app shell** (the `@main` entry point, `AppDependencies`, assets, `Info.plist`, entitlements) is
  an explicit allowlist in the memo; it never becomes a module.

## UIKit

Apps adopted with UIKit screens **keep them in UIKit** (decided 2026-10-24). When a screen's module is
adopted, its logic moves into a tested view model and the view controller becomes a thin view in
`Modules/<M>/Views/` (excluded from coverage like SwiftUI views; the journey tests cover it).
Storyboards and xibs move with their module. The memo records UIKit or SwiftUI per screen. Agents get
UIKit rules (no logic in controllers, outlets not force-unwrapped, UI on the main actor). Converting a
screen to SwiftUI later is an ordinary `/feature`.

## Stage 1: Detect + discuss

1. `ios-pipeline init <existing repo>` (works on a repo; merges into existing `.gitignore`,
   `CLAUDE.md` and `.claude/settings.json`), commit, `ios-pipeline open`, `/adopt`.
2. `status adopt start`, then `git switch -c adopt/main`.
3. Stack detection (`stacks/<stack>/detect.py`): finds the project, schemes, targets, Swift version and
   default branch, proposes config values; the human confirms. `stack select`.
4. Detection report: every setup problem with a fix plan (fixes the pipeline can make itself are
   applied during setup; Xcode-only steps get exact instructions). **Blocking**: unsupported
   dependencies (`Podfile`, `Cartfile`, a workspace with extra projects, submodules); the pipeline needs
   an upgrade before it can adopt that app.
5. Conversation, as in `/discuss` but about the existing app: purpose, users, journeys as they work
   today, constraints, fragile areas. Planned features go straight into the backlog (`feature add`).
6. Output: `docs/discussion-notes.md` and the detection report.

## Stage 2: Survey + memo

1. **Inventory (scripted):** files, top-level types, which types each file references (a rough
   dependency graph). Cheap; sizes the surveyor passes.
2. **Surveyor passes** (read-only subagent, sonnet, bounded file list per pass): screens and
   navigation; data models and persistence; networking and services; one pass per candidate module
   (behavior, edge cases, error handling); existing tests mapped to areas.
3. **Memo:** the full template, plus
   - **spec = current behavior** (adoption is a pure refactor; the journey tests stay green);
   - **contracts redesigned** to the pipeline's standards (protocols, `Sendable`, no leaks) while
     keeping that behavior;
   - per module: `Legacy files:` (a legacy file may be **split** across modules; the memo says which
     part goes where), `Legacy tests:`, `Callers to repoint:`;
   - `## Legacy code` (all legacy paths and the app-shell allowlist) and `## Known issues`.
4. The human approves → `outline-approved`.

## Setup (adopt variant)

Project-level changes only; code waits for Stage 3.

1. Convert groups to synchronized folders (required; exact steps per group).
2. Add missing unit and UI test targets, or map existing ones in config.
3. Build settings: a Swift 5 target **stays in Swift 5 mode** with `SWIFT_STRICT_CONCURRENCY=complete`
   but without warnings-as-errors. Gates fail on any warning in `Modules/` (filtered by path from the
   build results), so adopted code is Swift-6-clean from the start. The target switches to Swift 6
   mode in Stage 6.
4. Lint and format run only on `Modules/` and the new tests.
5. `stack check --adopt`: the normal checks minus the Swift 6 requirement, nested-repo check over the
   whole tree, a clean build. → `setup`.

### How the gates do it

While the adoption is in stages 1-5 (`ADOPT_MODE=1` for the gate scripts, `ADOPTING` for the setup
check):
- the iOS build keeps the project's language mode, adds `SWIFT_STRICT_CONCURRENCY=complete` and drops
  warnings-as-errors; `stacks/ios/owned_warnings.py` then fails the gate on any warning in
  `Modules/` or a module's test folder (owned files are touched before each build so incremental
  builds always recompile them);
- the Swift 6 setup gate is skipped, and `stack check` accepts a Swift 5 project;
- full runs (`gates <Module>`, `gates --all`) also run the UI journey tests;
- `gates <Module>` and `--coverage-report` skip the other modules' unit tests (`SCOPE_MODULE`): modules
  are adopted in build order, so nothing adopted depends on the module yet, and only its own tests, the
  legacy tests and the journeys can change. `gates --all` runs every test; the orchestrator runs it after
  the last module;
- lint, api and coverage already look only at module folders, so legacy code is outside them.

From Stage 6 on, the gates are the normal ones, so the Swift 6 switch is checked like any app.

## Stage 3: Baseline

The regression net comes before any new code.

1. A subagent adds `-uiTesting` (clean in-memory state) to the app's persistence setup: the first,
   small, reviewed change to legacy code.
2. Accessibility identifiers may be added to legacy views (identifiers only) so UI tests can find
   elements.
3. ui-test-writer writes one XCUITest per memo journey against the current app.
4. A journey test that exposes an existing bug: the bug is **fixed now** (subagent, gated); the memo's
   spec is updated to the correct behavior.
5. Old tests must pass; failing or flaky ones go to the human (fix, disable and list in the memo, or
   drop).
6. `gates --all` (build with filtered warnings, old tests, journey tests) records the baseline.
7. The human runs the app on a device and confirms the journeys match the memo → checkpoint `baseline`.

## Stage 4: Scaffold

1. **Rename clashes:** modules share one Swift module with legacy code, so a legacy type whose name a
   redesigned contract uses (the memo's `Renames:`) is renamed with a `Legacy` prefix (skeleton-builder,
   `STEP: rename`; mechanical, gated on build, old tests and journey tests, committed on its own). These
   types disappear as their modules are adopted.
2. skeleton-builder (`STEP: scaffold`) writes each module's `Contracts/` (with `coverage-exempt-file` on
   declaration-only files) and `Mocks/`, and an empty composition root in the app shell. **No stubs**:
   nothing calls the modules yet.
3. Gates scoped to `Modules/`; legacy still builds and its old tests pass; `api` snapshots written.
   → `scaffold`.

## Stage 5: Adopt modules

Every module, in build order (only adopted modules count as dependencies), on `adopt/module/<Name>`.
Its units are those of its `Files:` line plus a final **switch-over unit** (added by
`status init-modules` for every module with a `Legacy files:` line while adopting).

1. **Code units**, as in the normal Stage 5 loop: **test-writer** writes tests from the spec (it never
   sees code, legacy or new); **code-writer** writes the implementation and **may read the module's
   legacy files** for reference, splitting them as the memo says. Legacy code stays in place for now, so
   callers keep working; module code never uses legacy types.
2. **Switch-over unit** (its own attempts):
   1. **Legacy test scan:** legacy-test-scanner compares the module's old tests with the new ones and
      the spec; `missed` cases are written by test-writer from the spec (never copied); `contradicts`
      and `not-in-spec` go to the human.
   2. **code-writer** repoints the legacy callers (`Callers to repoint:`) to the module's `Contracts/`
      and the instance in the **composition root** (`AppDependencies` in the app shell, created in the
      scaffold), replacing legacy singletons, and deletes the replaced legacy code.
   3. **test-writer** deletes the module's old tests and repoints other old tests that used the
      replaced code.
   4. Gates (build, the module's tests, the remaining old tests) and a review that checks only the
      switch-over: callers use the contract and behave the same.
3. The usual end of the loop: coverage triage, a full gate run (with the journey tests and the
   remaining old tests), merge into `adopt/main`, `gates --after-merge` (skipped when the merge holds
   exactly the gated code), API snapshot, tag. After the last module, `gates --all` runs every test.

Features can be queued during the adoption but only start after it finishes: a feature on
half-adopted code would mix two kinds of change.

## Stage 6: Verify

1. **Legacy check (scripted):** nothing in the source folder outside `Modules/` and the app-shell
   allowlist, no `Legacy…` types, no old tests (`ios-pipeline status adopt legacy`; `status adopt finish`
   refuses until it is empty). Anything left goes back to its module.
2. **Swift 6 switch:** the target moves to Swift 6 mode with warnings-as-errors; issues (most likely
   in the app shell) are fixed in a dedicated unit.
3. All journey tests; whole-app review; the human's device test, with feedback sorted into fixes now
   and features for the backlog, as in `/verify`.
4. `status adopt finish` → checkpoints `adopted` and `app-accepted`. The app is now a normal pipeline
   app: adopt mode is off and only the tags remain.

## Build plan

| PR | Contents |
| --- | --- |
| 1 | This design; `BASE_BRANCH`; `status adopt start/finish/abandon`; `adopt/` refs; next-step hints |
| 2 | Detection: `stacks/ios/detect.py` (project, schemes, Swift version, branch, unsupported dependencies, git clashes and hooks) |
| 3 | Gates: legacy by exclusion, warnings filtered by path, journey tests in full runs, adopt-aware `stack check` |
| 4 | `/adopt` command, surveyor and legacy-test scanner agents, adopt and UIKit rules for the other agents, switch-over units, `stack inventory`, `status adopt legacy` (Stage 6 check, required by `adopt finish`), setup-guide sections for the adoption and the Swift 6 switch, orchestrator section, README |
