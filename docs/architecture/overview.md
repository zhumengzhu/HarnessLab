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
7. `eval` (planned)
   - Task suites, pass rate tracking, and regression gating

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

## Planned Evolution

1. Replace in-memory stores with SQLite-backed stores
2. Add deterministic replay from traces
3. Add evaluation task sets and baseline diffing
4. Introduce metrics dashboards or reports
5. Add guarded self-improvement proposal pipeline
