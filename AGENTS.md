# HarnessLab Agent Guidelines

## Mission

HarnessLab is a learning-first agent harness project.

Primary objective:

- Build a clear, minimal, and testable agentic runtime.

Secondary objective:

- Keep architecture and contracts stable enough for future Python -> TypeScript migration.

## Current Phase

Current phase is MVP.

Must include:

- Single-process runtime
- One-turn loop plus session updates
- Policy-gated tool execution
- Trace recording
- Unit tests

Must NOT include yet:

- Multi-agent orchestration
- Distributed runtime
- Plugin marketplace complexity
- Uncontrolled self-modifying pipelines

## Repository Structure Ownership

- `src/harnesslab/core`: loop orchestration, contracts, core models
- `src/harnesslab/tools`: tool registry and tool implementations
- `src/harnesslab/policy`: safety and authorization checks
- `src/harnesslab/session`: session persistence layer
- `src/harnesslab/memory`: memory persistence layer
- `src/harnesslab/telemetry`: trace and telemetry outputs
- `tests`: unit and contract tests
- `docs`: roadmap and architecture documentation

## Architectural Rules

1. Keep contract boundaries explicit.
2. Prefer ports-and-adapters over direct coupling.
3. Enforce policy checks before all tool execution.
4. Keep loop behavior deterministic where practical.
5. Record key runtime actions with trace events.

Stable contract names:

- `ModelPort`
- `PolicyPort`
- `ToolPort`
- `SessionStorePort`
- `MemoryStorePort`
- `TraceRecorderPort`

If a contract changes, update docs and tests in the same change.

## Safety and Tooling Rules

- Deny unknown tools by default.
- Deny out-of-workspace file paths.
- Restrict shell execution to allowlisted commands.
- Enforce shell timeouts and bounded output.
- Keep tool output normalized (`ok`, `output`, optional `error`).

Never bypass policy checks for convenience.

## Testing and Quality Gate

Before completing non-trivial changes, run:

```bash
uv run pytest
uv run ruff check
```

For architecture-affecting changes:

- Add or update tests for changed behavior.
- Update relevant docs under `docs/`.

## Documentation Rules

Core docs:

- `docs/roadmap.md`
- `docs/architecture/overview.md`
- `docs/architecture/tool-runtime.md`
- `docs/architecture/data-model.md`
- `docs/architecture/diagram-conventions.md`

Mermaid diagrams must follow `docs/architecture/diagram-conventions.md`.

When behavior changes, keep docs synchronized in the same PR.

## Change Discipline

- Keep changes small and atomic.
- Avoid broad refactors without test coverage.
- Do not introduce new dependencies without clear need.
- Preserve naming consistency across code, docs, and diagrams.

## Prohibited Practices

- Hidden side effects in core loop logic
- Direct infrastructure calls that bypass adapters/contracts
- Untested behavior changes in policy or tool runtime
- Silent changes to data model fields without doc updates

