#!/usr/bin/env python3
"""Move an app built with ios-pipeline (v1) under bull (v2).

    python3 scripts/migrate_v1.py <app-folder>...            # dry run: show what would change
    python3 scripts/migrate_v1.py --apply <app-folder>...    # migrate and commit

Per app it:
  1. checks the app is a git repo root on its base branch with a fully clean tree, and that no
     v1 feature or adoption is active;
  2. converts .pipeline/status.json into .bull/status.json (stage, checkpoints, modules, units,
     pause) and the v1 feature list into .bull/backlog.json;
  3. maps .pipeline/config.sh onto bull settings (`bull config set`);
  4. lets bull rebuild the module list from docs/outline.md (`bull status init-modules
     --replace`) and keeps that result only if no progress is lost;
  5. removes the v1 CLAUDE.md block, the ios-pipeline permissions and status line, .pipeline/
     and its .gitignore lines;
  6. commits, then runs `bull init .` (relink: bull's CLAUDE.md block, settings, .gitignore).

Stdlib only; needs `bull` and `git` on PATH. A one-off tool, not part of bull.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

APP_CHECKPOINTS = (
    "outline-approved",
    "setup",
    "skeleton",
    "ui-approved",
    "app-accepted",
)
UNIT_ORDER = ("pending", "tests", "code", "done")
MAX_ATTEMPTS = 3
COMMIT_MESSAGE = "chore: migrate from ios-pipeline (v1) to bull"

# v1 config.sh key -> bull key, per stack (None: dropped on purpose).
COMMON_KEYS = {
    "STACK": "stack",
    "BASE_BRANCH": "base_branch",
    "REVIEW_MODE": "review_mode",
    "MAX_ATTEMPTS": "max_attempts",
    "MAX_FILES_PER_UNIT": "max_files_per_unit",
    "COVERAGE_EXCLUDE_EXTRA": "coverage.exclude_extra",
}
STACK_KEYS = {
    "ios": {
        "APP_PROJECT": "project",
        "APP_SCHEME": "scheme",
        "APP_SOURCE_DIR": "source_dir",
        "APP_TEST_DIR": "test_dir",
        "UNIT_TEST_TARGET": "unit_test_target",
        "UI_TEST_TARGET": "ui_test_target",
        "SIMULATOR_NAME": "simulator",
        "APP_MODULE": None,
    },
    "python_cli": {
        "APP_PACKAGE": "package",
        "APP_SOURCE_DIR": "source_dir",
        "APP_TEST_DIR": "test_dir",
    },
}


class Stop(Exception):
    """The app can't be migrated as it is; the message says why."""


