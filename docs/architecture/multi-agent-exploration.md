# Multi-Agent Exploration (Phase 6 RFC)

**Status:** Design / discussion. **Not approved for implementation.**

This RFC frames how HarnessLab might eventually support multi-agent
work without losing the single-process, single-trace, replayable
character that defines the project today.

It deliberately makes **no commitment to a specific runtime topology**;
the goal is to enumerate options, list the open questions, and propose
the smallest PoC that would yield a real product signal.

---

## 1. Motivation and the open question

The current loop is fundamentally **one agent, one session, one trace**.
That has been the right default through Phase 5 because it keeps:

- a single source of truth for what happened (`trace.jsonl`)
- a single replayable contract (`ReplayModel` + `FrozenClock`)
- a single policy boundary (`PolicyPort` between loop and tools)

But several real workloads stretch this shape uncomfortably:

| Workload | Single-loop pain point |
|----------|------------------------|
| **Deep research** (search → read → cross-check → write report) | One agent juggling 4 roles in 30+ steps loses focus; context compaction degrades the synthesis stage. |
| **Coding with review** | The same model "writes the change" and "reviews the change"; quality plateaus quickly. |
| **Long autonomous tasks** (e.g. eval triage runs) | A single loop cannot work on two failures in parallel even when they are independent. |
| **Tool specialization** | Some tools (browser, sandboxed python) benefit from a dedicated agent that holds context for that tool only. |

The question is not "should HarnessLab support multi-agent." It is:
**which product shape buys real value without dissolving the
properties we worked hard to keep?**

---

## 2. Candidate product shapes (industry survey)

We pick the shape **before** the implementation.

### 2.1 Pipeline / Workflow
A fixed DAG of specialized agents (`planner → researcher → writer`).
Closest commercial analogue: simple LangGraph / CrewAI flows, OpenAI
Swarm "handoff" patterns.

- **Pros:** predictable; trivially auditable; each stage is a small
  prompt; trivially deterministic for eval.
- **Cons:** rigid; cannot adapt graph shape per task; reads more like
  "workflow with LLM nodes" than "agentic behavior".
- **HarnessLab fit:** very high — maps onto a series of `run_session`
  calls glued by a thin driver; minimal Port changes.

### 2.2 Supervisor / Sub-agent
A "manager" agent spawns child agents for sub-tasks, gathers their
outputs, decides next step. Closest analogues: Anthropic Claude
sub-agents, LangGraph supervisor, OpenAI Agents SDK handoffs, Cursor's
"explore" subagent.

- **Pros:** dynamic; matches how humans delegate; sub-agent failure is
  contained; sub-agents can use restricted tool sets / policies.
- **Cons:** more state (parent + N children); more trace fan-in;
  cost-explosion risk if poorly bounded; replay determinism harder.
- **HarnessLab fit:** **high** — `Session.parent_session_id` already
  exists for `fork`. Reuse it for "spawn". `PolicyPort` already supports
  per-tool restrictions; per-child profiles map naturally.

### 2.3 Peer / Debate
Two or more agents critique each other's outputs (debate, reflexion,
self-consistency). Common in research.

- **Pros:** measured quality lift on some benchmarks.
- **Cons:** high token cost; convergence is fragile; little operator
  benefit in coding/research that already has human-in-the-loop.
- **HarnessLab fit:** medium — possible as an offline pattern, not a
  primary product shape.

### 2.4 Background / Asynchronous agents
Long-lived agents that watch a workspace, queue, or schedule and act
when triggered. Closest analogues: Cursor background agents, Devin,
Bugbot, GitHub copilot-workspace.

- **Pros:** unlocks "the agent did it while I slept" experiences;
  natural fit for proposal review / regression triage.
- **Cons:** distributed-system complexity (queues, locks, idle
  costs); the single-process AGENTS.md rule fails immediately.
- **HarnessLab fit:** **low for Phase 6**; revisit only if the local
  improvement loop genuinely outgrows a CLI invocation.

### 2.5 Worker pool / Auction
Many homogeneous workers compete for a queued task. Mostly relevant for
batch generation, not interactive work.

- **HarnessLab fit:** **out of scope.** Doesn't match the learning-first,
  observable-by-default ethos.

