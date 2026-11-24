# The Bull

The Bull lets [Claude Code](https://claude.com/claude-code) build and extend apps through a
disciplined, test-first, staged process. It is a Python command (`bull`) plus a Claude Code plugin
(`/bull:*` commands, specialized subagents and hooks).

Claude Code works as the **orchestrator**: it talks with you, keeps the spec, and hands each piece of
work to a subagent with a narrow brief. Automated **gates** (build, tests, coverage, lint, contract
checks) decide when a piece is done, and you approve each **checkpoint**.

```
discuss → outline → setup → skeleton → prototype → modules → verify
```

1. **Discuss**: what the app is for, its user journeys, and its stack.
2. **Outline**: a memo (`docs/outline.md`) with the spec, modules, contracts and build order. You approve it.
3. **Setup**: the manual project steps for the stack, checked by `bull stack check`.
4. **Skeleton**: module folders, contracts, stubs and mocks that compile.
5. **Prototype**: the UI on mocks, for you to try and approve.
6. **Modules**: one module at a time. Tests are written from the spec first, then the code, then
   gates, review and coverage triage, then a merge.
7. **Verify**: one end-to-end test per user journey, a whole-app review, your own hands-on test, and
   acceptance.

After acceptance, `/bull:feature` adds features through the same stages on their own branch.
`/bull:adopt` brings an existing app under bull, one module at a time.


## Install

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), git and Claude Code. bull runs on macOS and
Linux.

```
uv tool install git+https://github.com/NyckJohnson/BullOfKrete
bull doctor
```

`bull doctor` checks the tools and reports which stacks' toolchains are missing.

## Quick start

```
bull init ~/apps/example      # new app folder, git repo and bull files
bull open ~/apps/example      # launches Claude Code with the bull plugin
```

In Claude Code, run `/bull:discuss`. bull tells you the next step at every point:
`bull status next` in the terminal, or the Claude Code status line. After a break, `/bull:resume`
picks up where you left off.

`bull help` lists every command; each one takes `--help`.

## Development

```
git clone https://github.com/NyckJohnson/BullOfKrete && cd BullOfKrete
uv sync
uv run pytest
```

The spec is `docs/outline.md`. Every module under `src/bull/Modules/` has its tests in `tests/`, and
`tests/journey/` runs the installed `bull` end to end.

## Stacks

Everything language- or platform-specific lives in a **stack**: a folder with a TOML manifest,
Python readers, rules for each agent, a setup guide and a self-test. Built-in stacks:

| Stack | Kind | Status |
| --- | --- | --- |
| `python_cli` | tool | experimental |
| `ios` | app | experimental (needs macOS and Xcode) |

`bull stacks --all` lists them all, including the test stacks. You can build new stacks with bull
itself (`bull init --stack`), and an app can have several parts, each on its own stack.

### Example: adding the Go language as a stack
```
mkdir -p ~/bullstacks                    # any parent folder you like
bull init --stack ~/bullstacks/go_cli    # creates go_cli/ as a stack repo
bull open ~/bullstacks/go_cli            # launches Claude Code in it

# in Claude Code:
/bull:stack                              # The Bull walks you through building the stack

# after /bull:stack finishes, back in a terminal:
bull stack install ~/bullstacks/go_cli   # runs the static self-test, then installs it for you
bull stacks                              # go_cli is now listed as experimental

# use it in a new app:
bull init ~/apps/example-go
bull open ~/apps/example-go              # then /bull:discuss; pick go_cli at setup
```

## License

MIT. See [LICENSE](LICENSE).
