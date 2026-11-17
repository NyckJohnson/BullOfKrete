# Fixture tool: rules

## common
- The fixture language is line-based and has no toolchain. Sources are `*.fx` files under
  `<source_dir>/Modules/<module>/` (`source_dir` defaults to `src`); module names are lowercase.
- In a `*.fx` file, every non-blank line not starting with `#` is a **code line**. `#` starts a
  comment line (and is the prefix for `coverage-exempt` markers).
- A module's contract lives in `<source_dir>/Modules/<module>/Contracts/*.fx`. Each `pub <decl>`
  line there is one contract declaration; `field <name>: <type>` lines (types `string`,
  `integer`, `boolean`) declare the fields an interface file is checked against.
- `pub Legacy<Name>` marks legacy code still waiting to be adopted.
- A code line containing `WARN` is a build warning and fails the build; one containing `LINT` is a
  lint error and fails the lint gate. Neither belongs in finished code.
- Tests are `*.test` files in `<test_dir>/<module>/` (`test_dir` defaults to `tests`): `pass <name>`
  and `fail <name>` are tests (id `<module>/<file stem>::<name>`); `covers <path>:<lines>` marks
  source lines as executed, e.g. `covers src/Modules/counter/a.fx:1,3-5` (path relative to the
  part root).
- Journey tests are `<test_dir>/journey/*.test`, same syntax.
- The part root holds `fixture.toml` (see `stack setup`). Gate output goes to `results/`.

## outline
- Each module entry's `Files:` names `.fx` files relative to `<source_dir>/Modules/<module>/`; the
  contract file is `Contracts/<name>.fx`.
- Write the module's protocol draft as the `pub` and `field` lines its contract file will hold.
- Journeys are `.test` files under `tests/journey/`, one per user journey.

## skeleton-builder
- Create `<source_dir>/Modules/<module>/Contracts/<name>.fx` with the memo's `pub` and `field`
  lines, and one `.fx` file per memo file with at least one code line.
- Create `<test_dir>/<module>/` for each module; add no tests yet.
- Make sure `fixture.toml` exists at the part root; leave no `WARN` or `LINT` lines.

## test-writer
- Write `<test_dir>/<module>/<file stem>.test` for each source file in the unit.
- One `pass <name>` line per behavior the spec describes; names are short `snake_case`.
- Add `covers <path>:<lines>` lines for the source lines each behavior exercises.
- Never edit `.fx` source files.

## code-writer
- Write the unit's `.fx` files so every code line the spec needs exists and is covered by a
  `covers` line in the tests.
- Never edit `.test` files or anything under `Contracts/` (a contract change means `blocked`).
- Leave no `WARN` or `LINT` lines; check with the module's fast gates.

## reviewer
- Check that each `.fx` file only holds what the spec asks for, that contract `pub` and `field`
  lines match the memo, and that no `WARN`, `LINT` or stray `Legacy` declarations remain in
  module code.
- Check that tests name every behavior in the spec and that `covers` lines point at real lines.

## coverage-analyst
- An uncovered line is a code line of a source file with no `covers` entry for it.
- `missed`: a behavior the spec names but no test covers. `exempt`: add a `# coverage-exempt`
  comment line directly above the line, with the reason. `not-in-spec`: code the spec never asks
  for.
- A file with only comments and blank lines has no coverage data.

## journey-test-writer
- Write `<test_dir>/journey/<journey>.test`, one `pass <step>` line per step of the journey as the
  memo describes it.
- Journey tests never `covers` module lines; they run in the `journeys` gate only.

## surveyor
- A fixture project has `fixture.toml` at its root and `*.fx` sources; `detect` reports 0.9
  confidence when both exist.
- List each folder of `.fx` files as a candidate module; list every `pub Legacy<Name>` line as
  legacy code to replace, and every `.test` file as a legacy test.
- Note any `WARN` lines outside `Modules/`: they are tolerated while adopting and must be gone
  before the final switch.
