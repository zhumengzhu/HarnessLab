# HarnessLab TUI

Status: **Beta** — production-oriented Textual operator surface (`harnesslab tui`).

## Launch

```bash
uv run harnesslab tui
# or from workspace root:
cd /path/to/project && uv run harnesslab tui
```

Uses SQLite session store and the same `HarnessLoop` as CLI/Web.

## Layout

```text
┌ Sessions ──┬─ Chat log ────────────────┬─ Trace / Activity ──┐
│ session A  │ you: …                    │ tool read_file · ok │
│ session B* │ assistant: …              │ llm · 120 tok · 800ms│
└────────────┴───────────────────────────┴─────────────────────┘
 status: session · model · failover · turns/steps
```

- **Left:** recent sessions (newest first); click to resume.
- **Center:** conversation log + composer (`/compact`, `/help` supported via loop).
- **Right:** span-derived activity (tools, hooks, LLM calls, compaction, spawn).

## Keybindings

| Key | Action |
| --- | --- |
| `Enter` | Send message |
| `n` | New session |
| `r` | Refresh session list |
| `?` | Help |
| `q` | Quit |

Turns run in a **background worker** so the UI stays responsive during long agent runs.

## vs Web UI

| Feature | Web | TUI |
| --- | --- | --- |
| Multi-session sidebar | ✅ | ✅ |
| Span waterfall | ✅ Jaeger tree | Activity stream |
| Token/context inspector | ✅ Trace tab | LLM token line only |
| Settings / failover toggle | ✅ | config.json only |
| Streaming token deltas | ✅ SSE | ✅ live preview (`stream-live`) during turn |

TUI targets **daily terminal use** and **quick session switching**; deep trace
review remains in the Web Trace tab.

## Architecture

- `src/harnesslab/tui/app.py` — Textual app (layout, workers, bindings)
- `src/harnesslab/tui/span_feed.py` — span → Rich markup formatter

See also [`docs/architecture/tui-stack-options.md`](../architecture/tui-stack-options.md).
