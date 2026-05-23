# HarnessLab

HarnessLab is a learning-first agent harness: a single-process runtime with
a multi-step agent loop, policy-gated tools, composed prompts, persistent
sessions, and JSONL traces for eval and replay.

## Goals

- Build a clear, autonomous agentic loop (model decides when to stop).
- Support sandboxed tool use with policy checks.
- Keep session boundaries explicit; treat sessions as first-class entities.
- Make behavior observable and testable from day one.

## Tech Stack

- Python 3.11+
- `uv` for dependency and environment management
- `pytest` for tests

## Quick Start

```bash
uv sync
uv run pre-commit install   # one-time: enables local quality-gate hook
uv run harnesslab run "list files in this workspace"
uv run pytest
```

The CLI exposes eight subcommands:

- `harnesslab run <input>` — start a session and run the agent loop
  (multi-step by default; see `--max-steps`).
- `harnesslab eval` — run the YAML eval suite.
- `harnesslab replay <trace.jsonl>` — re-drive a recorded trace and
  report any divergence.
- `harnesslab metrics <trace.jsonl>` — aggregate counts, latency, and
  context usage from a recorded trace.
- `harnesslab propose` — turn recurring failure clusters in traces
  and eval runs into advisory improvement proposals.
- `harnesslab session` — list, inspect, resume, or fork persisted
  sessions (SQLite).
- `harnesslab context <trace.jsonl>` — inspect per-call context
  snapshots from `model_call` events.
- `harnesslab serve` — local Web chat UI (localhost only).

Run `harnesslab --help` for the full surface.

### Agent loop (`run`)

Each `harnesslab run` invocation starts a new session and drives
`run_session`: the model may call tools repeatedly until it returns a
terminal decision (`final` — done, or `ask_user` — pause for input) or
hits the step budget.

```bash
# Default: up to 20 inner steps per user message.
uv run harnesslab run "find all Python files and summarize structure"

# Cap the inner loop for testing or cost control.
uv run harnesslab run "hello" --max-steps 3
```

Built-in tools: `read_file`, `write_file`, `edit_file`, `grep`, `glob`,
`run_shell_safe`. See `docs/architecture/tool-runtime.md` for policy
details.

### Web chat UI (`serve`)

```bash
export DEEPSEEK_API_KEY="***"   # required for default --model deepseek
uv run harnesslab serve --workspace-root .
# open http://127.0.0.1:8787/
```

The browser UI shares the SQLite session store with the CLI — sessions
created in the web UI appear in `harnesslab session ls`, and vice versa.
When using DeepSeek, session titles in the sidebar are auto-generated
after the first message (short LLM call, low token; falls back silently).

Use `--model simple` for offline smoke tests without network access.
Only `127.0.0.1` is allowed; the server refuses public bind addresses.

### Model backends (`run`)

`harnesslab run` supports two model backends:

- `--model simple` (default): deterministic local parser model (no network).
- `--model deepseek`: calls DeepSeek Chat Completions (networked).

DeepSeek requires `DEEPSEEK_API_KEY` in the environment.

```bash
export DEEPSEEK_API_KEY="***"
uv run harnesslab run "summarize current workspace safety posture" --model deepseek
```

Optional env overrides:

- `DEEPSEEK_BASE_URL` (default: `https://api.deepseek.com/v1`)
- `DEEPSEEK_MODEL` (default: `deepseek-chat`)

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

### Session management

When using SQLite storage, sessions persist across process restarts.
Use the `session` subcommand to inspect and continue work:

```bash
# List recent sessions (newest first).
uv run harnesslab session --workspace-root . ls

# Show metadata and conversation for one session.
uv run harnesslab session --workspace-root . show ses_abc123

# Continue a session with another user message.
uv run harnesslab session --workspace-root . resume ses_abc123 "keep going"

# Fork: copy messages into a new session with parent_session_id set.
uv run harnesslab session --workspace-root . fork ses_abc123 --goal "try alt approach"
```

Global flags (`--workspace-root`, `--sqlite-path`) must appear **before**
the subcommand: `harnesslab session --workspace-root . ls`.

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
doubles as living documentation of the loop's invariants. See
[`eval/README.md`](eval/README.md) for the propose→eval workflow and
task authoring guide (ten shipped tasks as of Phase 3.3).

### Replay, Metrics & Context

Every `harnesslab run` invocation appends to
`<workspace>/.harnesslab/trace.jsonl`. Read-only tools turn that file
into evidence:

