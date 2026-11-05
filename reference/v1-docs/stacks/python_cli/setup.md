# python_cli setup

Manual steps before /skeleton. Fill in the app's package name from the memo wherever it says
`<package>`. After the last step, `ios-pipeline stack check` must show all ✅.

1. **Install `uv`.** Follow https://docs.astral.sh/uv/getting-started/installation/ — `uv` can
   fetch a matching Python itself, so nothing else to install.
2. **Write `pyproject.toml`** at the app root (`stack select` only makes empty folders and merges
   `.gitignore`/config lines, the same for every stack — it can't know this file's content):

   ```toml
   [project]
   name = "<package>"
   version = "0.1.0"
   requires-python = ">=3.11"

   [project.scripts]
   <package> = "<package>.cli:main"

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [tool.hatch.build.targets.wheel]
   packages = ["src/<package>"]

   [tool.pytest.ini_options]
   pythonpath = ["src"]

   [tool.mypy]
   python_version = "3.11"
   strict = true

   [dependency-groups]
   dev = [
       "pytest>=8",
       "coverage[toml]>=7",
       "mypy>=1.11",
       "ruff>=0.6",
   ]
   ```
3. **Make the package importable.** `src/<package>/__init__.py` (empty file is fine) and
   `src/<package>/cli.py` with a `main()` function — the skeleton step fills these in from the
   memo's outline, but the folder and the empty `__init__.py` unblock `uv sync` before any module
   exists.
4. **Config.** Fill in `.pipeline/config.sh`: `APP_PACKAGE="<package>"`,
   `APP_SOURCE_DIR="src/<package>"`, `APP_TEST_DIR="tests"`.
5. **Sync once.** `uv sync` from the app root — creates `.venv/` and `uv.lock`.

Notes for the human:
- `src/<package>/Modules/<Module>/` and `tests/<Module>/` (both literal `Modules`, capitalized —
  the pipeline's shared module convention, same as every stack) are created by the pipeline itself
  as each module starts; nothing to do by hand there.
- Commit `pyproject.toml` and `uv.lock` once `uv sync` has run.

## For a feature
A feature that adds a third-party dependency: `uv add <package>` from the app root, then commit
the updated `pyproject.toml` and `uv.lock`. No other manual step — a plain Python package has no
capabilities, entitlements or extra targets to wire up by hand.
