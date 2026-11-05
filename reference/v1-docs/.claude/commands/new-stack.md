---
description: Add a new stack (language/toolchain the pipeline can build apps with) — pipeline repo only
argument-hint: "[stack name]"
---

This is a **pipeline-repo command**, not part of the plugin: it edits the pipeline itself
(`stacks/<name>/`), which app sessions never do. It does not exist inside an app.

0. **Refuse if this isn't the pipeline repo, or is inside an app.** If the current folder (or any
   ancestor) has `.pipeline/config.sh`, or this repo isn't `ios-agent-pipeline` itself (no
   `stacks/README.md` here), stop and say so: this command only runs in the pipeline repo, on a
   session that has never `cd`'d into an app folder.
1. **Resume check.** If `$1` names an existing `stacks/<name>/DESIGN.md`, read its "Build
   checklist" and resume at the first unchecked box. Otherwise this is a fresh stack: `$1` is the
   name (ask for one if missing; lowercase, e.g. `python-cli`).

### Step 1 — Discuss and design
Only if "Design discussed and approved by the human" isn't checked yet.

Talk through, and settle, every question in `stacks/_template/DESIGN.md`'s headings: language and
version, package/build tool, test framework (and how to run one module's tests and a single failing
test), coverage tool and data format, lint/format tools, what a contract is in this language and
how `contract.py` will read it, how modules map to this language's normal folder layout (don't
force Swift's `Modules/<Module>/{Contracts,Mocks,Views}` shape if the language organizes code
differently), `STACK_KIND`, whether it has a journey/end-to-end layer, the human's one-time setup,
and whether adoption support (`detect.py`/`inventory.py`) is in scope now or later. Read
`stacks/README.md`'s "Writing a stack's files" section and `stacks/ios/` as a reference (the
*shape*, not Swift/Xcode specifics) before proposing answers.

Write the answers into `stacks/<name>/DESIGN.md` (create it with `ios-pipeline stack new <name>` if
it doesn't exist yet — refuses if the name is invalid, already exists, or this is run inside an
app). **Stop and get the human's explicit approval of the filled-in design before continuing.**
Check its box once approved.

### Step 2 — Scaffold
`ios-pipeline stack new <name>` (if not already run in step 1): writes a minimal `stack.sh`
(`TODO` placeholders, `STACK_MATURITY="experimental"`) and copies in `DESIGN.md`. Check its box.

### Step 3 — Fixture and cases first
Only if not already checked.

Write `stacks/<name>/fixture/` (a tiny one- or two-module app in this stack, passing every gate —
prefer files the pipeline can write itself over a hand-made project file; the latter is the
exception, not the default) and `stacks/<name>/cases.json` from `stacks/_template/cases.json`'s
shape, covering the required case ids (`stacks/README.md` "Self-test"; add `journey`/
`journey-failing` only if this stack will define `stack_ui_tests`). Write every manifest key in
`stack.sh` for real (clear the `TODO`s), since `--static` checks them.

Run `ios-pipeline stack test <name> --static` and fix what it reports until it passes. This needs
no toolchain and checks shape only — it does **not** mean the gates work yet. Check this box once
`--static` passes.

### Step 4 — Write the stack
Only if not already checked.

Write `gates.sh` (the functions `stack_preflight`, `stack_setup_gate`, `stack_build_test`,
`stack_build_test_fast`, `stack_lint`, `stack_rerun_failed`, and `stack_ui_tests` if this stack has
a journey layer — defining it is what turns journeys on, nothing else to flip), `contract.py`,
`coverage.py`, `check.py`, and `setup.md`, each from the spec in `stacks/README.md` ("Writing a
stack's files") — write each for this language's own idioms, not by copying `stacks/ios/`'s files
and editing them.

Run `ios-pipeline stack test <name>` (no `--static`: this needs the real toolchain) and iterate
until every case passes. Check this box once it does.

### Step 5 — Rules
Only if not already checked.

Write `stacks/<name>/rules.md`: `## common`, one `## <agent>` section per required agent
(`stacks/README.md` lists which), and `## outline`. **Stop and get the human's review before
continuing** — these rules shape every line the agents will write. Check this box once reviewed.

### Step 6 — Land it
Only if not already checked.

Add the stack to the table in `stacks/README.md` as `experimental`. Run
`python3 -m unittest discover -s tests` and fix anything it breaks. Commit on a branch named for
the stack, and open a PR (this repo's usual working agreement: branch from `main`, no stacked
PRs). Check this box.

Tell the human when every box is checked, and that the stack moves to `verified` once a real app
has shipped with it (`ios-pipeline stacks` shows the maturity).