```bash
# Re-drive the recorded loop and report any divergence per session.
uv run harnesslab replay .harnesslab/trace.jsonl

# When a session depends on files written by an earlier session, replay
# in the same workspace so the round-trip can succeed.
uv run harnesslab replay .harnesslab/trace.jsonl --workspace .

# Compare byte-for-byte (only useful for traces produced by the
# FrozenClock + SeqIdProvider runtime, e.g. eval task traces).
uv run harnesslab replay eval-trace.jsonl --strict

# Restrict to one session id.
uv run harnesslab replay .harnesslab/trace.jsonl --session-id ses_abc123

# Telemetry aggregation (human-readable or JSON).
uv run harnesslab metrics .harnesslab/trace.jsonl
uv run harnesslab metrics .harnesslab/trace.jsonl --json

# Context window observability: peak usage and per-call snapshots.
uv run harnesslab context .harnesslab/trace.jsonl show
uv run harnesslab context .harnesslab/trace.jsonl series --limit 10
uv run harnesslab context .harnesslab/trace.jsonl show --json
```

`replay` exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Every session replayed and matched the original. |
| 2 | Trace is unreplayable (missing required events, malformed payload, or unknown `--session-id`). |
| 4 | At least one session diverged; details are printed per session. |

`metrics` always exits 0; it is an observation tool, not a gate.

Semantic divergence ignores: timestamps (`created_at`, `started_at`,
`ended_at`, `duration_ms`, `latency_ms`), id renaming (`ses_*`, `msg_*`, `tool_*`,
`run_*` are normalized to `<prefix>_NNN` in first-appearance order),
tool output text (`output_preview`, `output_size`,
`output_truncated`), model telemetry (`model_name`, `provider`,
`request_tokens`, `response_tokens`, `total_tokens`), and the Phase 2.6
`context` snapshot on `model_call` events — those reflect
provider/runtime variability rather than loop behavior.
Everything else — the sequence of event types, the tool name and args,
the policy decision, the `ok` / `error` outcome — must match.

### Improvement Proposals

When recurring failures show up in real traces or eval runs,
`harnesslab propose` turns them into advisory markdown proposals in
`proposals/`. Proposals are **never applied automatically**; see
`AGENTS.md` "Proposal Handling" for the binding contract.

```bash
# Mine a production trace for failure clusters.
uv run harnesslab propose --trace .harnesslab/trace.jsonl

# Combine trace + eval failures, write into a custom dir.
uv run harnesslab propose \
    --trace .harnesslab/trace.jsonl \
    --eval-report eval/reports/latest.json \
    --out proposals/

# Single events do not warrant a proposal. Default min-occurrences is 2.
uv run harnesslab propose --trace .harnesslab/trace.jsonl --min-occurrences 3

# Non-destructive preview (JSON to stdout, no files written).
uv run harnesslab propose --trace .harnesslab/trace.jsonl --format json
```

Each proposal file (`prop_<YYYYMMDDhhmm>_<sig8>.md`) has YAML
front-matter (id, status, kind, cluster_signature, occurrences,
generated_at, related_files) plus body sections including an
**Acceptance checklist** that requires:

- Human review
- `uv run pytest` green
- `uv run harnesslab eval` showing no baseline regression
- A new or updated test if code changed

The generator dedupes against any signature with an `open` proposal
on disk, so re-running `propose` is safe and idempotent. To clear a
proposal, edit its front-matter `status` to `accepted` / `rejected` /
`superseded` in a reviewed commit.

`harnesslab propose` always exits 0 — it is a discovery tool, not a
gate. The gate is `harnesslab eval`, enforced by the checklist on
every proposal.

## Quality Gate

Before every commit, both `uv run pytest` and `uv run ruff check` must
pass. This is enforced by the local pre-commit hook
(`.pre-commit-config.yaml`) and documented in `.cursor/rules/quality-gate.mdc`
for AI agents working on the repo.

## Project Layout

- `src/harnesslab/core`: contracts, domain models, agent loop; `prompt/`,
  `compaction.py`, `context.py`
- `src/harnesslab/tools`: tool registry and built-in tools
- `src/harnesslab/policy`: safety policy checks
- `src/harnesslab/session`: session store (in-memory + SQLite)
- `src/harnesslab/memory`: memory store (persistence only; no loop
  writeback yet)
- `src/harnesslab/telemetry`: JSONL trace recorder and metrics aggregation
- `src/harnesslab/providers`: `ModelPort` adapters (DeepSeek)
- `src/harnesslab/eval`: YAML task suite and regression runner
- `src/harnesslab/replay`: trace reader, replayer, divergence detector
- `src/harnesslab/improve`: advisory proposal generator
- `eval/`: shipped tasks, baseline, reports
- `docs/`: roadmap and architecture documentation

## Documentation

- `AGENTS.md`: binding guidelines for AI agents and contributors
- `docs/roadmap.md`: MVP steps and Post-MVP phases (Phase 2 complete)
- `docs/architecture/overview.md`: architecture boundaries and runtime flow
- `docs/architecture/tool-runtime.md`: tool runtime and safety model
- `docs/architecture/data-model.md`: core runtime data contracts
- `docs/architecture/diagram-conventions.md`: Mermaid naming and style rules

