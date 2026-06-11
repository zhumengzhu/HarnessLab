# HarnessLab Web UI vs claude-tap — Observability Gap Analysis

Status: **research snapshot** (2026-06). Use this when deciding which
trace-review features to port into HarnessLab vs keeping claude-tap as an
external HTTP proxy viewer.

## Positioning

| Dimension | [claude-tap](https://github.com/zhumengzhu/claude-tap) | HarnessLab Web UI |
| --- | --- | --- |
| Role | Local HTTP/WS **proxy** + multi-client trace reviewer | **Harness runtime** chat + native OTel spans |
| Data model | One record = upstream API request/response (JSONL) | `SpanRecord` forest (`parent_span_id`, events, links) |
| Primary surfaces | Standalone viewer + session dashboard | Session tabs: Chat / Trace / Activity |

Neither replaces the other: claude-tap inspects **raw vendor traffic** from
arbitrary CLIs; HarnessLab inspects **loop semantics** (policy, hooks,
compaction, sub-agents, checkpoints).

## Feature matrix

| Feature | claude-tap | HarnessLab | Gap |
| --- | --- | --- | --- |
| Span waterfall / hierarchy | Flat turn list only | Jaeger-style native tree | claude-tap lacks execution hierarchy |
| Live streaming | SSE append of API records | Span lifecycle SSE + token deltas | Different streams |
| Request/response deep read | Full HTTP, cURL export, SSE rebuild | `ModelCallInspector` (prompt blocks, API messages) | HarnessLab lacks raw HTTP proxy view |
| Turn-to-turn diff | Structured diff (`diff.js`) | Prompt block + `api_messages` index diff | Full line-level message diff TBD |
| Global trace search | Cmd+F across records | Deep span filter (attrs + metrics + prompt text) | No dedicated Cmd+F shortcut |
| Tool inspection | Rich tool_use / tool_result | Tool I/O panel + artifact fetch via Web API | Full output when externalized only |
| Context / token audit | Per-request usage + cache R/W | Context inspector + turn token bar in Trace | Cache R/W breakdown TBD |
| Metrics dashboard | Session aggregates in viewer | Usage nav + OTel/Grafana path | claude-tap lacks cost trends |
| Export | JSONL, compact, HTML self-contained | JSONL copy/download + **self-contained HTML** | claude-tap lacks span hierarchy in export |
| Hook / policy visibility | N/A (proxy layer) | `tool.hooks.*` spans + events | Activity + Trace now surface hooks (2026-06) |
| Checkpoint / rewind | N/A | Trace tab checkpoints | HarnessLab-only |
| Sub-agent links | Thread / response-id chains | Span links + child panel | Different correlation models |
| Replay / eval UI | N/A | CLI only | **HarnessLab Web: no divergence UI** |

## HarnessLab strengths (keep investing here)

- Native **span forest** with `parent_span_id` (Observability v2)
- **Activity** feed for operator events (tool deny, compact, spawn, failover, hooks)
- **LiveTurn** + token streaming during `llm.generate`
- **Checkpoint rewind** embedded in Trace
- **Sub-agent** trace fan-in and child session panel

## claude-tap strengths (use when debugging external agents)

- Inspect **exact** Anthropic/OpenAI/Gemini/Codex payloads
- **Adjacent-turn diff** for prompt drift
- **Global search** and path/tool filters on API traffic
- **Portable HTML** export for sharing traces without a server

## Recommended HarnessLab follow-ups (priority)

1. ~~Render **`ContextSnapshot`** in Trace `ModelCallInspector`~~ — **Done (2026-06)**.
2. ~~**Turn-level token summary** in Trace toolbar~~ — **Done (2026-06)**.
3. ~~**Prompt diff** between adjacent `llm.generate` spans~~ — **Partial (2026-06)**; block sizes + `api_messages` index diff; line-level TBD.
4. ~~**Tool inspector** with args + output preview~~ — **Done (2026-06)**; artifact fetch via `GET /api/sessions/{id}/artifacts/{ref}`.
5. ~~**Trace global search** across attributes/metrics/prompt~~ — **Done (2026-06)** via deep filter.
6. ~~**Self-contained HTML export** for offline review~~ — **Done (2026-06)** (Trace JSONL panel).
7. **TUI production** — multi-pane + trace feed + token streaming preview (**Beta**, see [`guides/tui.md`](../guides/tui.md)).

## References

- HarnessLab: [`docs/architecture/observability-v2.md`](../architecture/observability-v2.md), [`docs/architecture/webui-design.md`](../architecture/webui-design.md)
- claude-tap: local `~/Github/claude-tap` — `claude_tap/viewer_assets/`, `docs/guides/agent-trace-viewer.md`
- Related HarnessLab research: [`docs/research/claude-code-monitor.md`](claude-code-monitor.md)
