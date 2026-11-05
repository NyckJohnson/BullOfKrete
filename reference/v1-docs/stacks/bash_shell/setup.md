# bash_shell setup

Manual steps before /skeleton. Fill in the tool's name from the memo wherever it says `<name>`.
After the last step, `ios-pipeline stack check` must show all ✅.

1. **Install the tools.** With Homebrew (https://brew.sh):

   ```bash
   brew install bats-core shellcheck shfmt bash
   ```

   The tool itself targets macOS's own `/bin/bash` (3.2) and needs none of these to run; they are
   for the gates. Homebrew's `bash` is used only for coverage tracing (`BASH_XTRACEFD`), which
   needs bash 4.1+. Nothing to change in your login shell.
2. **Config.** Fill in `.pipeline/config.sh`: `APP_NAME="<name>"` (leave `APP_SOURCE_DIR="lib"`
   and `APP_TEST_DIR="tests"` unless you have a reason).
3. **Write the entrypoint** `bin/<name>` (`stack select` made `bin/`, `lib/` and `tests/`, but
   can't know this file's name), then `chmod +x bin/<name>`:

   ```bash
   #!/usr/bin/env bash
   # <name>: <one line from the memo's Purpose>.
   set -euo pipefail

   <NAME>_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

   main() {
     echo "usage: <name> <command>" >&2
     return 2
   }

   main "$@"
   ```

   (`<NAME>` is the name in capitals with `_` for `-`.) The skeleton step wires the modules into
   it from the memo's Commands section.
4. **Check.** `ios-pipeline stack check`.

Notes for the human:
- `lib/Modules/<module>/` and `tests/<module>/` (literal `Modules`, capitalized: the pipeline's
  shared module convention) are created by the pipeline as each module starts.
- Coverage reports go to `.pipeline/results/`, nothing to commit.

## For a feature
A feature that needs a new external command (`jq`, `curl`, …): install it (`brew install <it>`),
and add a check for it to the entrypoint's start (`command -v <it> >/dev/null || { echo "<name>
needs <it>" >&2; exit 69; }`) so users get a clear message. Nothing else to wire up by hand.
