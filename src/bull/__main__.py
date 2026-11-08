"""`python -m bull`: the same entry point as the `bull` console script."""

from __future__ import annotations

import sys

from bull.Modules.cli.main import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
