# Fixture service (test stack): rules

## common
- This stack is a **service part**: the fixture language (below) plus a small HTTP service that
  bull starts before another part's journey tests and stops after them. It has no journey tests,
  interfaces or `detect` of its own.
- The fixture language is line-based and has no toolchain. Sources are `*.fx` files under
  `<source_dir>/Modules/<module>/` (`source_dir` defaults to `src`); module names are lowercase.
- In a `*.fx` file, every non-blank line not starting with `#` is a **code line**. `#` starts a
  comment line (and is the prefix for `coverage-exempt` markers).
- A module's contract lives in `<source_dir>/Modules/<module>/Contracts/*.fx`. Each `pub <decl>`
  line there is one contract declaration; `field <name>: <type>` lines (types `string`,
  `integer`, `boolean`) declare the fields of the data the module provides.
- A code line containing `WARN` is a build warning and fails the build; one containing `LINT` is a
  lint error and fails the lint gate. Neither belongs in finished code.
- Tests are `*.test` files in `<test_dir>/<module>/` (`test_dir` defaults to `tests`): `pass <name>`
  and `fail <name>` are tests (id `<module>/<file stem>::<name>`); `covers <path>:<lines>` marks
  source lines as executed, e.g. `covers src/Modules/counter/counter.fx:1,3-5` (path relative to
  the part root).
- The part root holds `fixture.toml` (see `stack setup`). Gate output goes to the part's results
  folder (`BULL_RESULTS`).
- **The service.** `[run]` has three steps, each given a port: `start <port>` launches the server
  on `127.0.0.1:<port>` in the background and returns at once, writing its pid to
  `<results>/serve-<port>.pid` and its output to `<results>/serve-<port>.log`; `ready <port>`
  polls `GET /health` until it answers 200 (`ok`); `stop <port>` terminates the server named by
  the pid file and removes the file (no pid file is not an error). bull waits up to
  `ready_timeout` (30 s) for `ready`, and always runs `stop`, also when the journeys fail.
- `GET /health` answers 200 with body `ok`; every other path answers 404. The service is
  bull's own and lives with the stack, not in the part's `*.fx` files: agents never write or
  change it.
- Other parts reach a running service through `BULL_URL_<PART>` (e.g. `http://127.0.0.1:<port>`),
  set only during their journeys. A service part is started only when the memo's `## Interfaces`
  names one of its modules as the provider of an interface that the journeying part consumes.

## outline
- Each module entry's `Files:` names `.fx` files relative to `<source_dir>/Modules/<module>/`; the
  contract file is `Contracts/<name>.fx`.
- Write the module's protocol draft as the `pub` and `field` lines its contract file will hold.
- In an app with several parts, give each module of this part a `- Part: <name>` line, and list
  every interface this part serves under `## Interfaces` with `- Provider: <this part> / <module>`
  and the consuming parts; that is what makes bull start this service for their journeys.
- This stack has no journeys gate: write the user journeys that exercise the service as journey
  tests of a consuming part whose stack has one.

## skeleton-builder
- Create `<source_dir>/Modules/<module>/Contracts/<name>.fx` with the memo's `pub` and `field`
  lines, and one `.fx` file per memo file with at least one code line.
- Create `<test_dir>/<module>/` for each module; add no tests yet.
- Make sure `fixture.toml` exists at the part root; leave no `WARN` or `LINT` lines.
- Add nothing for the service: `start`, `ready` and `stop` come with the stack and need no files.

## test-writer
- Write `<test_dir>/<module>/<file stem>.test` for each source file in the unit.
- One `pass <name>` line per behavior the spec describes; names are short `snake_case`.
- Add `covers <path>:<lines>` lines for the source lines each behavior exercises.
- Never edit `.fx` source files. Service behavior (start, `/health`, stop) is checked by the
  consuming part's journeys, not by module tests here.

## code-writer
- Write the unit's `.fx` files so every code line the spec needs exists and is covered by a
  `covers` line in the tests.
- Never edit `.test` files or anything under `Contracts/` (a contract change means `blocked`).
- Leave no `WARN` or `LINT` lines; check with the module's fast gates.
- Do not start servers yourself to test; if you do run `start <port>` by hand, run `stop <port>`
  with the same port before returning, so no server is left running.

## reviewer
- Check that each `.fx` file only holds what the spec asks for, that contract `pub` and `field`
  lines match the memo, and that no `WARN`, `LINT` or `Legacy` declarations remain in module code.
- Check that tests name every behavior in the spec and that `covers` lines point at real lines.
- Check that the memo's `## Interfaces` names this part as provider wherever a consuming part's
  journeys need the running service.

## coverage-analyst
- An uncovered line is a code line of a source file with no `covers` entry for it.
- `missed`: a behavior the spec names but no test covers. `exempt`: end the line itself with
  `# coverage-exempt: <reason>` (a marker on a line of its own exempts nothing), or wrap several
  lines in `# coverage-exempt-begin: <reason>` … `# coverage-exempt-end`. `not-in-spec`: code the
  spec never asks for.
- A file with only comments and blank lines has no coverage data; mark it with
  `# coverage-exempt-file: <reason>` in its first 10 lines.
