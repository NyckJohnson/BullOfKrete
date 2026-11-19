"""Journey 7: an app with two parts (``cli`` on the fixture stack, ``web`` on fixture_service)."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

from tests.journey.conftest import (
    BullRunner,
    bull_ok,
    commit_all,
    write_files,
)

PARTS_LINE = "- Parts: cli (fixture), web (fixture_service)\n"

INTERFACE_SCHEMA = (
    '{\n  "type": "object",\n  "properties": {\n'
    '    "count": {"type": "integer"},\n    "name": {"type": "string"}\n  }\n}\n'
)

INTERFACE_BLOCK = """
## Interfaces

### TallyEvents
- File: interfaces/tally-events.json (json-schema)
- Provider: {provider}
- Consumers: {consumer}
"""


def _memo(
    export_depends: str = "none",
    import_depends: str = "none",
    provider: str | None = None,
    consumer: str | None = None,
) -> str:
    """The two-part memo: ``cli / Export`` and ``web / Import``, optionally with an interface."""
    interfaces = ""
    if provider and consumer:
        interfaces = INTERFACE_BLOCK.format(provider=provider, consumer=consumer)
    return f"""# Two parts

## Purpose
Events exported by a command line tool and imported by a web service.

## User journeys
1. **Export** — export the events.
   - Part: cli

## Constraints
{PARTS_LINE}
## Build order
1. Export (depends on: {export_depends})
2. Import (depends on: {import_depends})

## Modules

### Export
- Part: cli
- Purpose: exports events.
- Depends on: {export_depends}
- Files: Contracts/export.fx, export.fx
- Behavior spec:
  - exports the events
- Reference tests: none
- Contract: pending

### Import
- Part: web
- Purpose: imports events.
- Depends on: {import_depends}
- Files: Contracts/import.fx, import.fx
- Behavior spec:
  - imports the events
- Reference tests: none
- Contract: pending
{interfaces}
## Decisions log
"""


def _fields(extra: str = "") -> str:
    return "field name: string\nfield count: integer\n" + extra


def _skeleton(extra_export_field: str = "") -> dict[str, str]:
    """What the skeleton-builder would write for both parts (fixture language)."""
    return {
        "cli/src/Modules/Export/Contracts/export.fx": (
            "# export contract\npub Export\n" + _fields(extra_export_field)
        ),
        "cli/src/Modules/Export/export.fx": "# export\nstart value 0\n",
        "cli/tests/Export/export.test": (
            "pass exports\ncovers src/Modules/Export/export.fx:2\n"
            "covers src/Modules/Export/Contracts/export.fx:2-4\n"
        ),
        "cli/tests/journey/export.test": "pass journey_smoke\n",
        "web/src/Modules/Import/Contracts/import.fx": (
            "# import contract\npub Import\n" + _fields()
        ),
        "web/src/Modules/Import/import.fx": "# import\nstart value 0\n",
        "web/tests/Import/import.test": (
            "pass imports\ncovers src/Modules/Import/import.fx:2\n"
            "covers src/Modules/Import/Contracts/import.fx:2-4\n"
        ),
    }


def _two_part_app(
    bull: BullRunner,
    tmp_path: Path,
    env: dict[str, str],
    memo: str,
    skeleton: bool = True,
) -> Path:
    """An app with both parts added, the memo approved and the setup checkpoint recorded."""
    app = tmp_path / "ana"
    bull_ok(bull, "init", str(app), cwd=tmp_path)
    bull_ok(bull, "part", "add", "cli", "fixture", "--dir", "cli", cwd=app)
    bull_ok(bull, "part", "add", "web", "fixture_service", "--dir", "web", cwd=app)
    bull_ok(bull, "status", "stage", "1", cwd=app)
    bull_ok(bull, "status", "stage", "2", cwd=app)
    write_files(
        app,
        {"docs/outline.md": memo, "interfaces/tally-events.json": INTERFACE_SCHEMA},
    )
    commit_all(app, env, "docs: outline memo")
    bull_ok(bull, "status", "checkpoint", "outline-approved", cwd=app)
    bull_ok(bull, "status", "init-modules", cwd=app)
    write_files(app, {"cli/fixture.toml": "", "web/fixture.toml": ""})
    bull_ok(bull, "stack", "check", "--part", "cli", cwd=app)
    bull_ok(bull, "stack", "check", "--part", "web", cwd=app)
    bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
    bull_ok(bull, "status", "stage", "3", cwd=app)
    if skeleton:
        write_files(app, _skeleton())
    commit_all(app, env, "chore: setup and skeleton")
    return app


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def _service_ports(app: Path) -> list[int]:
    """Ports the web part's service was started on, from its ``serve-<port>.log`` files."""
    logs = (app / ".bull" / "results" / "web").glob("serve-*.log")
    return sorted(int(log.stem.removeprefix("serve-")) for log in logs)


