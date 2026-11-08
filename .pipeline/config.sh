# App settings for the iOS Agent Pipeline. Plain KEY="value" lines only: this file is
# read by both bash and Python. Paths are relative to the app folder.
#
# Defaults live in the pipeline's workflow/defaults.sh and stacks/<stack>/defaults.sh.
# To override one for this app only, copy its line here (e.g. REVIEW_MODE="split").
# Write KEY="value" or KEY='value': no spaces around =, no $VARIABLES (they are not expanded).

# The stack this app is built with (`ios-pipeline stacks` lists them). Chosen during /discuss
# with `ios-pipeline stack select <name>`, which also adds the stack's settings below.
STACK="python_cli"

# --- python_cli stack: a uv-managed, src-layout CLI package ---
# Import name of the package, and the name of its installed console script (both the same
# string, by convention — rename freely, they just have to stay in sync with pyproject.toml).
APP_PACKAGE="myapp"
# Folder containing the installable package; modules live in <APP_SOURCE_DIR>/Modules/<Module>/,
# their tests in <APP_TEST_DIR>/<Module>/ (same convention as every other stack).
APP_SOURCE_DIR="src/myapp"
APP_TEST_DIR="tests"
APP_PACKAGE="bull"
APP_SOURCE_DIR="src/bull"
