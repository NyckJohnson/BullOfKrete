# <App name> outline

The memo: what the app does, how it is split into modules, and every decision made along the way.
Replace each `<placeholder>` and each example below with the app's own. Lines that start with
`- Key:` or a number are read by bull exactly as written, so keep their shape. Text in fenced code
blocks is never read.

## Purpose
<One paragraph: who the app is for, the problem it solves, and what "done" looks like.>

## User journeys
Number each journey; the title goes in bold, then a dash and the steps. In an app with several
parts, add an indented `- Part:` line naming the part the journey runs in.

1. **<Journey title>** — <the user does this, sees that, ends here>.
   - Part: app
2. **<Another journey>** — <steps and expected result>.
   - Part: app

## Screens and navigation
<The screens, pages or other surfaces the user sees, and how they move between them. For an app
without a visual interface, describe its entry points and output instead.>

## Commands
<Only for an app with a command line: each command, its options, and the module that wires it.
Delete this section otherwise.>

## Constraints
<Platforms, language and toolchain versions, offline and account needs, third-party services,
performance limits.>

List the parts only in an app with more than one: each part's name and its stack in parentheses.
Delete the line for a one-part app.

- Parts: app (<stack>), service (<stack>)

## Out of scope
- <Something the app will not do, and why.>

## Later features
- <An idea kept for after the first version.>

## Data models
<Each stored or exchanged type: its fields, their meaning, and where it lives.>

## Build order
Modules are built in this order, foundational first. Each line names the module and the modules it
depends on (`none` when it depends on nothing); a dependency must appear earlier in the list.

1. Storage (depends on: none)
2. Orders (depends on: Storage)
3. Billing (depends on: none)

## Modules
One `###` block per module in the build order, with the same names. Keys:

`Part` (only when there are several parts) · `Depends on` (comma-separated, or `none`; must match
the build order line) · `Files` (comma-separated; split the module into work units with `|`, each
unit small enough to build in one step) · `Reference tests` (old tests the module must cover, or
`none`) · `Changes (<slug>)` (files a feature changes; each must be in `Files`) ·
`Contract changes (<slug>)` (a feature's change to the module's contract).

When adopting an existing app, also: `Legacy files` (old code the module replaces), `Legacy tests`
(old tests of that code) and `Callers to repoint` (old files that must switch to the new module).
Leave these lines out entirely when there is nothing to list.

### Storage
- Purpose: <what the module is responsible for, in one sentence>.
- Part: app
- Depends on: none
- Files: Contracts/<contract file>, mocks/<mock file>
- Behavior spec:
  - <one checkable behavior per line>
- Reference tests: none
- Contract: <written when the module is merged>

### Orders
- Purpose: <what the module is responsible for>.
- Part: app
- Depends on: Storage
- Files: Contracts/<contract file>, mocks/<mock file> | order_list.<ext>, order_detail.<ext> | order_form.<ext>
- Protocol (draft; lives in `Contracts/`):
  ```<language>
  <the module's public types and interfaces>
  ```
- Behavior spec:
  - <one checkable behavior per line>
- Legacy files: <old folder>/OrderManager.<ext>, <old folder>/OrderCache.<ext>
- Legacy tests: <old test folder>/OrderManagerTests.<ext>
- Callers to repoint: <old folder>/MainScreen.<ext>
- Reference tests: <old test file>::<test name>, <old test file>::<another test name>
- Changes (<feature-slug>): order_detail.<ext>, order_form.<ext>
- Contract changes (<feature-slug>): <the protocol or type that changes, and how>
- Contract: <written when the module is merged>

### Billing
- Purpose: <what the module is responsible for>.
- Part: service
- Depends on: none
- Files: Contracts/<contract file>, mocks/<mock file> | invoices.<ext>
- Behavior spec:
  - <one checkable behavior per line>
- Reference tests: none
- Contract: <written when the module is merged>

## Interfaces
Only in an app with several parts: one `###` block per file or message that crosses parts. A module
never depends on a module in another part; it uses an interface instead. Keys: `File` (path and
format in parentheses) · `Provider` (`<part> / <Module>`) · `Consumers` (comma-separated
`<part> / <Module>`) · `Contract changes (<slug>)` (a feature's change to the interface).

### <Interface name>
- File: <shared folder>/<interface file> (<format, e.g. JSON>)
- Provider: service / Billing
- Consumers: app / Orders
- Contract changes (<feature-slug>): <the field or message that changes, and how>

## Unmapped reference tests
Old tests that no module's `Reference tests` line covers, one per line, with the reason.

- <old test file>::<test name> — <why no module covers it>

## Legacy code
Only when adopting an existing app: the app shell (entry point, composition root, assets), which
never becomes a module, and the old code that modules replace. Delete this section otherwise.

- App shell: <entry point file>, <composition root file>
- App shell tests: <old test folder>/<app shell test file>
- Legacy folders: <old folder>, <another old folder>
- Renames: Orders → LegacyOrders, Storage → LegacyStorage

## Decisions log
One line per decision, newest last: the date, what was decided, and why.

- <YYYY-MM-DD>: <decision> — <reason>.
