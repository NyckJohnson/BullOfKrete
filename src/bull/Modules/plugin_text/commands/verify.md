---
description: "Stage 6 — test and verify the full app (checkpoint 4)"
---

# Stage 6: Verify

Every module is built and merged. Now you check the app as a whole: no mocks left in real code, a
journey test for every journey, a review across all modules, and the human's own hands-on try. It
ends when the human accepts the app; then you help them queue what comes next.

During an adoption, `/bull:adopt`'s stage 6 replaces this command; follow it instead. During a
feature, run only the checks from mocks-check through hands-on (steps 3 to 8, with the feature's
changes), and take the feature's acceptance and next step from `/bull:feature`, not steps 9 to 11.

1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a pause
   and stop.
2. Run `bull status stage 6`. If it is refused, tell the human which earlier step is missing and
   stop.
3. Set the progress gauge:
   `bull status plan verify mocks-check <one item per journey> app-review fixes hands-on backlog`,
   with one item per memo journey in the middle. Mirror the items as a task list. Run
   `bull status tick <item>` as each item finishes, before that step's commit.
4. **mocks-check.** Check that real implementations are wired in everywhere: mocks only in tests and
   previews. Search the source for the mock types and make sure nothing else uses them. Route
   anything you find as in step 7. Tick `mocks-check`.
5. **Journey tests.** Run `bull status usage-check`, then brief the **journey-test-writer**: one
   journey test per memo journey. In an app with parts, write one brief per part whose stack has
   journey tests, with that part's `PART: <name> (<stack>)` line and only that part's journeys. Then
   run `bull gates --journeys`. Tick each journey as its test passes, and commit.
6. **app-review.** Run `bull status usage-check`, then brief the **reviewer** with
   `SCOPE: whole app` (in an app with parts, list every part). It checks consistency across modules
   and the stack's whole-app items, which it reads from the stack rules. Tick `app-review`.
7. **fixes.** Route each failing journey test and each review finding to the owning module's unit,
   and rerun its Stage 5 loop for that unit (attempts count). If the design is wrong, not just the
   code, propose a memo change first, following **Asking the human**, and fix the code only after
   the human approves it. Rerun `bull gates --journeys` when the fixes are merged. Tick `fixes`.
8. **hands-on.** Ask the human to use the app the way its users will (the stack's setup guide says
   how), going through every journey in the memo. Collect what they find as a numbered list. For
   each item, ask whether to:
   - **fix now**: route it as in step 7;
   - **later**: queue it with `bull feature add "<Title>: <what they said>"`;
   - **drop**: note it and move on.

   Retest each fix with the human. Repeat until the list is empty, then ask them to accept the app.
9. On acceptance:
   1. Tick `hands-on`.
   2. Run `bull status checkpoint app-accepted`.
   3. Commit `chore: app accepted`.
   4. Run `git tag app-accepted`.
10. **backlog.** Help the human decide what to build next:
    1. Preview both lists the memo keeps for later:
       `bull feature import docs/outline.md --section "Later features" --dry-run` and
       `bull feature import docs/outline.md --section "Out of scope" --dry-run`.
    2. Show them as two short lists, plus what step 8 already queued. Ask which to queue and in what
       order.
    3. Queue each chosen item with `bull feature add "<Title>: <desc>"` (add `--top` where the human
       asks for it first). Reorder with `bull feature move <slug> <pos>`.
    4. Tick `backlog`, then run `bull status plan verify --clear`.
    5. Commit `docs: queue features after first release`.
    6. Show the queue with `bull feature list`.
11. Ask the human whether to start the first feature now or later. To start it, they run
    `/bull:feature`, ideally in a fresh session.
