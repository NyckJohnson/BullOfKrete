# Fixture service (test stack): setup

The fixture service stack needs no installed tools: its gates and its service run on bull's own
Python. Do these steps once per app, in the service part's folder.

1. Create `fixture.toml` at the part root. It may be empty. Optional keys:
   - `ok = false` makes `bull stack check` fail with "fixture.toml says not ok" (for tests).
   - `broken_toolchain = true` makes the `preflight` gate abort every run (for tests).
2. Make sure the source folder (`source_dir`, default `src`) and the test folder (`test_dir`,
   default `tests`) exist; `bull stack select fixture_service` (or `bull part add <name>
   fixture_service`) creates them.
3. Check that the service can listen on `127.0.0.1`: bull picks a free port for each run, so no
   port needs to be reserved, but a firewall must allow local connections.
4. Try the service by hand, with any free port (here 8765), from the part root:
   - `python -m bull.Modules.stack_fixture.tool start 8765` starts it in the background;
   - `python -m bull.Modules.stack_fixture.tool ready 8765` exits 0 once `GET /health` answers 200;
   - `python -m bull.Modules.stack_fixture.tool stop 8765` stops it. Always stop what you start.
5. In an app with several parts, list this part as the provider of the interfaces its consumers
   use (memo `## Interfaces`), so their journeys start it.
6. Run `bull stack check`. Every item should pass.

## For a feature

Nothing to set up. Check that `fixture.toml` is still present, that no server from an earlier run
is still listed in `<results>/serve-*.pid` (run `stop <port>` for any you find), and that `bull
stack check` passes before the feature starts.

## For an adoption

This stack has no `detect`, so `bull adopt` will not pick it for an existing project. To adopt a
fixture service anyway, select it by hand (`bull stack select fixture_service`), confirm
`fixture.toml` is at the part root and its `*.fx` sources are under the source folder, and run
`bull stack check`. While the adoption runs, `WARN` lines outside `<source_dir>/Modules/` do not
fail the build; inside `Modules/` they still do.

## Final switch

After the last module is adopted, every `WARN` line fails the build, wherever it is. Remove the
remaining `WARN` lines and any `pub Legacy<Name>` declarations left outside modules, then run
`bull gates --all` and confirm it passes (consuming parts' journeys start and stop this service).
