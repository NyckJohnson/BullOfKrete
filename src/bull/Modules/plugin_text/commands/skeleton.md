---
description: "Stage 3 — build the compiling skeleton"
---

# Stage 3: Skeleton

The skeleton is the whole app in outline: every module's folder, contracts, mocks and stub files,
building cleanly and passing its gates, with no real behavior yet. The skeleton-builder agent
writes it; you brief it, run the gates and record the result.

1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a pause
   and stop.
2. Run `bull status stage 3`. If it is refused because the `setup` checkpoint is missing, tell the
   human to run `/bull:setup` first, and stop.
3. If the app has parts, run steps 4 to 6 once per part, in build order. Each brief then carries a
   `PART: <name> (<stack>)` line and lists only that part's modules.
4. Brief the **skeleton-builder** in the orchestrator's brief shape:
   - `TASK:` build the compiling skeleton (of this part, with parts).
   - `READ ONLY THESE:` the whole memo, `docs/outline.md`; the app's settings,
     `.bull/config.toml`; and, with parts, the part's settings, `.bull/parts/<part>.toml`.
   - `ACCEPTANCE:` every module in the memo (of this part) has its folder, contracts, mocks and
     stubs, and the gates pass.
5. If the report has a `MANUAL STEPS FOR HUMAN` block, walk the human through those steps the way
   `/bull:setup` does: one step at a time, waiting for "done" after each. Then rerun the gates.
6. When the skeleton-builder returns `done`, run `bull gates --all --skip-coverage`. All gates must
   pass. On a failure, give the skeleton-builder the failing output as a `PREVIOUS FAILURE` and try
   again; each try counts as one attempt.
7. If the skeleton-builder returns `blocked`, or the gates still fail after `max_attempts`
   attempts, report it to the human (following **Asking the human** in the orchestrator
   instructions) and stop.
8. When all gates pass:
   1. Run `bull api <M> --write` for each module, to snapshot its contract.
   2. Run `bull api --interface <Name> --write` for each interface listed under `## Interfaces`.
   3. Run `bull status checkpoint skeleton`.
   4. Commit `chore: skeleton`.
   5. Run `git tag skeleton`.
9. Tell the human that the skeleton is built and that the next step is to run `/bull:prototype`.
   This is a good point to start a fresh session; they can run `/bull:resume` there.
