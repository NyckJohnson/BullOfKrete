---
description: Add features after the app is accepted — queue ideas (one, or a file of them) and build them one at a time
argument-hint: "[idea | path to a backlog file | nothing to continue]"
---

Features extend an accepted app through a shorter run of the six stages, on their own branch.
Follow the **Feature cycle** section of the orchestrator instructions. `ios-pipeline status feature -h`
lists the backlog commands.

## 1. Queue what the human gave you: $ARGUMENTS

- **An existing file path** (e.g. `docs/ideas.md`, `~/Desktop/backlog.md`): run
  `ios-pipeline status feature import <path> --dry-run`, show the human the list, and on their OK run it
  without `--dry-run`. If it finds nothing, show them the expected format (`ios-pipeline template backlog`).
- **An idea in words**: `ios-pipeline status feature add "<Title>: <one-line description>"`.
  Add `--top` only if the human says it comes before what is already queued.
- **Nothing**: skip to step 2.

Commit queued ideas (`docs: queue feature <slug>`) on the current branch.

## 2. Decide what to work on

Run `ios-pipeline status next`.
- **A feature is active**: continue it at its stage (step 3). If `next` says to switch branch, do that first.
- **App not accepted yet**: ideas stay queued; say so and stop.
- **No active feature**: show `ios-pipeline status feature list` and confirm with the human which feature
  goes next (the first queued, unless they pick another or reorder with `feature move`). Then, on a
  clean `main`: `ios-pipeline status feature start [<slug>]`, commit `chore: start feature <slug>`,
  and `git switch -c feature/<slug>/main`.

## 3. Run the feature's stages

Run `ios-pipeline status usage-check` before every step, as always. Every stage below is the stage of
the same number, scoped to the feature; `ios-pipeline status stage <n>` and `status checkpoint <name>`
apply to the active feature. Tag with `git tag $(ios-pipeline status ref tag <name>)`.

1. **Discuss.** Start from the brief (`docs/features/<slug>.md`, "Idea") and the current memo. Settle
   new or changed journeys (with failure paths), screens, affected modules, contract changes, and
   out of scope. Keep notes in the brief's "Discussion notes" and "Agreed scope"; commit as you go.
2. **Outline.** Edit `docs/outline.md` in place (memo template rules apply):
   - New journeys get the next numbers; changed journeys are edited where they are.
   - New modules go at the right place in the build order with their own block.
   - In each **existing** module the feature changes, add `- Changes (<slug>): <files>`, listing every
     file whose behavior or code changes (including implementation files that must follow a contract
     change), and update its behavior spec. New files go in a new unit: append `| <File>.swift` to the
     `Files:` line rather than joining an existing unit, so finished units stay done.
   - A changed contract gets `- Contract changes (<slug>): <what changes>`.
   - Add a decisions-log line for the feature.
   - If the feature came from the memo's `Later features` or `Out of scope` list, remove it there.
   Show the human the memo diff (`git diff main -- docs/outline.md`) and the contract changes, stating that
   approving the memo approves those contract changes. Revise until they approve. Then
   `ios-pipeline status feature plan` (check its output), commit `docs: feature <slug> outline approved`,
   `status checkpoint outline-approved`, tag.
3. **Manual setup** (only if the feature needs project changes only the human can make, such as a new
   capability, permission or target; the stack's guide has a "For a feature" section,
   `ios-pipeline stack setup`, with `--part <part>` in an app with several parts). Walk the human through
   those steps as `/setup` does, then `ios-pipeline stack check`, commit `chore(<slug>): project setup`.
   A feature that adds a part: `ios-pipeline part add` first, then the part's whole setup.
   **Skeleton** (only if the plan says "needed"). Delegate to **skeleton-builder** with
   `MODE: feature <slug>` and the plan's new modules and contract changes. Then
   `ios-pipeline gates --all --skip-coverage`, `ios-pipeline api <Module> --write` for each new or changed
   module, commit `chore(<slug>): skeleton`, `status checkpoint skeleton`, tag.
4. **Prototype** (only if screens are new or changed). As `/prototype`, for those screens only. The real
   services don't do the new things yet (contract stubs), so the human judges these screens in
   previews, which use mocks; say so. On approval: commit, `status checkpoint ui-approved`, tag.
5. **Build.** The **Stage 5 loop**, which already uses the feature's branches and tags. Reopened units
   follow it like new ones; their briefs say `CHANGE: <slug>` (see the orchestrator instructions).
6. **Verify.** As `/verify`, with these differences: **ui-test-writer** writes tests for the new journeys
   and updates those for changed journeys only; `ios-pipeline gates --app-ui-tests` runs **every** journey
   (regression); **reviewer** gets `SCOPE: feature <slug>` (the diff from `main`, plus how it fits the rest).
   When the human accepts: `ios-pipeline status feature accept`, commit, add the feature to the memo's
   "Features" section, commit, `ios-pipeline gates --all` on the feature branch, then `git switch main`,
   `git merge --no-ff feature/<slug>/main`, `git tag feature/<slug>/accepted`.

## Stopping and abandoning

- Stop at the same points as the other stages: PAUSE, a blocked unit, an unlisted contract change
  (checkpoint 3), code that isn't in the spec. At each checkpoint and at the end of a feature, suggest a
  fresh session (`/feature` or `/pipeline-resume` continues).
- After an accepted feature, if the backlog has more, say which is next and ask whether to start it now.
- **Abandon** only when the human says so: commit on the feature branch, `git switch main`,
  `ios-pipeline status feature abandon`, commit. Main is untouched; the branch stays for reference;
  ideas queued on the branch are carried over.
