"""`bull help`: the command list grouped as in the Commands table."""

from __future__ import annotations

# One group per row of the Commands table, in its order: (usage lines, what the row does).
# Continuation lines are written in full (`bull <command> …`) so every line names its command.
_ROWS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("bull init [path] [--adopt] [--stack]",),
        "New app, relink, adoption start, or stack repo",
    ),
    (
        ("bull open [path] [--print-command] [-- <provider args>]",),
        "Render the plugin and launch the coding agent",
    ),
    (("bull doctor [--json]",), "Check the install and the toolchains"),
    (
        (
            "bull status [--json]",
            "bull status next | stage <n> | checkpoint <name> | init-modules [--replace]",
            "bull status module <M> <state> | unit <M> <n> <state> | attempt <M> <n>",
            'bull status unblock <M> <n> | pause "<reason>" | resume',
            'bull status wait <M> "<what>" | approve <M> "<note>"',
            "bull status refscan <M> --covered n --missed n --contradicts n --not-in-spec n",
            "bull status plan <label> <item>... | plan <label> --clear | tick <item>",
            "bull status ref trunk|base|module <M>|tag <label> | tags [--json]",
        ),
        "Pipeline state",
    ),
    (("bull status usage-check [--json]",), "Usage verdict: OK / PAUSE / UNKNOWN"),
    (
        (
            'bull feature add "<Title>: <desc>" [--top]',
            "bull feature import <file> [--section <heading>] [--dry-run]",
            "bull feature list [--json] | move <slug> <pos> | drop <slug>",
            "bull feature start [<slug>] | plan | accept | abandon",
        ),
        "Backlog and feature cycle",
    ),
    (("bull adopt start | legacy [--json] | finish | abandon",), "Adoption"),
    (
        ("bull stack detect [--apply [<stack>]] [--json]",),
        "Detection report for an existing project",
    ),
    (
        (
            "bull gates <M> [--fast | --coverage-report | --skip-coverage] [--json]",
            "bull gates --failed | --all [--skip-coverage] | --after-merge <branch> | --journeys",
        ),
        "Gates",
    ),
    (("bull coverage <M> [--json]",), "Coverage triage report from the last full run"),
    (
        (
            'bull api <M> [--write [--approved "<note>"]] [--check]',
            "bull api --interface <Name> [...]",
        ),
        "Contract snapshots",
    ),
    (
        (
            "bull stacks [--all] [--json]",
            "bull stack select <name> | rules <agent> [--part p]",
            "bull stack setup [--section s] [--part p] | check [--part p] [--json]",
            "bull stack run <command> [--part p] | install <path>",
        ),
        "Stacks",
    ),
    (
        ("bull stack test <name|path> [--static] [--case <id>] [--json]",),
        "Stack self-test",
    ),
    (
        ("bull part add <name> <stack> [--dir <folder>] | list [--json] | check",),
        "Parts",
    ),
    (
        (
            "bull config show [--part p] [--json]",
            "bull config set <key> <value> [--user | --part p]",
        ),
        "Settings",
    ),
    (("bull migrate",), "Upgrade the app's files to the current format"),
    (("bull template outline|backlog|design",), "Print a template"),
    (
        (
            "bull hook session-start|before-agent|before-shell|before-edit|before-read|agent-end",
        ),
        "Hook entry points (input on stdin from the provider)",
    ),
    (("bull statusline",), "Status line: record usage, print the line"),
    (("bull help | bull --version",), "This list; the version"),
)

_HEADER = (
    "Usage: bull <command> [options]\n"
    "Every command takes --help; the ones marked [--json] can print JSON.\n"
    "\n"
    "Commands:\n"
)


def render_help() -> str:
    """The command list, one group per row of the Commands table, in its order."""
    blocks: list[str] = []
    for lines, does in _ROWS:
        block = [f"  {line}" for line in lines]
        block.append(f"      {does}")
        blocks.append("\n".join(block))
    return _HEADER + "\n".join(blocks) + "\n"
