# HarnessLab Architecture Overview

## Purpose

HarnessLab is a learning-focused agent harness that emphasizes clear boundaries,
safe tool execution, and reproducible behavior.

The project starts with a local single-process runtime and evolves toward
stronger observability and automated improvement workflows.

## System Map

```mermaid
flowchart TD
    UserInput[User Input] --> CoreLoop[Core Loop]
    CoreLoop --> ModelPort[Model Port]
    ModelPort --> Decision{Decision}
    Decision -->|assistant| AssistantReply[Assistant Reply]
    Decision -->|tool| PolicyPort[Policy Port]
    PolicyPort -->|allow| ToolRuntime[Tool Runtime]
    PolicyPort -->|deny| DeniedReply[Denied Reply]
    ToolRuntime --> SessionStore[Session Store]
    AssistantReply --> SessionStore
    DeniedReply --> SessionStore
    ToolRuntime --> TraceRecorder[Trace Recorder]
    AssistantReply --> TraceRecorder
    DeniedReply --> TraceRecorder
```

## Goals

- Build a minimal but complete agentic loop
- Keep tool execution policy-driven and auditable
- Make session and memory explicit, not implicit
- Keep components replaceable to support future migration (Python -> TypeScript)
- Preserve deterministic evaluation and regression checks

## Non-Goals (MVP)

- Multi-agent orchestration
- Distributed execution
- Runtime plugin marketplace
- Fully automated self-modifying code paths

## Layered Architecture

1. `core`
   - Loop orchestration, state transitions, and contracts
   - Decides assistant reply vs tool call
2. `policy`
   - Authorization checks before tool execution
   - Path and command validation
3. `tools`
   - Tool registry and concrete tool implementations
   - File and shell adapters behind stable interfaces
4. `session`
   - Conversation state lifecycle
   - Session identifiers and message timelines
5. `memory`
   - Long-lived records beyond one turn/session
   - Retrieval and writeback policy boundary
6. `telemetry`
   - Structured traces, run events, and replay-friendly artifacts
7. `eval`
   - YAML task suites, pass rate tracking, and regression gating
   - `harnesslab eval` CLI subcommand; baseline JSON in-repo
8. `replay`
   - Trace reader, deterministic session replayer, divergence detector
   - `harnesslab replay` / `harnesslab metrics` CLI subcommands
9. `improve`
   - Failure fingerprinting, clustering, advisory proposal generation
   - `harnesslab propose` CLI subcommand; proposals committed under
     `proposals/` with explicit accept/reject lifecycle
10. `providers`
   - External `ModelPort` adapters (e.g. DeepSeek)
   - Runtime-selectable backend for `harnesslab run --model ...`

## Runtime Flow (Single Turn)

1. Receive user input
2. Append a user message to the session
3. Model decides:
   - assistant response, or
   - tool invocation
4. Policy validates the tool call
5. Tool executes (or is denied)
6. Result is recorded to session + trace
7. Assistant-visible output is returned

```mermaid
sequenceDiagram
    participant User
    participant CoreLoop as Core Loop
    participant ModelPort as Model Port
    participant PolicyPort as Policy Port
    participant ToolRuntime as Tool Runtime
    participant SessionStore as Session Store
    participant TraceRecorder as Trace Recorder

    User->>CoreLoop: user_input
    CoreLoop->>SessionStore: append user message
    CoreLoop->>ModelPort: decide(session, input)
    ModelPort-->>CoreLoop: assistant or tool decision
    alt assistant response
        CoreLoop->>SessionStore: append assistant message
        CoreLoop->>TraceRecorder: record decision + response
        CoreLoop-->>User: assistant response
    else tool call
        CoreLoop->>PolicyPort: allow_tool(call)
        alt denied
            CoreLoop->>SessionStore: append tool message (denied)
            CoreLoop->>TraceRecorder: record tool_denied
            CoreLoop-->>User: denied response
        else allowed
            CoreLoop->>ToolRuntime: execute(call)
            ToolRuntime-->>CoreLoop: tool result
            CoreLoop->>SessionStore: append tool message
            CoreLoop->>TraceRecorder: record tool_executed
            CoreLoop-->>User: tool result message
        end
    end
```

Diagram style and naming rules are defined in
`docs/architecture/diagram-conventions.md`.

## Stability Boundaries

The following contracts should remain stable across implementations:

- `ModelPort`
- `PolicyPort`
- `ToolPort`
- `SessionStorePort`
- `MemoryStorePort`
- `TraceRecorderPort`
- `ClockPort`
- `IdPort`

`ClockPort` and `IdPort` are non-negotiable for deterministic replay: the loop
must obtain every timestamp and every entity ID from them, never directly from
`datetime.now()` or `uuid4()` at call sites.

All infrastructure details (storage engine, model provider, runtime language)
should be replaceable behind these contracts.

## Architecture Decisions (Current)

- Single process runtime for fast iteration
- JSONL trace output for transparent debugging
- Policy-first tool execution (deny by default for unknown tools)
- Small built-in tool surface in MVP (`read_file`, `write_file`, `run_shell_safe`)
- Deterministic core via injected `ClockPort` and `IdPort` (replay-ready by construction)
- Shell tool runs argv with `shell=False`; policy bans shell metacharacters
- `ToolRegistry` normalizes both "unknown tool" and tool exceptions into
  `ToolResult(ok=False)` so the loop only sees the normalized result shape
