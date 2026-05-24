# HarnessLab Agent Guidelines

## Mission

HarnessLab is a learning-first agent harness project.

Primary objective:

- Build a clear, minimal, and testable agentic runtime.

Secondary objective:

- Keep architecture and contracts stable enough for future Python -> TypeScript migration.

## Current Phase

MVP (Steps 1–6), Post-MVP Phase 2, and Phase 3–4 operator hardening are
**complete**. The runtime is a daily-usable local agent harness.

Must include (current):

- Single-process runtime
- Multi-step agent loop (`run_session` with `max_steps`; terminal decisions
  `final` / `ask_user`)
- Policy-gated tool execution (eight built-in tools; named shell profiles
  `dev` / `read_only` / `strict`; ``fetch_url`` host allowlist for wttr.in)
- Modular prompt composition (`PromptComposer` + static/dynamic blocks)
- Session as first-class citizen (persist, list, resume, fork)
- Session- and workspace-scoped memory (`/remember`, `/remember-global`)
- Automatic context compaction (threshold + overflow recovery)
- Per-call context observability (`ContextSnapshot` on `model_call`)
- Local Web chat UI (`harnesslab serve`, `./hl-serve`) with settings panel
  and tool result cards
- Optional LLM session auto-titles after first turn (DeepSeek only)
- Operator config (`~/.config/harnesslab/config.json`) + provider registry
- Trace recording, eval/replay/propose CLI, unit + contract tests
- DeepSeek provider (`deepseek-v4-flash` / `deepseek-v4-pro`) behind
  `ModelPort` for `harnesslab run --model deepseek`

Must NOT include yet:

- Vector RAG / semantic memory retrieval
- Multi-agent orchestration
- Distributed runtime
- Plugin marketplace complexity
- Uncontrolled self-modifying pipelines
- Official OpenAI/Anthropic SDK adapters (MVP uses `httpx`; migrate in
  post-MVP provider expansion)

## Agent Loop Contract (Phase 2)

- `HarnessLoop.run_session(session_id, user_input, max_steps=N)` is the
  primary entry point. `run_turn` is `run_session(..., max_steps=1)`.
- `Decision.kind` is one of `tool | assistant | final | ask_user`.
  Terminal kinds (`final`, `ask_user`) end the inner loop; `tool` and
  `assistant` continue until `max_steps` or a terminal decision.
- Before each model call the loop may compact older messages
  (`compaction_started` / `compaction_completed` trace events). Adapters
  raise `ModelOverflowError` on context overflow; the loop compacts once
  and retries.
- Provider adapters consume `PromptComposer` output — do not hardcode system
  prompts in `providers/` except via composer blocks.
- Session lifecycle fields (`status`, `step_count`, `last_step_at`,
  `parent_session_id`, `title`) are part of the data contract; update
  docs and SQLite migrations when they change.

## Repository Structure Ownership

- `src/harnesslab/core`: loop orchestration, contracts, core models;
  `core/prompt/` (composer + blocks), `core/compaction.py`,
  `core/context.py`
- `src/harnesslab/tools`: tool registry and built-in tool implementations
- `src/harnesslab/policy`: safety and authorization checks
- `src/harnesslab/session`: session persistence layer
- `src/harnesslab/memory`: memory persistence + session-scoped loop
  read/write (`core/memory_policy.py`)
- `src/harnesslab/telemetry`: trace recording and metrics aggregation
- `src/harnesslab/providers`: external `ModelPort` adapters (e.g. DeepSeek)
- `src/harnesslab/eval`: YAML task suite and regression runner
- `src/harnesslab/replay`: trace reader, replayer, divergence detector
- `src/harnesslab/improve`: advisory proposal generator
- `src/harnesslab/web`: localhost Web UI (`harnesslab serve`); lifecycle
  helper `./hl-serve` (`scripts/hl_serve.py`)
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
- `ClockPort`
- `IdPort`

If a contract changes, update docs and tests in the same change.

## Safety and Tooling Rules

- Deny unknown tools by default.
- Deny out-of-workspace file paths (`read_file`, `write_file`, `edit_file`
  require path; `grep` / `glob` allow optional path with same workspace check).
- Restrict shell execution to allowlisted commands; `git` requires a
  read-only subcommand from `SAFE_GIT_SUBCOMMANDS`.
- Enforce shell timeouts and bounded output.
- Keep tool output normalized (`ok`, `output`, optional `error`).
- The shell allowlist is not a sandbox against arbitrary code execution via
  `python` / `pytest` / `uv run` — workspace path checks remain primary.

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
5. Provider telemetry and `ContextSnapshot` belong in `model_call` trace
   payload; treat token counters, model names, and `context` as volatile
   in semantic replay compare.

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

