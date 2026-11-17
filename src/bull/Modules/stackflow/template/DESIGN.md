# Stack design

Fill each section during the design discussion (stage 1). When the human approves this file, run
`bull status checkpoint design-approved`. Progress is tracked in `.bull/status.json`, not here.

## Language and tools

The language, its version, and the tools the gates run: build, test runner, coverage, linter,
formatter, type checker. Which tools must be installed (`[[stack.requires]]` in `stack.toml`).

## Contracts

Where a module's contract lives, which declarations count as contract, and how the contract
scanner lists them (`readers.py` `contract_declarations`).

## Modules

How a module maps to folders: source and test paths, mocks, file naming, and the `source_glob`
and `test_glob` patterns.

## Kind

`app`, `service` or `tool`, and what that means for journeys: how journey tests drive the built
product.

## Human setup

The manual steps a person does once per app before the skeleton (`setup.md`), and what
`bull stack check` verifies afterwards.

## Adoption support

Whether the stack can adopt an existing project: how `detect` recognises one, what the baseline
needs, and the final switch to full strictness. Write "none" if adoption is not supported.

## Interfaces and running

Interface formats the stack reads (`[interfaces]`), and for a service: how it starts, how bull
knows it is ready, and how it stops (`[run]`). Write "none" for parts that don't apply.

## Decisions log

- <date>: <decision> — <why>
