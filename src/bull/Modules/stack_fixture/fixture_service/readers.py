"""The `fixture_service` stack's readers: the functions bull imports from this folder.

The service stack speaks the same fixture language as the `fixture` stack (`*.fx` sources,
`pub` contract lines, `tests.json`/`coverage.json` results, a `fixture.toml` setup check, `field`
lines checked against json-schema interfaces), so its four required readers and `interface_check`
are the fixture stack's, re-exported unchanged.
"""

from __future__ import annotations

from bull.Modules.stack_fixture.fixture.readers import (
    check,
    contract_declarations,
    interface_check,
    test_results,
    uncovered,
)

__all__ = [
    "check",
    "contract_declarations",
    "interface_check",
    "test_results",
    "uncovered",
]
