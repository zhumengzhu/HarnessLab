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
uv run harnesslab "list files in this workspace"
uv run pytest
```

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

