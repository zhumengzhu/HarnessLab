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

## Provider Layer (Post-MVP)

External LLMs are integrated only via `ModelPort` adapters under
`src/harnesslab/providers/`.

Rules:

1. Keep `ModelPort` stable; do not leak provider-specific response
   shapes into `core`.
2. `harnesslab run` may use non-deterministic providers (e.g.
   DeepSeek), but `eval` / `replay` paths must remain deterministic.
3. Provider secrets come from environment variables; never commit keys
   or key-like fixtures.
4. Provider failures must degrade to normalized assistant responses, not
   unhandled exceptions that break the loop.
5. Provider telemetry belongs in `model_call` trace payload; treat
   token counters/model names as volatile in semantic replay compare.

## Proposal Handling

HarnessLab generates improvement proposals via `harnesslab propose`.
Proposals live under `proposals/` as markdown files with YAML
front-matter (`id`, `status`, `kind`, `cluster_signature`,
`occurrences`, `generated_at`, `related_files`).

The following rules are **binding** for every AI agent (including the
one editing this repo) and every human contributor.

1. **Proposals are advisory.**
   - AI agents MUST NOT automatically apply a proposal's suggested
     actions, even when the suggestion looks safe.
   - AI agents MAY draft a code change that addresses an `open`
     proposal, but the change is a normal PR and remains subject to
     the project's standard quality gate.

2. **Status transitions are human-driven.**
   - A proposal moves from `status: open` to `accepted` only after
     ALL of:
     - (a) a human reviewed the proposal and the proposed code change,
     - (b) `uv run pytest` is green,
     - (c) `uv run harnesslab eval` shows no baseline regression.
   - A proposal moves to `rejected` requires a `## Decision` section
     stating the reason; the cluster_signature stays on file so future
     `propose` runs do not keep raising the same dead-end suggestion.
   - A proposal moves to `superseded` requires a link to the
     replacement proposal id in the body.

3. **Commit hygiene.**
   - When a commit addresses an open proposal, the commit message
     SHOULD reference the proposal id (e.g.
     `Addresses prop_2026_05_23_a3f2c1`).
   - The proposal file's `status:` SHOULD be updated to `accepted` in
     the same commit (or the immediately following commit when split).
   - Never edit a proposal's `cluster_signature`, `occurrences`, or
     `generated_at` by hand; those reflect the input data and are
     diagnostic, not policy.

4. **Generator behavior is stable.**
   - Default `--min-occurrences` is 2. Single events do not warrant a
     proposal.
   - Identical `cluster_signature` is deduped against any `open`
     proposal on disk; `accepted` / `rejected` / `superseded` proposals
     do not block re-emission so recurring problems stay surfaced.
   - The proposal id is `prop_<YYYYMMDDhhmm>_<sha1(signature)[:8]>`,
     stable for a given (signature, generated_at minute).

5. **No LLM in the proposal pipeline.**
   - `suggested_actions` come from hand-written templates keyed by
     cluster kind (`src/harnesslab/improve/templates.py`).
   - Do not wire an LLM call into the proposal generator without first
     updating this section, `docs/architecture/overview.md` Improvement
     Loop, and the Non-Goals in the same change.

## Prohibited Practices

- Hidden side effects in core loop logic
- Direct infrastructure calls that bypass adapters/contracts
- Untested behavior changes in policy or tool runtime
- Silent changes to data model fields without doc updates
- Auto-applying improvement proposals (see "Proposal Handling" above)

