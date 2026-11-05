<!--
This is the discussion record and build checklist for a new stack, created by
`ios-pipeline stack new <name>` and filled in by `/new-stack` (stacks/README.md "Adding a stack").
Keep the headings; /new-stack resumes from the checked boxes at the bottom.
-->

# <name> stack: design

## Language and tools
- Language and version:
- Package/build tool:
- Test framework:
  - Run one module's tests only (`--fast`):
  - Run a single failing test by id (`--failed`):
- Coverage tool and data format:
- Lint tool(s):
- Format tool:

## Contracts
What a contract (a module's `Contracts/` folder) is in this language, and how `contract.py` reads
it (a real parser, or a line scanner like iOS's — state which and why):

## Modules
How modules map to folders in this language's normal layout (mirror, don't force Swift's
`Modules/<Module>/{Contracts,Mocks,Views}` shape if this language organizes code differently):

## Kind
`STACK_KIND`: `app` (has screens) / `service` (runs as a process) / `tool` (neither).
Does it have a journey/end-to-end layer (`stack_ui_tests`)? If so, what does a "UI test" mean here
(a real UI, a CLI run end to end, an HTTP call)?

## Human setup
What a human installs and configures once, before `/setup` can check it:

## Adoption support
Planned now, or left for later (`detect.py`/`inventory.py` are optional)?

## Decisions log
- <date>: <decision>, <reason>

---

## Build checklist
(`/new-stack` reads these to know where to resume)

- [ ] Design discussed and approved by the human
- [ ] `stack new` scaffold exists (`stack.sh`, this file)
- [ ] Fixture and `cases.json` written; `ios-pipeline stack test <name> --static` passes
- [ ] `gates.sh`, `contract.py`, `coverage.py`, `check.py`, `setup.md` written; `ios-pipeline stack test <name>` passes every case
- [ ] `rules.md` written and reviewed by the human
- [ ] Added to `stacks/README.md` as `experimental`; pipeline unit tests pass; PR opened
