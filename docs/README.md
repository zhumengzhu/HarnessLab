# HarnessLab Documentation

Central index for learning and contributing to HarnessLab. Start with
**why the repo exists**, then follow the architecture docs while reading
the matching code paths.

## Start here

| Doc | Audience | Content |
| --- | --- | --- |
| [`why-harnesslab.md`](why-harnesslab.md) | New contributors & learners | Learning goals, what this is **not**, reading order |
| [`../README.md`](../README.md) | Daily users | Quick start, CLI, Web UI, configuration |
| [`../AGENTS.md`](../AGENTS.md) | Humans + AI agents | Architecture rules, quality gate, proposal policy |
| [`roadmap.md`](roadmap.md) | Planners | Phased delivery + **What's next** (sub-agent, skill install) |

## Architecture (runtime contracts)

These docs describe **stable behavior**. If you change a Port or trace
payload shape, update the relevant file and tests in the same PR.

| Doc | Topics |
| --- | --- |
| [`architecture/overview.md`](architecture/overview.md) | System map, loop, compaction, Web API, memory, skills |
| [`architecture/data-model.md`](architecture/data-model.md) | Session, Message, TraceEvent, ContextSnapshot |
| [`architecture/tool-runtime.md`](architecture/tool-runtime.md) | Tool registry, policy, audit events |
| [`architecture/compaction.md`](architecture/compaction.md) | Auto/manual compaction, thinking after compact |
| [`architecture/web-api.md`](architecture/web-api.md) | Localhost HTTP + SSE contract |
| [`architecture/webui-design.md`](architecture/webui-design.md) | Chat UX, SSE, Thinking/Thought, composer slash commands |
| [`architecture/provider-expansion.md`](architecture/provider-expansion.md) | ModelPort adapters, catalog, transforms |
| [`architecture/model-parameters.md`](architecture/model-parameters.md) | Thinking / effort operator controls |
| [`architecture/frontend-ts-migration.md`](architecture/frontend-ts-migration.md) | TS WebUI migration phases and status |
| [`architecture/multi-agent-exploration.md`](architecture/multi-agent-exploration.md) | Supervisor PoC, spawn_sub_agent |
| [`architecture/diagram-conventions.md`](architecture/diagram-conventions.md) | Mermaid style rules |

## Research (non-normative)

| Doc | Content |
| --- | --- |
| [`research/harness-landscape.md`](research/harness-landscape.md) | 2026 agent harness capability map vs HarnessLab |
| [`research/claude-code-monitor.md`](research/claude-code-monitor.md) | External agent observation notes |
| [`guides/deep-research-landscape.md`](guides/deep-research-landscape.md) | Deep research skills vs tools (DeerFlow, OpenCode, HarnessLab design) |
| [`guides/web-research-providers.md`](guides/web-research-providers.md) | Search/fetch providers, pricing, proxy |

## Other repo docs

| Path | Content |
| --- | --- |
| [`../eval/README.md`](../eval/README.md) | YAML eval suite, baseline workflow |
| [`../webui/README.md`](../webui/README.md) | Build/serve TS frontend |
| [`../proposals/README.md`](../proposals/README.md) | Advisory improvement proposals |
| [`../skills/`](../skills/) | Built-in workspace skills (`deep-research`, `humanizer`, `compact`) |

## Suggested learning paths

### Path A — Understand the harness (1–2 hours)

1. [`why-harnesslab.md`](why-harnesslab.md)
2. Run `uv run harnesslab run "hello" --model simple` and open
   `.harnesslab/trace.jsonl`
3. [`architecture/overview.md`](architecture/overview.md) — Agent loop section
4. [`architecture/tool-runtime.md`](architecture/tool-runtime.md)
5. `uv run harnesslab eval`

### Path B — Extend tools or policy

1. Path A through tool-runtime
2. Add or change a tool under `src/harnesslab/tools/`
3. Add an eval task under `eval/tasks/` and update baseline if needed
4. Update `architecture/tool-runtime.md` if the public tool surface changed

### Path C — Web UI or streaming

1. [`architecture/webui-design.md`](architecture/webui-design.md)
2. [`architecture/frontend-ts-migration.md`](architecture/frontend-ts-migration.md)
3. [`../webui/README.md`](../webui/README.md) — build and serve
4. Trace a turn: browser → `POST /api/sessions/{id}/messages` (SSE) → loop

### Path D — Providers and thinking models

1. [`architecture/provider-expansion.md`](architecture/provider-expansion.md)
2. [`architecture/model-parameters.md`](architecture/model-parameters.md)
3. Inspect `providers/transforms/` replay policies and `Message.reasoning_text`

## Maintenance rules

- **Behavior change** → update the matching architecture doc + tests.
- **Port / data contract change** → also update `overview.md` and
  `data-model.md` (see [`../AGENTS.md`](../AGENTS.md)).
- **Learning / motivation** → `why-harnesslab.md` or this index; avoid
  duplicating long tutorials in README and docs.
- **Research** → `docs/research/`; do not treat as implementation spec.