---

## 3. Recommended shape: **Supervisor + bounded sub-sessions (2.2)**

Among the five, **supervisor / sub-agent** is the only shape that:

- maps onto an existing Port (`SessionStorePort`,
  `Session.parent_session_id`) without inventing a new lifecycle,
- preserves a per-agent JSONL trace (each sub-session is just another
  session in the same store, with a parent ref),
- composes with Phase 5.3 `plan` mode (the plan becomes the spawn list),
- composes with Phase 5.4 MCP and Phase 5.5 Python sandbox (a
  sub-agent can hold the high-risk profile, the parent stays read-only),
- and lets eval / replay keep their current shape — each session is
  still independently replayable.

We deliberately **reject**:

- 2.1 Pipeline as the primary shape — too rigid; the value of agents is
  adaptive routing, not fixed graphs. (It can still be expressed as a
  supervisor with a hardcoded plan.)
- 2.4 Background agents — violates AGENTS.md single-process rule and
  introduces distributed-system concerns that the project explicitly
  defers.

---

## 4. How the recommended shape fits existing Ports

| Concern | Existing primitive | Reuse |
|---------|--------------------|-------|
| Identity of a sub-agent | `Session` row | A spawned sub-agent is a child `Session` with `parent_session_id` set (already supported by `fork`). |
| Communication | `Session.messages` + a new `assistant` message kind tag | Parent reads the child's `final` message via `SessionStorePort.get(child_id)`. |
| Policy isolation | `PolicyPort` + shell profiles | Child session created with its own `policy_profile` and tool allowlist. |
| Tracing | One `TraceRecorderPort` per process | Same recorder; events carry `session_id` already; add `parent_session_id` to `session_started` payload. |
| Replay | `ReplayModel` + `FrozenClock` | Replay the parent and each child independently; an integration replay step (Phase 6.x) cross-links them by ID. |
| Memory | `MemoryStorePort` (KV) | Child gets a scoped namespace (`session:{child_id}:notes`); parent can read child notes after completion. |
| Artifacts (Phase 5.2) | `ArtifactStorePort` | Refs are valid across parent + child sessions in the same workspace. |

**No new Port is required for the supervisor PoC.** That is a strong
signal we picked a shape that the rest of HarnessLab already accommodates.

---

## 5. Open questions (must answer before Phase 6 implementation)

1. **Spawn API surface.** Does the parent issue a tool call
   (`tool_name: spawn_sub_agent`) or a new `Decision.kind: spawn`?
   - *Recommendation:* a built-in tool, behind policy, so existing
     `tool_executed` / `tool_denied` event types cover it. Avoids a new
     decision kind.
2. **Synchronous vs. async sub-agents.** Does the parent block on the
   child, or does the child run in the background and post results
   asynchronously?
   - *Recommendation (PoC):* synchronous only. Async re-introduces 2.4
     concerns. Revisit when a real interactive use case forces it.
3. **Cost / step bounds.** A parent that can spawn children that can
   spawn children is an unbounded fork bomb in token space.
   - *Recommendation:* `RuntimeLimits.max_sub_agent_depth` (default 1) +
     `max_sub_agents_per_session` (default 4) + `max_total_steps`
     across the tree.
4. **Trace ergonomics.** `harnesslab replay`, `metrics`, `context` were
   built session-at-a-time. How do they present a tree?
   - *Recommendation (PoC):* add a `--include-children` flag; default
     to single-session for backwards compatibility. Defer dedicated
     tree-view UI until the supervisor PoC has real data.
5. **Determinism.** A supervisor that picks "which sub-agent" can
   diverge on rerun.
   - *Recommendation:* sub-agent spawn arguments must be a deterministic
     function of the parent's `Decision`. Trace replay drives the same
     spawn from the same recorded `tool_executed`.
6. **Failure model.** What does the parent see if the child crashes,
   exceeds `max_steps`, or returns `ask_user`?
   - *Recommendation:* the parent's `spawn_sub_agent` tool returns a
     normalized `ToolResult` with `child_session_id`, `outcome`,
     `final_message`, `step_count`. `ask_user` from a child rolls up to
     the parent as "child paused, your call".
