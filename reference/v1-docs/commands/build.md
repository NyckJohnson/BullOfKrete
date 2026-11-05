---
description: Stage 5 — build modules one at a time, foundational first
argument-hint: "[module name to build only that one]"
---

Run `ios-pipeline status stage 5` (during a feature this sets the feature's stage; branches and tags
come from `ios-pipeline status ref`).

Ask `ios-pipeline status next` which step comes next (or use $ARGUMENTS
as the module if given). Follow the **Stage 5 loop** in the orchestrator instructions exactly,
running `ios-pipeline status usage-check` before every step.
Use `ios-pipeline gates <Name> --fast` while iterating, and `ios-pipeline gates --failed` to rerun only
the tests that failed in the last run; only the full `ios-pipeline gates <Name>` run before the merge
records the pass the merge guard needs. After a merge, `ios-pipeline gates --after-merge <branch>`
replaces `gates --all`; after the last module, run `ios-pipeline gates --all` once.

Keep going module after module until one of these happens, then stop and report:
- All modules are `done` → tell the human to run `/verify` (during a feature or an adoption: continue
  with its stage 6, as `/feature` or `/adopt` describes).
- Usage check says PAUSE → pause (golden rule 8).
- A unit is `blocked`, a protocol change is needed, or coverage triage finds
  code that isn't in the spec → ask the human.

During an adoption, each module's last unit is its switch-over, and briefs carry the `ADOPT:` lines
the orchestrator instructions describe.

Report progress to the human only at module boundaries: a short line per module.