def _processes_naming_port(port: int) -> list[str]:
    listing = subprocess.run(
        ["ps", "-Ao", "command"], capture_output=True, text=True, check=True
    ).stdout
    return [
        line
        for line in listing.splitlines()
        if f" {port}" in line and "serve" in line.lower()
    ]


def _assert_service_left_nothing_behind(app: Path) -> None:
    ports = _service_ports(app)
    assert ports, "the web service part was never started"
    for port in ports:
        assert _port_is_free(port), f"port {port} still answers after the run"
        assert _processes_naming_port(port) == []


def test_an_app_with_two_parts_passes_gates_all(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = tmp_path / "ana"
    bull_ok(bull, "init", str(app), cwd=tmp_path)
    added_cli = bull_ok(bull, "part", "add", "cli", "fixture", "--dir", "cli", cwd=app)
    assert "cli" in added_cli.stdout
    bull_ok(bull, "part", "add", "web", "fixture_service", "--dir", "web", cwd=app)
    listed = json.loads(bull_ok(bull, "part", "list", "--json", cwd=app).stdout)
    assert {(p["name"], p["stack"], p["dir"]) for p in listed} == {
        ("cli", "fixture", "cli"),
        ("web", "fixture_service", "web"),
    }
    assert "no problems" in bull_ok(bull, "part", "check", cwd=app).stdout
    assert (app / ".bull/parts/cli.toml").is_file()
    assert (app / ".bull/parts/web.toml").is_file()
    assert (app / "cli/src").is_dir() and (app / "web/src").is_dir()

    # Outline: the memo gives every module a part; init-modules records them.
    bull_ok(bull, "status", "stage", "1", cwd=app)
    bull_ok(bull, "status", "stage", "2", cwd=app)
    write_files(app, {"docs/outline.md": _memo()})
    commit_all(app, env, "docs: outline memo")
    bull_ok(bull, "status", "checkpoint", "outline-approved", cwd=app)
    bull_ok(bull, "status", "init-modules", cwd=app)
    status = json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)
    assert {m["name"]: m["part"] for m in status["modules"]} == {
        "Export": "cli",
        "Import": "web",
    }

    # Setup: the checkpoint is recorded only once both parts pass their stack check.
    for part in ("cli", "web"):
        refused = bull("stack", "check", "--part", part, cwd=app)
        assert refused.returncode != 0
        assert "fixture.toml" in refused.stdout
    write_files(app, {"cli/fixture.toml": ""})
    bull_ok(bull, "stack", "check", "--part", "cli", cwd=app)
    assert bull("stack", "check", "--part", "web", cwd=app).returncode != 0
    write_files(app, {"web/fixture.toml": ""})
    bull_ok(bull, "stack", "check", "--part", "web", cwd=app)
    bull_ok(bull, "status", "checkpoint", "setup", cwd=app)
    bull_ok(bull, "status", "stage", "3", cwd=app)

    # Skeleton: each module's gates run in its own part folder with its own stack.
    write_files(app, _skeleton())
    commit_all(app, env, "chore: skeleton")
    for module in ("Export", "Import"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    commit_all(app, env, "chore: api snapshots")
    export_gates = bull_ok(bull, "gates", "Export", cwd=app)
    assert "tests cli" in export_gates.stdout
    assert "web" not in export_gates.stdout
    assert (app / ".bull/results/cli/tests.json").is_file()
    import_gates = bull_ok(bull, "gates", "Import", cwd=app)
    assert "tests web" in import_gates.stdout
    assert "cli" not in import_gates.stdout
    assert (app / ".bull/results/web/tests.json").is_file()

    # gates --all: each part in name order, then journeys; the pass is recorded.
    everything = bull_ok(bull, "gates", "--all", cwd=app)
    out = everything.stdout
    assert out.index("tests cli") < out.index("tests web")
    assert "journeys cli" in out
    assert "not recorded" not in out
    assert "2 tests run" in out
    head = bull_ok(bull, "status", "ref", "trunk", cwd=app).stdout.strip()
    assert head == "main"
    passes = list((app / ".bull" / "passes").glob("*.json"))
    assert passes, "gates --all recorded no pass"


def test_a_web_module_depending_on_a_cli_module_is_refused_by_init_modules(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = tmp_path / "ana"
    bull_ok(bull, "init", str(app), cwd=tmp_path)
    bull_ok(bull, "part", "add", "cli", "fixture", "--dir", "cli", cwd=app)
    bull_ok(bull, "part", "add", "web", "fixture_service", "--dir", "web", cwd=app)
    bull_ok(bull, "status", "stage", "1", cwd=app)
    bull_ok(bull, "status", "stage", "2", cwd=app)
    write_files(app, {"docs/outline.md": _memo(import_depends="Export")})
    commit_all(app, env, "docs: outline memo")
    bull_ok(bull, "status", "checkpoint", "outline-approved", cwd=app)

    refused = bull("status", "init-modules", cwd=app)
    assert refused.returncode != 0
    message = refused.stdout + refused.stderr
    assert "Import" in message and "Export" in message
    assert "another part" in message
    assert "interface" in message
    status = json.loads(bull_ok(bull, "status", "--json", cwd=app).stdout)
    assert status["modules"] == []


def test_overlapping_part_folders_are_reported_by_part_check(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = tmp_path / "ana"
    bull_ok(bull, "init", str(app), cwd=tmp_path)
    bull_ok(bull, "part", "add", "cli", "fixture", "--dir", "cli", cwd=app)
    bull_ok(bull, "part", "add", "web", "fixture_service", "--dir", "web", cwd=app)
    assert "no problems" in bull_ok(bull, "part", "check", cwd=app).stdout

    web_part = app / ".bull/parts/web.toml"
    web_part.write_text(
        web_part.read_text().replace('dir = "web"', 'dir = "cli"'), encoding="utf-8"
    )
    checked = bull("part", "check", cwd=app)
    assert checked.returncode == 1
    assert "overlap" in checked.stdout + checked.stderr
    assert "cli" in checked.stdout + checked.stderr
    assert "web" in checked.stdout + checked.stderr


def test_interface_is_snapshotted_and_each_side_is_gated_with_its_own_stack(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    memo = _memo(provider="cli / Export", consumer="web / Import")
    app = _two_part_app(bull, tmp_path, env, memo)

    # Not snapshotted yet: the check says so; --write stores the file's text.
    before = bull("api", "--interface", "TallyEvents", cwd=app)
    assert before.returncode == 1
    assert "no snapshot" in before.stdout + before.stderr
    wrote = bull_ok(bull, "api", "--interface", "TallyEvents", "--write", cwd=app)
    assert "TallyEvents" in wrote.stdout
    snapshot = app / "docs" / "api" / "interfaces" / "TallyEvents.md"
    assert snapshot.is_file()
    assert '"count"' in snapshot.read_text()
    matches = bull_ok(bull, "api", "--interface", "TallyEvents", cwd=app)
    assert "matches its snapshot" in matches.stdout
    bull_ok(bull, "api", "Export", "--write", cwd=app)
    commit_all(app, env, "chore: interface snapshot")

    # The provider side is checked by the cli part's stack.
    export_gates = bull_ok(bull, "gates", "Export", cwd=app)
    assert "interface cli Export" in export_gates.stdout
    assert "✗" not in export_gates.stdout


def test_the_consumer_is_built_and_gated_before_the_provider_exists(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    memo = _memo(provider="cli / Export", consumer="web / Import")
    app = _two_part_app(bull, tmp_path, env, memo, skeleton=False)
    # Only the consumer's files exist: Export (the provider) has no code yet.
    consumer_only = {k: v for k, v in _skeleton().items() if k.startswith("web/")}
    write_files(app, consumer_only)
    bull_ok(bull, "api", "Import", "--write", cwd=app)
    bull_ok(bull, "api", "--interface", "TallyEvents", "--write", cwd=app)
    commit_all(app, env, "chore: consumer skeleton")
    assert not (app / "cli/src/Modules/Export").exists()

    gates = bull_ok(bull, "gates", "Import", cwd=app)
    assert "interface web Import" in gates.stdout
    assert "✗" not in gates.stdout
    assert "not recorded" not in gates.stdout


def test_gates_all_checks_interfaces_after_the_parts(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    memo = _memo(provider="cli / Export", consumer="web / Import")
    app = _two_part_app(bull, tmp_path, env, memo)
    for module in ("Export", "Import"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    bull_ok(bull, "api", "--interface", "TallyEvents", "--write", cwd=app)
    commit_all(app, env, "chore: snapshots")

    everything = bull_ok(bull, "gates", "--all", cwd=app)
    out = everything.stdout
    assert out.index("interface cli Export") < out.index("interface web Import")
    assert out.index("tests web") < out.rindex("journeys cli")
    assert "not recorded" not in out


def test_a_provider_field_missing_from_the_schema_fails_the_interface_gate_on_the_provider_side(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    memo = _memo(provider="cli / Export", consumer="web / Import")
    app = _two_part_app(bull, tmp_path, env, memo)
    for module in ("Export", "Import"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    bull_ok(bull, "api", "--interface", "TallyEvents", "--write", cwd=app)
    commit_all(app, env, "chore: snapshots")

    write_files(app, _skeleton(extra_export_field="field extra: string\n"))
    bull_ok(bull, "api", "Export", "--write", "--approved", "adds a field", cwd=app)
    commit_all(app, env, "feat(Export): extra field")
    failed = bull("gates", "Export", cwd=app)
    assert failed.returncode != 0
    assert "✗ interface cli Export" in failed.stdout
    assert "extra" in failed.stdout
    assert "not in the schema" in failed.stdout
    assert not list((app / ".bull" / "passes").glob("*.json"))


def test_editing_the_interface_file_fails_the_api_gate_until_approved(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    memo = _memo(provider="cli / Export", consumer="web / Import")
    app = _two_part_app(bull, tmp_path, env, memo)
    for module in ("Export", "Import"):
        bull_ok(bull, "api", module, "--write", cwd=app)
    bull_ok(bull, "api", "--interface", "TallyEvents", "--write", cwd=app)
    commit_all(app, env, "chore: snapshots")

    edited = INTERFACE_SCHEMA.replace(
        '"name": {"type": "string"}',
        '"name": {"type": "string"},\n    "tag": {"type": "string"}',
    )
    write_files(app, {"interfaces/tally-events.json": edited})
    commit_all(app, env, "feat: interface gains tag")

    checked = bull("api", "--interface", "TallyEvents", cwd=app)
    assert checked.returncode == 1
    assert "differs from its snapshot" in checked.stdout
    assert "tag" in checked.stdout
    gates = bull("gates", "--all", cwd=app)
    assert gates.returncode != 0
    assert "TallyEvents" in gates.stdout
    refused = bull("api", "--interface", "TallyEvents", "--write", cwd=app)
    assert refused.returncode != 0
    assert "must approve" in refused.stdout + refused.stderr

    bull_ok(bull, "status", "approve", "TallyEvents", "tag field agreed", cwd=app)
    written = bull_ok(bull, "api", "--interface", "TallyEvents", "--write", cwd=app)
    assert "wrote" in written.stdout
    assert '"tag"' in (app / "docs/api/interfaces/TallyEvents.md").read_text()
    matches = bull_ok(bull, "api", "--interface", "TallyEvents", cwd=app)
    assert "matches its snapshot" in matches.stdout


def _service_provider_app(
    bull: BullRunner, tmp_path: Path, env: dict[str, str]
) -> Path:
    """An app whose interface is provided by the service part, consumed by the cli part."""
    memo = _memo(provider="web / Import", consumer="cli / Export")
    return _two_part_app(bull, tmp_path, env, memo)


def test_the_service_part_is_started_ready_and_stopped_around_a_cross_part_journey(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    app = _service_provider_app(bull, tmp_path, journey_env)

    done = bull_ok(bull, "gates", "--journeys", cwd=app)
    assert "journeys cli" in done.stdout
    assert "not ready" not in done.stdout + done.stderr
    _assert_service_left_nothing_behind(app)


def test_the_service_part_is_stopped_even_when_the_cross_part_journey_fails(
    bull: BullRunner, tmp_path: Path, journey_env: dict[str, str]
) -> None:
    env = journey_env
    app = _service_provider_app(bull, tmp_path, env)
    write_files(app, {"cli/tests/journey/export.test": "fail export_is_broken\n"})
    commit_all(app, env, "test: a failing journey")

    failed = bull("gates", "--journeys", cwd=app)
    assert failed.returncode != 0
    assert "✗ journeys cli" in failed.stdout
    _assert_service_left_nothing_behind(app)
