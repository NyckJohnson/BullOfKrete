---
description: Stage 3 — build the compiling skeleton
---

Run `ios-pipeline status usage-check` (stop if PAUSE), then
`ios-pipeline status stage 3`.

In an app with several parts, do this once per part, in build order, with `PART:` in the brief and only
that part's modules. Delegate to the **skeleton-builder** subagent with a brief (format in the orchestrator instructions)
that points it at the whole of `docs/outline.md` and `.pipeline/config.sh` (and the part's
`.pipeline/parts/<part>.sh`).
If it returns `MANUAL STEPS FOR HUMAN`, walk the human through them as `/setup` does, then rerun the gates.

The manual project setup comes first. If `setup` is not among the checkpoints in
`ios-pipeline status summary`, or `ios-pipeline stack check` fails, stop and tell the human to
run `/setup`.

When it returns `done`:
1. Run `ios-pipeline gates --all --skip-coverage`. All other gates must pass.
2. For each module: `ios-pipeline api <Module> --write`, so the
   API snapshots match the draft protocols.
3. Commit `chore: skeleton`, `git tag skeleton`,
   `ios-pipeline status checkpoint skeleton`.
4. Tell the human the skeleton is ready and to run `/prototype`.

On `blocked` or gate failures after 3 attempts, report to the human and stop.