7. **Memory and proposal lifecycle.** Sub-agents emitting
   `/remember-global` could pollute workspace notes.
   - *Recommendation:* by default, children cannot write workspace
     memory; only the parent can. Proposals (`harnesslab propose`)
     remain a CLI step on the parent trace, unchanged.
8. **UI shape.** Should the Web UI render the tree at all?
   - *Recommendation:* PoC adds a single "spawned children" tab on a
     session page that links to child session views; no live streaming
     tree until product feedback says it matters.

---

## 6. AGENTS.md changes required

Phase 6 implementation cannot land without an explicit AGENTS.md update
in the same commit. The minimum diff would be:

- **"Must NOT include yet"** → remove `Multi-agent orchestration`,
  add `Asynchronous / background sub-agents` (still forbidden).
- **"Architectural Rules"** → add: *Sub-agents are child Sessions, not a
  new contract. Spawn happens via a policy-gated tool, never via a
  Port the loop calls directly.*
- **"Safety and Tooling Rules"** → add: *Sub-agent spawns are bounded by
  `RuntimeLimits.max_sub_agent_depth` and `max_sub_agents_per_session`;
  children inherit the strictest of (parent profile, requested profile).*
- **"Agent Loop Contract"** → clarify: parent-loop terminal decisions
  (`final`, `ask_user`) still terminate the parent's inner loop;
  child outcomes surface as tool results, not as new decision kinds.

---

## 7. Minimum PoC (the "Phase 6 deliverable")

Goal: **prove the supervisor shape works on one real research task,
end-to-end, with replay intact**. Not a feature; an experiment.

1. Add `tools/spawn_sub_agent.py`: a policy-gated tool that
   - accepts `goal`, optional `policy_profile`, optional `max_steps`
   - calls `HarnessLoop.start(goal=…, parent_session_id=…)` then
     `run_session(child_id, goal, max_steps=…)`
   - returns a normalized `ToolResult` per §5 question 6.
2. Add `RuntimeLimits.max_sub_agent_depth` and
   `max_sub_agents_per_session`; enforce in the tool.
3. Add `parent_session_id` to the `session_started` trace payload.
4. Extend `harnesslab session show ID` with `--include-children`.
5. One **deterministic** eval task `supervisor_research_then_write`:
   - parent gets a goal, plans (Phase 5.3), spawns one research child,
     spawns one writer child, returns a `final`.
   - `SimpleModel` drives both parent and children with `/plan` /
     `/tool spawn_sub_agent {...}` / `/final` commands; no LLM in eval.
6. One **live** smoke task under `RUN_LIVE=1` (network-tagged) using
   Anthropic Claude as the supervisor over a 2-child research task.

**Exit criteria for the PoC** (which, if not all met, kills Phase 6):

- Deterministic eval green; baseline updated cleanly.
- Live smoke produces a parent trace + 2 child traces, all of which
  replay independently with no divergence.
- AGENTS.md updated per §6.
- The PoC reveals a concrete operator pain point that Phase 5
  single-agent could not address (recorded in the commit message).

If the PoC succeeds, Phase 6.x can plan the productionization
(async, streaming UI, scheduling). If it fails or the pain isn't
visible, we keep multi-agent in `Deferred` and stop spending design
budget on it.

---

## 8. What this RFC explicitly does NOT decide

- The exact spawn-tool name or argument schema (lock when PoC starts).
- Whether sub-agents may themselves spawn (locked at PoC depth = 1).
- Streaming presentation in the Web UI.
- Marketplace, hosted runtime, distributed scheduling — out of scope
  forever for HarnessLab unless the project's mission statement
  changes.

---

## 9. References

- [LangGraph supervisor pattern](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/)
- [OpenAI Agents SDK handoffs](https://github.com/openai/openai-agents-python)
- [Anthropic sub-agent patterns](https://docs.anthropic.com/en/docs/agents-and-tools)
- [Model Context Protocol](https://modelcontextprotocol.io/) (Phase 5.4
  prerequisite)
- HarnessLab's existing `Session.parent_session_id` and `HarnessLoop.fork`
  (Phase 2.3) — already the right substrate.
