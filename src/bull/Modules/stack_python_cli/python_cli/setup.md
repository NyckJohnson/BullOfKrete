# Python CLI stack: setup

Do these steps by hand once per app (or part), before `/bull:skeleton`. Replace `<package>` with
the package name from the memo. When you are done, `bull stack check` must pass every item.

1. **Install `uv`** (https://docs.astral.sh/uv/getting-started/installation/). `uv` fetches a
   matching Python itself.
2. **Write `pyproject.toml`** at the part root. `bull stack select` creates the folders and merges
   the `.gitignore` lines, but it doesn't write this file. Use this template:
   ```toml
   [project]
   name = "<package>"
   version = "0.1.0"
   requires-python = ">=3.11"
   dependencies = []

   [project.scripts]
   <package> = "<package>.cli:main"

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [tool.hatch.build.targets.wheel]
   packages = ["src/<package>"]

   [tool.pytest.ini_options]
   pythonpath = ["src"]
   testpaths = ["tests"]

   [tool.mypy]
   python_version = "3.11"
   strict = true
   mypy_path = "src"

   [dependency-groups]
   dev = ["pytest>=8", "pytest-cov>=5", "coverage[toml]>=7", "mypy>=1.11", "ruff>=0.6"]
   ```
   `pytest-cov` is there because the build gate runs `pytest --cov`.
3. **Make the package importable.** Create `src/<package>/__init__.py` (empty) and
   `src/<package>/cli.py` with a `main()` that returns 0. The skeleton fills them in.
4. **Set the settings.** Run `bull config set package <package>`. Also set `source_dir`
   (`src/<package>`) and `test_dir` (`tests`) with `bull config set` if they differ from what
   `bull stack select` wrote.
5. **Sync once.** Run `uv sync` at the part root; it creates `.venv/` and `uv.lock`. Commit
   `pyproject.toml` and `uv.lock`.
6. **Check.** Run `bull stack check`. It confirms `uv` is found, `pyproject.toml` is present, the
   package imports, and Python is 3.11 or newer.

`Modules/<module>/` and `tests/<module>/` are created as modules are built; there is nothing to
do by hand.

## For a feature

If the feature adds a third-party dependency, run `uv add <dependency>` at the part root and
commit `pyproject.toml` and `uv.lock`. Nothing else: a Python package has no capabilities or extra
targets to wire by hand.
