# Fixture tool: setup

The fixture stack needs no installed tools: its gates run on bull's own Python. Do these steps
once per app, in the part folder.

1. Create `fixture.toml` at the part root. It may be empty. Optional keys:
   - `ok = false` makes `bull stack check` fail with "fixture.toml says not ok" (for tests).
   - `broken_toolchain = true` makes the `preflight` gate abort every run (for tests).
2. Make sure the source folder (`source_dir`, default `src`) and the test folder (`test_dir`,
   default `tests`) exist; `bull stack select fixture` creates them.
3. Run `bull stack check`. Every item should pass.

## For a feature

Nothing to set up. Check that `fixture.toml` is still present and `bull stack check` passes before
the feature starts.

## For an adoption

1. Confirm `fixture.toml` is at the existing project's root and its `*.fx` sources are under the
   source folder; `bull adopt` uses `detect`, which needs both.
2. Leave legacy `.fx` files where they are. While the adoption runs, `WARN` lines outside
   `<source_dir>/Modules/` do not fail the build; inside `Modules/` they still do.
3. Existing `.test` files stay as legacy tests until each module's switch-over replaces them.
4. Run `bull stack check`.

## Final switch

After the last module is adopted, adopt mode ends and every `WARN` line fails the build, wherever
it is. Remove the remaining `WARN` lines and any `pub Legacy<Name>` declarations left outside
modules, then run `bull gates --all` and confirm it passes.
