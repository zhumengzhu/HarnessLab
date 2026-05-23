# HarnessLab

HarnessLab is a learning-first agent harness project.

## Goals

- Build a clear and minimal agentic loop.
- Support sandboxed tool use with policy checks.
- Keep session and memory boundaries explicit.
- Make behavior observable and testable from day one.

## Tech Stack

- Python 3.11+
- `uv` for dependency and environment management
- `pytest` for tests

## Quick Start

```bash
cd /Users/zmz/Github/HarnessLab
uv sync
uv run pre-commit install   # one-time: enables local quality-gate hook
uv run harnesslab run "list files in this workspace"
uv run pytest
```

The CLI exposes two subcommands:

- `harnesslab run <input>` — run one turn of the loop.
- `harnesslab eval` — run the YAML eval suite (see below).

Run `harnesslab --help` for the full surface.

### Storage backends

By default `harnesslab run` uses in-memory session and memory stores
(state is lost when the process exits). To persist state across runs
use the SQLite backend:

```bash
uv run harnesslab run "hello" --storage sqlite
# default DB path: <workspace-root>/.harnesslab/state.sqlite

uv run harnesslab run "again" --storage sqlite \
    --sqlite-path ./my-runs/state.sqlite
```

The same Port contract suite (`tests/test_port_contracts.py`) runs
against both backends, so they are behaviorally interchangeable.

### Eval suite

`harnesslab eval` drives a small, versioned set of YAML tasks
(`eval/tasks/*.yaml`) against the live loop, then compares results to
`eval/baseline.json` and writes a JSON report to
`eval/reports/latest.json`.

```bash
# Run every task, compare against baseline, write the latest report.
uv run harnesslab eval

# Run a single task by filename stem.
uv run harnesslab eval --task 02_write_then_read

# Refresh the baseline after an intentional, reviewed behavior change.
uv run harnesslab eval --update-baseline
```

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | All tasks passed, no baseline regression. |
| 2 | At least one task failed (no baseline to compare against, or new failure not in baseline). |
| 3 | Baseline regression detected (was passing, now failing — or `tool_failures` / `invalid_args` increased). |
| 64 | Usage error (missing subcommand or unknown task). |

Each task declares its expected trace shape (ordered event subset,
forbidden event types, and `final_reply` substring), so the eval suite
doubles as living documentation of the loop's invariants.

## Quality Gate

Before every commit, both `uv run pytest` and `uv run ruff check` must
pass. This is enforced by the local pre-commit hook
(`.pre-commit-config.yaml`) and documented in `.cursor/rules/quality-gate.mdc`
for AI agents working on the repo.

## Project Layout

- `src/harnesslab/core`: contracts, domain models, agent loop
- `src/harnesslab/tools`: tool runtime and built-in tools
- `src/harnesslab/session`: session store
- `src/harnesslab/memory`: memory store
- `src/harnesslab/policy`: safety policy checks
- `src/harnesslab/telemetry`: trace models and recorder
- `docs/roadmap.md`: MVP-to-advanced roadmap

## Documentation

- `docs/roadmap.md`: roadmap from MVP to advanced capabilities
- `docs/architecture/overview.md`: architecture boundaries and runtime flow
- `docs/architecture/tool-runtime.md`: tool runtime and safety model
- `docs/architecture/data-model.md`: core runtime data contracts
- `docs/architecture/diagram-conventions.md`: Mermaid naming and style rules

