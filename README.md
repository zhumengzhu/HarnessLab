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

The CLI exposes five subcommands:

- `harnesslab run <input>` — run one turn of the loop.
- `harnesslab eval` — run the YAML eval suite.
- `harnesslab replay <trace.jsonl>` — re-drive a recorded trace and
  report any divergence.
- `harnesslab metrics <trace.jsonl>` — aggregate counts and latency
  from a recorded trace.
- `harnesslab propose` — turn recurring failure clusters in traces
  and eval runs into advisory improvement proposals.

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

### Replay & Metrics

Every `harnesslab run` invocation appends to
`<workspace>/.harnesslab/trace.jsonl`. Two read-only tools turn that
file into evidence:

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
```

`replay` exit codes:

| Code | Meaning |
| --- | --- |
| 0 | Every session replayed and matched the original. |
| 2 | Trace is unreplayable (missing required events, malformed payload, or unknown `--session-id`). |
| 4 | At least one session diverged; details are printed per session. |

`metrics` always exits 0; it is an observation tool, not a gate.

Semantic divergence ignores: timestamps (`created_at`, `started_at`,
`ended_at`, `duration_ms`), id renaming (`ses_*`, `msg_*`, `tool_*`,
`run_*` are normalized to `<prefix>_NNN` in first-appearance order),
and tool output text (`output_preview`, `output_size`,
`output_truncated`) because those reflect IO side effects rather than
loop behavior. Everything else — the sequence of event types, the
tool name and args, the policy decision, the `ok` / `error` outcome —
must match.

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

