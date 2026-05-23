# HarnessLab Dev Quick Guide

## What This Project Is

HarnessLab is a learning-first agent harness.

Current focus: a clean MVP with stable interfaces, safe tools, and repeatable tests.

## Daily Priorities

1. Keep the loop simple and deterministic.
2. Run tool calls only through policy checks.
3. Preserve contract boundaries.
4. Keep docs and tests in sync with behavior changes.

## MVP Boundaries

Allowed now:

- Single-process runtime
- Session updates and trace recording
- Policy-gated file and shell tools
- Unit tests and basic lint checks

Not now:

- Multi-agent orchestration
- Distributed runtime
- Large plugin systems

## Contract Names (Do Not Drift)

- `ModelPort`
- `PolicyPort`
- `ToolPort`
- `SessionStorePort`
- `MemoryStorePort`
- `TraceRecorderPort`

If you change a contract, update tests and docs in the same change.

## Safety Rules

- Deny unknown tools by default.
- Deny paths outside workspace root.
- Allowlist shell commands.
- Enforce timeout and output caps for shell.

Do not bypass policy checks.

## Must-Run Commands

```bash
uv run pytest
uv run ruff check
```

## Docs to Keep Updated

- `docs/roadmap.md`
- `docs/architecture/overview.md`
- `docs/architecture/tool-runtime.md`
- `docs/architecture/data-model.md`
- `docs/architecture/diagram-conventions.md`

Use Mermaid style and naming rules from `diagram-conventions.md`.

