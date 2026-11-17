---
description: "Add features after the app is accepted — queue ideas (one, or a file of them) and build them one at a time"
argument-hint: "[idea | path to a backlog file | nothing to continue]"
---

# Features

After the app is accepted, new work comes in as features. You queue ideas in the backlog, then build
them one at a time, each through stages 1 to 6 scoped to what it changes. Follow the **Feature
cycle** in the orchestrator instructions; `bull feature --help` lists the commands.

## 1. Queue

Look at `$ARGUMENTS`:

- **A file path**: run `bull feature import <path> --dry-run` and show the human the ideas it
  found. On OK, run it again without `--dry-run`. If nothing found, show the expected format with
  `bull template backlog` and stop.
- **An idea in words**: queue it with `bull feature add "<Title>: <one line>"`. Add `--top` only if
  the human says so.
- **Nothing**: go to step 2.

When you queued something, commit `docs: queue feature <slug>` (or one commit for an import) on the
current branch.

## 2. Decide

Run `bull status next`.

- **An active feature**: continue it at its stage, in step 3. If `next` says to switch branch, switch
  branch first.
- **The app is not accepted yet, or an adoption is active**: the ideas stay queued. Tell the human
  so (a feature can start only after the app is accepted, or after the adoption finishes) and stop.
- **No active feature**: show the queue with `bull feature list` and confirm with the human which
  feature to start: the first queued one, unless the human picks another or reorders with
  `bull feature move <slug> <pos>`. Then, on a clean trunk, run `bull feature start [<slug>]`. It
  commits `chore: start feature <slug>` and switches to `feature/<slug>/main` by itself.

## 3. Stages

Run `bull status usage-check` before every step; on `PAUSE`, follow the orchestrator's rule for a
pause and stop. While a feature is active, `bull status stage` and `bull status checkpoint` apply to
the feature, and every branch and tag comes from `bull status ref`. Tag with
`git tag $(bull status ref tag <name>)`. As everywhere, run each `bull status …` change before its
step's commit, and tag after the commit.

### 3.1 Discuss

1. Run `bull status stage 1`.
2. Discuss the feature with the human, starting from the brief's "Idea" (`docs/features/<slug>.md`)
   and the memo. Agree on: new and changed journeys, with their failure paths; new or changed
   screens; the affected modules; contract changes; interfaces between parts; and what is out of
   scope.
3. Keep notes in the brief's "Discussion notes" and write what you agreed in its "Agreed scope".
   Commit as you go.

### 3.2 Outline

1. Run `bull status stage 2`.
2. Edit the memo in place:
   - New journeys get the next numbers; changed journeys are edited in place.
   - New modules go at the right place in the build order.
   - In each existing module the feature changes, add `- Changes (<slug>): <files>`, naming every
     file whose behavior or code changes (including implementations that must follow a contract
     change), and update its behavior spec.
   - New files of an existing module go in a new unit: append `| <file>` to its `Files:` line, never
     into a finished unit.
   - A changed contract gets `- Contract changes (<slug>): <what>`; the same goes for an
     interface's entry under `## Interfaces`.
   - Add a decisions-log line for the feature.
   - If the feature came from `Later features` or `Out of scope`, remove it from there.
3. Show the human the memo diff, `git diff <trunk> -- docs/outline.md` (the trunk comes from
   `bull status ref trunk`), and list the contract changes. Say that approval approves those
   contract changes. Revise until approved.
4. On approval:
   1. Run `bull feature plan` and check its output: the reopened units, new modules, contract
      changes, and whether a skeleton is needed. It refuses memo problems; fix them and run it again.
   2. Run `bull status checkpoint outline-approved`.
   3. Commit `docs: feature <slug> outline approved`.
   4. Tag with `git tag $(bull status ref tag outline-approved)`.

### 3.3 Setup and skeleton

The feature's later stages need the `setup` and `skeleton` checkpoints, so record each one even
when its step has nothing to do.

1. **Manual setup, only if the feature needs it.** Run `bull stack setup --section "For a feature"`
   (with `--part <name>` in an app with parts) and walk the human through it as `/bull:setup` does.
   Check with `bull stack check` (`--part <name>` for each part). A feature that adds a part runs
   `bull part add <name> <stack>` first, then that part's whole setup. Then run
   `bull status checkpoint setup` and commit `chore(<slug>): project setup`. If no setup is needed,
   run `bull status checkpoint setup` and commit with a note that no setup was needed.
2. **Skeleton, only if `bull feature plan` said `Skeleton needed: yes`.**
   1. Run `bull status stage 3`.
   2. Brief the **skeleton-builder** with `MODE: feature <slug>`, the new modules and the contract
      changes.
   3. Run `bull gates --all --skip-coverage`; on a failure, retry as `/bull:skeleton` does.
   4. Run `bull api <M> --write` for each new or changed module. A contract change listed in the
      memo passes once as pre-approved.
   5. Run `bull status checkpoint skeleton`.
   6. Commit `chore(<slug>): skeleton`.
   7. Tag with `git tag $(bull status ref tag skeleton)`.

   If no skeleton is needed, run `bull status stage 3`, then `bull status checkpoint skeleton`, and
   commit with a note that no skeleton was needed.

### 3.4 Prototype

1. Run `bull status stage 4`.
2. Only if screens are new or changed: run `/bull:prototype`'s steps for those screens. The real
   code doesn't do the new things yet (it has stubs), so the human judges them on mocks; tell them
   so. On approval, run `bull status checkpoint ui-approved`, commit, and tag with
   `git tag $(bull status ref tag ui-approved)`.
3. Otherwise run `bull status checkpoint ui-approved` with a note in the commit message that nothing
   changed on screen, commit, and tag.

### 3.5 Build

Run `bull status stage 5` and the Stage 5 loop, as `/bull:build` does; it already uses the
feature's branches and tags. Briefs for reopened units add `CHANGE: <slug>` and the brief's "Agreed
scope".

### 3.6 Verify

1. Run `bull status stage 6`.
2. Verify as `/bull:verify` does, except:
   - Brief the **journey-test-writer** with `MODE: feature <slug>`: it adds tests for new journeys
     and updates those of changed ones.
   - `bull gates --journeys` still runs every journey.
   - Brief the **reviewer** with `SCOPE: feature <slug>`: the feature's diff from the trunk, in the
     context of the whole app.
3. On acceptance:
   1. Run `bull status checkpoint accepted`.
   2. Run `bull feature accept`.
   3. Add the feature to the memo's "Features" section.
   4. Commit `docs: feature <slug> accepted`.
   5. Run `bull gates --all` on the feature branch. All must pass.
   6. Run `git switch <trunk>`, then `git merge --no-ff feature/<slug>/main`.
   7. Run `git tag feature/<slug>/accepted`.
4. Name the next queued feature (from `bull feature list`) and ask whether to start it now.

## Stopping

Stop at the usual points: usage-check reports `PAUSE`, a blocked unit, an unlisted contract change
(one not in the memo's `Contract changes (<slug>)` lines), or code not in the spec. Ask the human as
the orchestrator's **Asking the human** describes. Suggest a fresh session at each checkpoint and at
the end; there, `/bull:feature` or `/bull:resume` continues. After acceptance, name the next queued
feature and ask whether to start it.

## Abandon

Abandon a feature only when the human says so:

1. Commit any work on the feature branch.
2. Run `git switch <trunk>`.
3. Run `bull feature abandon`.
4. Commit `chore: abandon feature <slug>`.

The trunk is left untouched and the feature branch stays. Ideas queued on the feature branch are
carried over to the trunk's backlog.