- Trace is the source of truth for replay: `user_input_received` plus a
  full `decision_made` payload (`kind`, `tool_name`, `tool_args`,
  `assistant_message`) is sufficient to rebuild a `ReplayModel` without
  consulting the original Session or model
- Model invocation is now auditable via `model_call` trace events
  (decision kind, latency, and optional token counters/provider meta)

## Replay & Divergence Model (Step 5)

The replayer takes a JSONL trace, extracts `(user_input, Decision)` pairs
from each session, and drives the production loop with `ReplayModel`
backed by those decisions plus `FrozenClock` + `SeqIdProvider`. The new
trace is then compared to the original by `detect_divergence`.

```mermaid
flowchart TD
    JSONL[trace.jsonl] --> Reader[trace_reader.read_trace]
    Reader --> Grouped[group_by_session]
    Grouped --> Extract[extract user_input + Decision pairs]
    Extract --> ReplayModel
    ReplayModel --> Loop[HarnessLoop with FrozenClock + SeqIdProvider]
    Loop --> NewTrace[New TraceEvent list]
    NewTrace --> Divergence[detect_divergence]
    Grouped --> Divergence
    Divergence --> Report[DivergenceReport]
```

Two comparison modes:

- **Semantic (default).** Normalizes prefix ids (`ses_*`, `msg_*`,
  `tool_*`, `run_*`) to `<prefix>_NNN` in first-appearance order, and
  scrubs volatile fields: timestamps (`created_at`, `started_at`,
  `ended_at`, `duration_ms`, `latency_ms`), tool output text
  (`output_preview`, `output_size`, `output_truncated`), and provider
  telemetry (`model_name`, `provider`, `request_tokens`,
  `response_tokens`, `total_tokens`). What remains — event order, event
  types, tool name, args, policy decision, `ok` / `error` — must match
  exactly. This is the right mode for any trace produced by `SystemClock`
  + `UuidIdProvider`.
- **Strict.** No normalization; byte-for-byte comparison. Only sensible
  for traces already produced by `FrozenClock` + `SeqIdProvider`
  (e.g. eval task traces).

Unreplayable traces raise `UnreplayableTraceError` early: missing
`session_started`, dangling `user_input_received` without a paired
`decision_made`, or a `decision_made` payload that fails to validate as
a `Decision`. The CLI surfaces this as exit code 2.

## Improvement Loop (Step 6)

The proposal generator mines failures from two sources and turns
recurring clusters into advisory markdown files. Nothing is ever
applied automatically; humans review and accept each proposal under
the gate of `harnesslab eval` + `pytest`.

```mermaid
flowchart TD
    Trace[trace.jsonl] --> Fingerprint
    EvalReport[eval/reports/latest.json] --> Fingerprint
    Fingerprint --> Cluster[build_clusters --min-occurrences=N]
    Cluster --> Generator[generate -> Proposal]
    Generator --> Dedupe[dedupe_against_existing open proposals]
    Dedupe --> Render[markdown with YAML front-matter]
    Render --> ProposalsDir[proposals/prop_*.md status=open]
    ProposalsDir --> HumanReview{Human review}
    HumanReview -->|accept| Gate[uv run harnesslab eval + pytest]
    Gate -->|green| Accepted[status: accepted]
    HumanReview -->|reject| Rejected[status: rejected with reason]
```

Failure signal sources and their fingerprint shapes:

| Source | Trigger | Fingerprint |
| --- | --- | --- |
| trace | `tool_executed.ok=false` | `tool_executed:<tool>:<short_error>` |
| trace | `tool_denied` | `tool_denied:<tool>:<short_reason>` |
| trace | `tool_invalid_args` | `tool_invalid_args:<tool>:<short_error>` |
| eval report | `TaskResult.passed=false` | `eval:<task_name>:<short_failure>` |

`replay` divergences are intentionally **not** failure signals;
divergence may reflect IO state changes (workspace contents) rather
than loop misbehavior. If a divergence reflects a real regression the
right place to encode it is a new eval task.

Suggested-action text is generated from hand-written templates keyed
by cluster `kind`. The project does not call an LLM here:

- It would add a network and credential dependency that the rest of
  the runtime carefully avoids.
- It would obscure the contract that proposals are deterministic
  artifacts of `(trace, eval_report)` plus version-pinned templates.
- It would muddy the AGENTS.md guarantee that proposals are advisory
  and never self-modify the codebase.

## Provider Integration (Post-MVP Phase 1)

`ModelPort` remains the stable contract. Concrete providers now live
under `src/harnesslab/providers/`:

- `SimpleModel`: deterministic parser model for eval/replay and offline
  workflows.
- `DeepSeekModel`: networked provider for `harnesslab run --model deepseek`.

This split keeps deterministic quality gates intact:

- `run --model deepseek` can be non-deterministic by design.
- `eval`, `replay`, and contract tests continue to rely on deterministic
  clocks/ids/models so baseline and divergence behavior stay stable.

## Planned Evolution

1. Replace in-memory stores with SQLite-backed stores — DONE (Step 3)
2. Add deterministic replay from traces — DONE (Step 5)
3. Add evaluation task sets and baseline diffing — DONE (Step 4)
4. Introduce metrics dashboards or reports — partial (Step 5: CLI
   aggregation; dashboards remain future work)
5. Add guarded self-improvement proposal pipeline — DONE (Step 6,
   advisory-only by AGENTS.md contract)