def run(
    cmd: list[str], cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, check=False, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise Stop(f"`{shlex.join(cmd)}` failed:\n{result.stdout}{result.stderr}")
    return result


# --- reading v1 ---------------------------------------------------------------------------


def read_config_sh(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        parts = shlex.split(raw, comments=True)
        values[key.strip()] = parts[0] if parts else ""
    return values


def regex_to_globs(pattern: str) -> list[str]:
    """Best effort for v1's COVERAGE_EXCLUDE_EXTRA regexes: `[^/]+` -> `*`, `(a|b)` -> two globs."""
    alternatives = [pattern]
    while any("(" in p for p in alternatives):
        expanded = []
        for p in alternatives:
            m = re.search(r"\(([^()]*)\)", p)
            if m is None:
                expanded.append(p)
                continue
            for choice in m.group(1).split("|"):
                expanded.append(p[: m.start()] + choice + p[m.end() :])
        alternatives = expanded
    globs = []
    for p in alternatives:
        glob = p.replace("[^/]+", "*").replace("[^/]*", "*").replace(".*", "*")
        glob = glob.lstrip("^").rstrip("$")
        if not glob.startswith("*"):
            glob = "*" + glob
        if not glob.endswith("*"):
            glob += "*"
        globs.append(glob)
    return globs


def map_config(v1: dict[str, str], warn: list[str]) -> dict[str, str]:
    stack = v1.get("STACK") or ("ios" if "APP_PROJECT" in v1 else "")
    if not stack:
        raise Stop("config.sh has no STACK and doesn't look like an iOS app")
    if stack not in STACK_KEYS:
        raise Stop(f"stack {stack!r} has no mapping in this script")
    keys = {**COMMON_KEYS, **STACK_KEYS[stack]}
    out = {"stack": stack}
    for key, value in v1.items():
        if key == "STACK":
            continue
        if key not in keys:
            warn.append(f"config.sh {key}={value!r} has no bull equivalent; dropped")
            continue
        target = keys[key]
        if target is None:
            continue
        if key == "COVERAGE_EXCLUDE_EXTRA":
            globs = regex_to_globs(value)
            warn.append(
                f"COVERAGE_EXCLUDE_EXTRA regex {value!r} became globs {globs}; check them"
            )
            value = ",".join(globs)
        if key == "SIMULATOR_NAME" and "," in value:
            device = value.split(",")[0].strip()
            warn.append(
                f"SIMULATOR_NAME {value!r} is a destination, bull wants a device name; "
                f"using {device!r}"
            )
            value = device
        out[target] = value
    if stack == "ios" and "ui_test_target" in out and "test_dir" in out:
        out["ui_test_dir"] = str(Path(out["test_dir"]).parent / out["ui_test_target"])
    return out


def merge_units(files: list[dict]) -> dict:
    """Old v1 per-file module records become one unit holding every file."""
    states = [f.get("state", "pending") for f in files]
    if "blocked" in states:
        state = "blocked"
    else:
        state = (
            UNIT_ORDER[min(UNIT_ORDER.index(s) for s in states)]
            if states
            else "pending"
        )
    attempts = max((f.get("attempts", 0) for f in files), default=0)
    return {
        "number": 1,
        "files": [f["name"] for f in files],
        "state": state,
        "attempts": attempts,
    }


def convert_status(v1: dict, warn: list[str]) -> dict:
    if v1.get("activeFeature"):
        raise Stop(
            f"v1 feature {v1['activeFeature']!r} is active; finish or abandon it first"
        )
    adopt = v1.get("adopt")
    if adopt and adopt.get("state") != "finished":
        raise Stop("a v1 adoption is in progress; finish or abandon it first")

    checkpoints = list(v1.get("checkpoints") or {})
    dropped = [c for c in checkpoints if c not in APP_CHECKPOINTS]
    if dropped:
        warn.append(
            f"checkpoints not on bull's app track dropped: {', '.join(dropped)}"
        )

    modules = []
    for m in v1.get("modules", []):
        units = m.get("units")
        if units is None:
            units = [merge_units(m.get("files", []))]
            warn.append(f"module {m['name']}: old per-file record merged into one unit")
        modules.append(
            {
                "name": m["name"],
                "part": "app",
                "depends": list(m.get("dependsOn", [])),
                "state": m.get("state", "pending"),
                "reference_tests": False,
                "scan": None,
                "units": [
                    {
                        "number": u["number"],
                        "files": list(u.get("files", [])),
                        "kind": "code",
                        "state": u.get("state", "pending"),
                        # v1 counted failed attempts from 0; bull counts the current one from 1.
                        "attempts": min(u.get("attempts", 0) + 1, MAX_ATTEMPTS),
                    }
                    for u in units
                ],
            }
        )

    pause = None
    if v1.get("paused"):
        pause = {
            "reason": v1.get("pauseReason") or "paused under ios-pipeline",
            "since": to_utc(v1.get("updatedAt")),
            "unit": None,
        }
    return {
        "format": 1,
        "kind": "app",
        "stage": int(v1.get("stage", 0)),
        "checkpoints": [c for c in checkpoints if c in APP_CHECKPOINTS],
        "modules": modules,
        "pause": pause,
        "waiting": None,
        "approvals": [],
        "plan": None,
        "feature": None,
        "adoption": None,
    }


def to_utc(text: str | None) -> str:
    when = datetime.fromisoformat(text) if text else datetime.now(UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def idea_of(root: Path, brief: str | None, title: str) -> str:
    if brief and (root / brief).is_file():
        m = re.search(
            r"^## Idea\s*\n(.*?)(?=^## |\Z)",
            (root / brief).read_text(),
            re.MULTILINE | re.DOTALL,
        )
        if m and m.group(1).strip():
            return " ".join(m.group(1).split())
    return title


def convert_backlog(root: Path, v1: dict) -> dict:
    items = []
    for f in v1.get("features") or []:
        items.append(
            {
                "slug": f["slug"],
                "title": f["title"],
                "description": idea_of(root, f.get("brief"), f["title"]),
                "state": f.get("state", "queued"),
                "added": to_utc(f.get("addedAt")),
                "brief": f.get("brief") or f"docs/features/{f['slug']}.md",
            }
        )
    return {"format": 1, "items": items}


# --- cleaning v1 files --------------------------------------------------------------------

V1_BLOCK = re.compile(
    r"<!-- ios-pipeline:begin.*?<!-- ios-pipeline:end -->\n?", re.DOTALL
)
V1_IMPORT = re.compile(r"^@\S*ios-agent-pipeline\S*\n?", re.MULTILINE)


V1_NOTE = re.compile(r"goes here, below the\s+managed block above\.")


def clean_claude_md(text: str) -> str:
    text = V1_IMPORT.sub("", V1_BLOCK.sub("", text)).lstrip("\n")
    return V1_NOTE.sub("goes here.", text)


def clean_settings(data: dict) -> dict:
    def v1(text: str) -> bool:
        return "ios-pipeline" in text or "ios-agent-pipeline" in text

    status_line = data.get("statusLine")
    if isinstance(status_line, dict) and v1(str(status_line.get("command", ""))):
        del data["statusLine"]
    permissions = data.get("permissions")
    if isinstance(permissions, dict):
        for key in ("allow", "deny", "ask"):
            if isinstance(permissions.get(key), list):
                permissions[key] = [p for p in permissions[key] if not v1(p)]
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for event in list(hooks):
            kept = [h for h in hooks[event] if not v1(json.dumps(h))]
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
        if not hooks:
            del data["hooks"]
    return data


def clean_gitignore(text: str) -> str:
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not line.startswith(".pipeline")
    )


# --- one app ------------------------------------------------------------------------------


def progress(status: dict) -> dict[str, list[tuple]]:
    return {
        m["name"]: [(tuple(u["files"]), u["state"]) for u in m["units"]]
        for m in status["modules"]
    }


def migrate(root: Path, apply: bool, any_branch: bool = False) -> None:
    root = root.expanduser().resolve()
    warn: list[str] = []
    v1_dir = root / ".pipeline"
    if not (v1_dir / "status.json").is_file():
        raise Stop("no .pipeline/status.json: not a v1 app")
    top = run(["git", "rev-parse", "--show-toplevel"], root).stdout.strip()
    if Path(top).resolve() != root:
        raise Stop(f"not a git repo root (the root is {top})")

    v1_status = json.loads((v1_dir / "status.json").read_text())
    config = map_config(read_config_sh(v1_dir / "config.sh"), warn)
    status = convert_status(v1_status, warn)
    backlog = convert_backlog(root, v1_status)

    bull_dir = root / ".bull"
    if bull_dir.exists():
        old = json.loads((bull_dir / "status.json").read_text())
        if old.get("modules") or old.get("checkpoints") or old.get("stage"):
            raise Stop(".bull/ already holds progress: already migrated?")
        warn.append(".bull/ from an earlier `bull init` holds no progress; replaced")

    base = config.get("base_branch", "main")
    branch = run(["git", "branch", "--show-current"], root).stdout.strip()
    if branch != base and not any_branch:
        raise Stop(
            f"on branch {branch!r}; switch to {base!r} first "
            "(or pass --any-branch to migrate a paused module branch in place)"
        )
    dirty = run(["git", "status", "--porcelain"], root).stdout
    if dirty.strip():
        raise Stop(f"the tree isn't clean (untracked files count too):\n{dirty}")

    done = sum(u["state"] == "done" for m in status["modules"] for u in m["units"])
    total = sum(len(m["units"]) for m in status["modules"])
    print(
        f"  stage {status['stage']}, checkpoints: {', '.join(status['checkpoints']) or 'none'}"
    )
    print(
        f"  modules {len(status['modules'])}, units {done}/{total} done"
        + (f", paused ({status['pause']['reason']})" if status["pause"] else "")
    )
    print(f"  backlog: {len(backlog['items'])} item(s)")
    print("  config: " + ", ".join(f"{k}={v}" for k, v in config.items()))
    if not apply:
        for w in warn:
            print(f"  note: {w}")
        print("  (dry run; nothing changed)")
        return

    # 1. bull's state files.
    if bull_dir.exists():
        shutil.rmtree(bull_dir)
    bull_dir.mkdir()
    (bull_dir / "config.toml").write_text("format = 1\n")
    (bull_dir / "status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n"
    )
    (bull_dir / "backlog.json").write_text(json.dumps(backlog, indent=2) + "\n")
    (bull_dir / "events.jsonl").write_text("")
    run(["bull", "status", "--json"], root)  # bull reads it back, or we stop here

    # 2. settings.
    for key, value in config.items():
        run(["bull", "config", "set", key, value], root)

    # 3. let bull rebuild the modules from the memo, unless that loses progress.
    before = json.loads((bull_dir / "status.json").read_text())
    rebuilt = run(["bull", "status", "init-modules", "--replace"], root, check=False)
    after = json.loads((bull_dir / "status.json").read_text())
    if rebuilt.returncode != 0:
        warn.append(
            "bull can't rebuild the modules from docs/outline.md; kept the converted list. "
            "Fix the memo before the next /bull:feature:\n    "
            + (rebuilt.stderr or rebuilt.stdout).strip().replace("\n", "\n    ")
        )
    elif progress(after) != progress(before):
        (bull_dir / "status.json").write_text(
            json.dumps(before, indent=2, sort_keys=True) + "\n"
        )
        lost = sorted(set(progress(before).items()) ^ set(progress(after).items()))
        names = sorted({name for name, _ in lost})
        warn.append(
            "the memo's modules/units differ from v1's status for: "
            + ", ".join(names)
            + "; kept the converted list (check the memo's Files: lines)"
        )

    # 4. remove v1.
    claude_md = root / "CLAUDE.md"
    if claude_md.is_file():
        claude_md.write_text(clean_claude_md(claude_md.read_text()))
    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        data = clean_settings(json.loads(settings.read_text()))
        settings.write_text(json.dumps(data, indent=2) + "\n")
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        gitignore.write_text(clean_gitignore(gitignore.read_text()))
    run(
        ["git", "rm", "-r", "--quiet", "--cached", "--ignore-unmatch", ".pipeline"],
        root,
    )
    shutil.rmtree(v1_dir)

    # 5. commit, then relink (bull's CLAUDE.md block, .claude/settings.json, .gitignore).
    run(["git", "add", "-A"], root)
    run(["git", "commit", "--quiet", "-m", COMMIT_MESSAGE], root)
    run(["bull", "init", "."], root)

    for w in warn:
        print(f"  note: {w}")
    print("  " + run(["bull", "status"], root).stdout.strip().replace("\n", "\n  "))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("apps", nargs="+", type=Path, help="app folders to migrate")
    parser.add_argument(
        "--apply", action="store_true", help="migrate (default: dry run)"
    )
    parser.add_argument(
        "--any-branch",
        action="store_true",
        help="allow a branch other than the base branch",
    )
    args = parser.parse_args()
    if shutil.which("bull") is None:
        print("bull is not on PATH", file=sys.stderr)
        return 2
    failed = 0
    for app in args.apps:
        print(f"{app}:")
        try:
            migrate(app, args.apply, args.any_branch)
        except Stop as stop:
            failed += 1
            print(f"  STOPPED: {stop}")
            if args.apply and (app / ".bull").exists() and (app / ".pipeline").exists():
                print("  half-migrated; the tree was clean before, so undo with:")
                print(
                    f"    git -C {shlex.quote(str(app))} checkout -- . && rm -rf "
                    f"{shlex.quote(str(app / '.bull'))}"
                )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
