---
description: Stage 2 — write the outline memo and get it approved (checkpoint 1)
---

Run `ios-pipeline status stage 2`.

1. Write `docs/outline.md` from `docs/discussion-notes.md`, following the
   structure of the template that `ios-pipeline template outline` prints, exactly, and the
   stack's memo conventions (`ios-pipeline stack rules outline`). If no stack is selected
   (`ios-pipeline stack show` fails), go back and settle it as `/discuss` describes. In an app with
   several parts (`ios-pipeline part list`), read each part's conventions (`--part <part>`), list the
   parts under Constraints, give every module and journey a `- Part:` line, and keep each module's
   dependencies inside its own part (`status init-modules` refuses the rest).
2. Design modules as folders in the app's source folder, ordered from no dependencies to most.
   Each module lists its files in build order (split into work units with `|`, at most
   `MAX_FILES_PER_UNIT` files each; contracts and models first), its dependencies, and a draft
   protocol (it will live in the module's `Contracts/` folder). Views and view models live in feature modules; view
   files go in a `Views/` folder (excluded from coverage).
3. List "anticipated operations" per module, but plan to build only what the
   journeys need plus cheap, obvious complements. Copy the notes' later features and out-of-scope
   items into the memo's `Later features` and `Out of scope` sections, one `- <Title>: …` item each.
4. Check the readiness list and report each item to the human as ✅ or ❌:
   - Purpose and all core user journeys are written down.
   - Screen list and navigation flow are known.
   - Every module has a purpose, dependencies, and a draft protocol.
   - Data models are defined with fields and types.
   - Build order is set.
   - Persistence, networking and third-party choices are made.
   - Out-of-scope items are listed.
   - Final test: could an agent build any one module from the memo alone?
5. Ask the human to review the memo. Revise until they approve.

On approval:
- `ios-pipeline status init-modules` (reads the build order and each
  module's work units from the memo and fills `status.json`; check its output).
- Commit `docs: outline approved`, then `git tag outline-approved`.
- `ios-pipeline status checkpoint outline-approved`.
- Tell the human to run `/setup`.
