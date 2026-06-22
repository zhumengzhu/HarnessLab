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

- **Left:** recent sessions (newest first); click to resume. `/find <query>`
  filters the list by title / goal / id.
- **Center:** conversation log + composer (`/compact`, `/help` supported via loop).
- **Right:** span-derived activity (tools, hooks, LLM calls, compaction, spawn).

The status bar also surfaces the session's cumulative `cost=$…` and a
`budget=<soft|hard>_exceeded` marker once a budget threshold is crossed.

## Keybindings

| Key | Action |
| --- | --- |
| `Enter` | Send message |
| `n` | New session |
| `f` | Fork current session |
| `r` | Refresh session list |
| `v` | Toggle verbose trace (tool errors/artifacts, token split, context %) |
| `y` | Copy the last assistant reply to the clipboard |
| `PgUp` / `PgDn` | Scroll the chat log |
| `Esc` | Stop the running turn (cooperative cancel) |
| `s` | Show settings summary |
| `?` | Help (lists all slash commands) |
| `q` | Quit |

When a turn ends in `ask_user` (or the step budget is reached) the session
enters `waiting_user`: the chat shows an `⏳ the agent is waiting for your
reply` marker and the composer placeholder switches to prompt for an answer.

`Esc` requests a **cooperative cancel** of the in-flight turn. It takes effect
at the next step boundary (before the next model call, and before a decided
tool is executed), so an already in-flight model/tool call finishes first; a
pending tool is **not** run after the stop. The turn ends as `cancelled` and
the session is left `waiting_user` so you can resume by sending a new message.

Slash commands: `/help`, `/settings`, `/model <backend>`, `/failover on|off`,
`/compact`, `/remember <text>`, `/find <query>` (empty query clears the filter),
`/search <query>` (search the current chat history), `/rename <title>`,
`/delete` (delete the current session), `/skill`, `/copy`.

`/delete` removes the current session (and its messages) and switches to the
most recent remaining session, or starts a fresh one when none are left. The
chat log scrolls with `PgUp` / `PgDn` (and the mouse wheel).

The composer offers **inline autocomplete** for slash commands (and common
argument variants such as `/model deepseek` or `/failover on`): type `/`, then
accept the ghost-text suggestion with `→` / `Tab`. `/help` (or `?`) prints the
full command list with descriptions.

Assistant replies render as **Markdown** (headings, lists, code blocks); copy
the latest one with `y` or `/copy`.

Turns run in a **background worker** so the UI stays responsive during long agent runs.

## vs Web UI

| Feature | Web | TUI |
| --- | --- | --- |
| Multi-session sidebar | ✅ | ✅ (`/find` filter) |
| Fork session | ✅ button | ✅ `f` key |
| Rename / delete session | ✅ | ✅ `/rename` · `/delete` |
| Chat history search | ✅ | ✅ `/search` |
| Session cost/budget | ✅ panel | ✅ status bar |
| Span waterfall | ✅ Jaeger tree | Per-turn hierarchical tree |
| Token/context inspector | ✅ Trace tab | `v` verbose: token split + context % |
| `ask_user` await affordance | ✅ | ✅ marker + composer placeholder |
| Settings / failover toggle | ✅ | `/settings` · `/failover` · `/model` · `s` key |
| Streaming token deltas | ✅ SSE | ✅ live preview (`stream-live`) during turn |
| Slash command discovery | ✅ palette | ✅ inline autocomplete + `/help` |
| Markdown replies | ✅ | ✅ Rich Markdown render |
| Copy last reply | ✅ | ✅ `y` / `/copy` |
| Cancel running turn | ✅ | ✅ `Esc` (cooperative) |

TUI targets **daily terminal use** and **quick session switching**; deep trace
review remains in the Web Trace tab.

## Observability scope (intentional)

The TUI is a **lean operator surface** (in the spirit of opencode / Claude
Code / pi), **not** a terminal trace explorer. Observability is split across
three layers, and the TUI deliberately only owns the shallowest one:

| Layer | Surface | Depth |
| --- | --- | --- |
| **Glance** | **TUI** | Lightweight, inline, opt-in |
| **Inspect** | **Web Trace tab** | Jaeger waterfall, `ModelCallInspector`, prompt diff, replay, ⌘F, HTML export |
| **Script** | **CLI** | `replay` / `metrics` / `context` / `session show` |

**The TUI keeps** (all "glance"-level, cheap to render):

- Status line: `model / failover / turns / steps / cost / budget`.
- Per-turn span feed in the right pane (tool / hook / llm / compact / spawn /
  policy-denied), one line each — the terminal equivalent of inline tool rows.
- `v` verbose toggle (opt-in): token split, context %, tool error/artifact.

**The TUI deliberately does NOT implement** (use Web Trace / CLI instead):

- Navigable / collapsible span tree, in-pane span search (`⌘F`).
- Per-span deep I/O inspector, prompt diff, replay-divergence UI, HTML export.

Rebuilding these in the terminal would duplicate the Web Trace tab without
adding learning value. A "trace explorer in the TUI" is **out of scope**.

> Note: features like **cancelling a running turn** (`Esc`, shipped) are
> *basic usability*, not observability — they remain in scope for the TUI
> even though deep trace inspection does not.

## Architecture

- `src/harnesslab/tui/app.py` — Textual app (layout, workers, bindings)
- `src/harnesslab/tui/span_feed.py` — span → Rich markup formatter
- `src/harnesslab/tui/session_list.py` — sidebar label / filter / status helpers
- `src/harnesslab/tui/settings_actions.py` — slash parsing, command catalog, model/failover
- `src/harnesslab/tui/history.py` — chat history search

See also [`docs/architecture/tui-stack-options.md`](../architecture/tui-stack-options.md).
