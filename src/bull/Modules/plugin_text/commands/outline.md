---
description: "Stage 2 — write the outline memo and get it approved (checkpoint 1)"
---

# Stage 2: Outline

You turn the discussion notes into the outline memo, the spec every later stage builds from, and
get the human to approve it.

1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a pause
   and stop.
2. Run `bull status stage 2`.
3. Run `bull config show` and look at the `stack` key, and run `bull part list`. Only when there is
   neither a stack nor a part is the discussion not finished: then tell the human to go back to the
   discuss step (`/bull:discuss`) and stop.
4. Read `docs/discussion-notes.md`. Then write `docs/outline.md`:
   - Follow the template from `bull template outline` exactly: its sections, their order and
     their line formats.
   - Follow the stack's memo rules from `bull stack rules outline`.
5. If the app has parts:
   - Read each part's memo rules with `bull stack rules outline --part <name>`.
   - List the parts under Constraints as `- Parts: <name> (<stack>), …`.
   - Give every module and every journey a `- Part: <name>` line.
   - Keep each module's dependencies inside its own part. A module never depends on a module in
     another part.
   - Describe every interface between parts under `## Interfaces`: its file, format, provider and
     consumers.
6. Write the modules:
   - Modules are folders, not packages. Put modules with no dependencies first in the build order.
   - Give each module a `Files:` line listing its files in build order, with contracts and models
     first. When a module has more files than `max_files_per_unit`, split the line into units with
     `|`, each unit holding at most `max_files_per_unit` files.
   - List each module's dependencies.
   - Draft each module's protocol: the types and operations other modules use. It lives in the
     module's `Contracts/` folder.
   - Place view files where the stack rules say.
   - Add an "Anticipated operations" list: operations the journeys do not need yet but will soon.
     Build only what the journeys need, plus cheap, obvious complements from that list.
7. Copy the later features and the out of scope items from the notes into the memo, in the same
   `- <Title>: <description or reason>` format.
8. **Rewrite of an existing tool.** When the app replaces an old tool whose tests are kept as
   reference (in the `reference_dir` folder), give each module a `Reference tests:` line naming the
   old tests that cover its behavior. List every old test that maps to no module under
   `## Unmapped reference tests`, each with a reason.
9. Check the memo against this readiness list and report each item to the human as ✅ or ❌:
   - Purpose and all core journeys written down
   - Screens (or command surface) and navigation flow known
   - Every module has a purpose, dependencies and a draft protocol (files split into units)
   - Data models defined with fields and types
   - Build order set
   - Persistence, networking and third-party choices made (or none needed)
   - Out of scope items listed
   - Final test: could an agent build any one module from the memo alone? Answer it by checking
     one module's block against its dependencies' protocols.

   Also check that the later features from the notes were copied into the memo (step 7).

10. Ask the human to read the memo and approve it. Say what approving commits them to: every later
    stage builds from it, and a later change to a contract stops the pipeline for their approval.
    Revise the memo for each correction and report the readiness list again, until the human
    approves it.
11. On approval:
    1. Run `bull status init-modules`. Check its output: it refuses memo problems and names them
       with line numbers. Fix each one in the memo, and run it again until it succeeds.
    2. Run `bull status checkpoint outline-approved`.
    3. Commit `docs: outline approved`.
    4. Run `git tag outline-approved`.
12. Tell the human the memo is approved and that the next step is to run `/bull:setup`. This is a
    good point to start a fresh session; they can run `/bull:resume` there.
