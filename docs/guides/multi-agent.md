# Multi-agent supervisor (Phase 6)

HarnessLab uses a **supervisor + child sessions** pattern: the parent loop
calls `spawn_sub_agent`, which runs a child `Session` to completion and
returns JSON with `child_session_id` and `final_response`. Each session has
its own trace slice, budget counters, and replay path.

This is **opt-in** — disabled by default so single-agent workflows stay
unchanged.

## Enable

**Config file** (`~/.config/harnesslab/config.json`):

```json
{
  "loop": {
    "multi_agent": {
      "enabled": true
    }
  }
}
```

**Web UI:** Settings → Advanced → **Multi-agent (spawn_sub_agent)** toggle
(writes the same key; restart `./hl-serve` so the tool registers at startup).

**CLI runtime:** `build_runtime` registers `spawn_sub_agent` only when
`loop.multi_agent.enabled` is true.

## Limits

Configured via `RuntimeLimits` (defaults in `core/config.py`):

| Limit | Default | Enforced in |
| --- | --- | --- |
| `max_sub_agent_depth` | 1 | `SpawnSubAgentTool` (parent chain depth) |
| `max_sub_agents_per_session` | 4 | spawn count per parent session |

Example in config (when supported in operator config):

```json
"loop": {
  "multi_agent": { "enabled": true },
  "limits": {
    "max_sub_agent_depth": 1,
    "max_sub_agents_per_session": 4
  }
}
```

## Tool contract

```json
{
  "goal": "Research sub-topic X and return bullet summary",
  "max_steps": 5
}
```

Returns normalized JSON:

```json
{
  "child_session_id": "ses_…",
  "parent_session_id": "ses_…",
  "final_response": "…"
}
```

Trace events on the **parent** session:

- `sub_agent_spawned` — child id, goal, max_steps
- `sub_agent_completed` — step_count, status, final preview, child budget_usage

Child sessions set `parent_session_id` on `session_started`.

## Operator visibility

```bash
# Parent metadata + child summary rows
harnesslab session show ses_parent --include-children

# Replay parent, then each child (in trace order)
harnesslab replay .harnesslab/spans.jsonl \
  --session-id ses_parent --include-children
```

**Web UI:** child list in the sidebar (`ChildSessionsPanel`); during a parent
turn, nested **ChildAgentRunCard** rows stream via SSE fan-in; Activity feed
shows spawn / finished events.

## Budget isolation

Token/cost budgets accumulate on **each session separately**. A child’s
`budget_usage` does not roll into the parent’s counters; inspect child rows
via `session show --include-children` or the child session detail view.

## Eval / replay

Deterministic eval tasks:

- `spawn_sub_agent_roundtrip`
- `supervisor_research_then_write`

Parent replay uses a **spawn stub** (recorded tool output) so nested live
children are not re-executed; `sub_agent_spawned` / `sub_agent_completed`
events are ignored in semantic divergence compare. Replay children with
`--include-children` for independent round-trip checks.

## Not included (Phase 6)

- Async / background sub-agent fleets
- Unbounded spawn trees (depth and per-session caps are mandatory)
- Cross-machine scheduling or worker pools

Design RFC: [`architecture/multi-agent-exploration.md`](../architecture/multi-agent-exploration.md).
